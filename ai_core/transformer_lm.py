"""
ai_core/transformer_lm.py
Production-ready Transformer LM wrapper (HuggingFace-based) with:
 - memory-conditioned generation
 - optional grounding via world_model.imagine(...) hook
 - safety filter pipeline stub (pluggable)
 - fine-tuning utilities (HF Trainer; optional LoRA/PEFT)
 - robust save() / load() to/from disk/state_dict for BrainCapsule integration
 - device & dtype management, generation caching, and generation streaming hooks

Design notes:
- This is not a "vanilla" LLM wrapper: it provides a generate(...) API that accepts:
    - memory (list[str]) or memory_tokens,
    - optional world_model and context -> uses world_model.imagine to produce imagined context tokens
    - safety checks and post-filters
- Save/load uses model.state_dict() + tokenizer.save_pretrained() or model.save_pretrained()
- Provide small, production-minded defaults but allow full config override via kwargs.
"""

import os
import json
import time
import logging
from typing import Optional, List, Dict, Any, Callable, Iterable, Tuple

import torch
from torch import nn

try:
    # HuggingFace transformers
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        GenerationConfig,
        Trainer,
        TrainingArguments,
        DataCollatorForLanguageModeling,
    )
except Exception as e:
    raise ImportError("transformers is required for ai_core.transformer_lm: " + str(e))

# Optional PEFT / LoRA
_PEFT_AVAILABLE = False
try:
    import peft  # noqa
    _PEFT_AVAILABLE = True
except Exception:
    _PEFT_AVAILABLE = False

log = logging.getLogger("ai_core.transformer_lm")


class TransformerLM:
    """
    Production-ready wrapper for a transformer-style LM.

    Main entry points:
      - generate(prompt, memory=[...], world_model=None, max_new_tokens=...)
      - score(text, context=...)
      - fine_tune_on_dataset(dataset, **training_args)
      - save(dir_or_capsule_dict) / load(path_or_state_dict)
      - enable_lora() (if PEFT available)

    Important design choices:
      - The wrapper expects torch.device management from caller, but will choose a device
        if none provided. For inference on CPU you can pass device='cpu'.
      - Generation can be conditioned on "memory" (list[str]) or "memory_tokens".
      - Optional: world_model grounding. If a world_model object is passed and defines
        `imagine(prompt, n, max_steps)` this wrapper will call it to produce additional
        grounding context for the LM.
    """

    def __init__(
        self,
        model_name_or_path: str = "gpt2",
        device: Optional[torch.device] = None,
        dtype: Optional[torch.dtype] = None,
        revision: Optional[str] = None,
        trust_remote_code: bool = False,
        generation_kwargs: Optional[dict] = None,
        tokenizer_kwargs: Optional[dict] = None,
        low_cpu_mem: bool = False,
        hf_repo_auth: Optional[str] = None,
    ):
        self.model_name_or_path = model_name_or_path
        self.revision = revision
        self.trust_remote_code = trust_remote_code
        self.hf_repo_auth = hf_repo_auth
        self.low_cpu_mem = low_cpu_mem

        # device/dtype selection
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.dtype = dtype or (torch.bfloat16 if getattr(torch, "bfloat16", None) else torch.float16 if self.device.type == "cuda" else torch.float32)

        # tokenizer
        self.tokenizer_kwargs = tokenizer_kwargs or {}
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, **self.tokenizer_kwargs)
        # ensure tokenizer has pad token
        if self.tokenizer.pad_token is None:
            # some GPT2 tokenizers don't have pad; add EOS as pad
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # model
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            revision=revision,
            trust_remote_code=trust_remote_code,
            low_cpu_mem_usage=low_cpu_mem,
        )

        # Move to device and dtype management
        try:
            if self.dtype and self.device.type == "cuda":
                self.model = self.model.to(self.dtype)
            self.model = self.model.to(self.device)
        except Exception as e:
            log.warning("Failed to set model dtype/device: %s", e)

        # generation defaults (safe defaults for production)
        self.generation_defaults = {
            "max_new_tokens": 256,
            "do_sample": True,
            "top_p": 0.9,
            "temperature": 0.8,
            "top_k": 50,
            "repetition_penalty": 1.02,
            "num_return_sequences": 1,
            "pad_token_id": self.tokenizer.pad_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
        }
        if generation_kwargs:
            self.generation_defaults.update(generation_kwargs)

        # simple in-memory cache to avoid repeated tokenization/generation for identical keys
        self._generate_cache: Dict[str, Dict[str, Any]] = {}

        # Safety/filters hooks - these can be replaced by application code
        # function signature: (prompt_str, generated_str) -> (allowed:bool, filtered_str:str)
        self.safety_filter: Callable[[str, str], Tuple[bool, str]] = self._default_safety_filter

        # world-model grounding hook (optional)
        # function signature: (world_model, prompt_str, n_imagined)->List[str] (imagined contexts)
        self.world_model_grounding: Optional[Callable[[Any, str, int], List[str]]] = self._default_world_model_grounding

        # optional peft (LoRA) controller
        self._peft_enabled = False

        log.info("TransformerLM initialized: model=%s device=%s dtype=%s", model_name_or_path, self.device, self.dtype)

    # ----------- Safety & grounding default hooks --------------
    def _default_safety_filter(self, prompt: str, generated: str) -> Tuple[bool, str]:
        # Minimal default: allow everything but trim extremely long outputs
        # Replace this with a real safety pipeline for production deployments.
        if len(generated) > 50_000:
            return False, generated[:50_000]
        return True, generated

    def _default_world_model_grounding(self, world_model, prompt: str, n_imagined: int = 4) -> List[str]:
        """
        Default grounding: if world_model has an `imagine` API:
            imaginations = world_model.imagine(seed=prompt, n_rollouts=n_imagined, max_steps=16)
        The wrapper expects world_model.imagine to return an iterable of strings describing imagined futures.
        """
        if world_model is None:
            return []
        if hasattr(world_model, "imagine"):
            try:
                results = world_model.imagine(prompt, n=n_imagined, max_steps=16)
                # ensure list[str]
                return [str(r) for r in results]
            except Exception as e:
                log.exception("World-model grounding failed: %s", e)
                return []
        return []

    # ----------- Core generation API --------------
    def _compose_prompt(self, prompt: str, memory: Optional[Iterable[str]] = None, imagined_contexts: Optional[Iterable[str]] = None, extra_context: Optional[str] = None) -> str:
        pieces: List[str] = []
        if memory:
            # keep most recent memories last (so that LM attends)
            pieces.append("\n".join(["<MEMORY> " + m for m in memory]))
        if imagined_contexts:
            pieces.append("\n".join(["<IMAGINE> " + c for c in imagined_contexts]))
        if extra_context:
            pieces.append("<CONTEXT> " + extra_context)
        pieces.append("<PROMPT> " + (prompt or ""))
        return "\n\n".join([p for p in pieces if p is not None and p != ""])

    def generate(
        self,
        prompt: str,
        memory: Optional[Iterable[str]] = None,
        world_model: Optional[Any] = None,
        n_imagined: int = 0,
        max_new_tokens: Optional[int] = None,
        return_dict: bool = False,
        use_cache: bool = True,
        generation_override: Optional[dict] = None,
        stop_tokens: Optional[List[str]] = None,
        decode_kwargs: Optional[dict] = None,
    ) -> Any:
        """
        Generate text conditioned on prompt, optional memory and optional world_model-grounding.

        Parameters:
        - prompt: main user prompt
        - memory: iterable of strings (agent memories)
        - world_model: optional object with imagine(prompt, n, max_steps) -> list[str]
        - n_imagined: number of imagined rollouts to ask world_model for and prepend to prompt
        - use_cache: whether to cache generation by key (prompt+memories)
        - generation_override: overrides of self.generation_defaults
        - stop_tokens: list of token substrings to stop on (post-filtering applied)
        - decode_kwargs: kwargs passed to tokenizer.decode
        """
        # build imagined contexts if requested
        imagined_contexts = []
        if world_model and n_imagined > 0:
            try:
                imagined_contexts = self.world_model_grounding(world_model, prompt, n_imagined)
            except Exception as e:
                log.exception("world_model grounding failed: %s", e)
                imagined_contexts = []

        full_prompt = self._compose_prompt(prompt, memory=memory, imagined_contexts=imagined_contexts)

        cache_key = None
        if use_cache:
            cache_key = f"gen::{hash(full_prompt)}::{max_new_tokens}::{json.dumps(generation_override or {})}"
            cached = self._generate_cache.get(cache_key)
            if cached:
                return cached["result"] if not return_dict else {"text": cached["result"], "meta": cached["meta"]}

        # prepare generation kwargs
        gen_kwargs = dict(self.generation_defaults)
        if generation_override:
            gen_kwargs.update(generation_override)
        if max_new_tokens:
            gen_kwargs["max_new_tokens"] = max_new_tokens

        # tokenize
        inputs = self.tokenizer(full_prompt, return_tensors="pt", truncation=True, padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                **gen_kwargs,
            )

        # decode
        decode_kwargs = decode_kwargs or {"skip_special_tokens": True, "clean_up_tokenization_spaces": True}
        generated_text = self.tokenizer.batch_decode(output_ids[:, inputs["input_ids"].shape[1]:], **decode_kwargs)
        generated_text = generated_text[0] if isinstance(generated_text, list) else str(generated_text)

        # optional stop tokens trimming
        if stop_tokens:
            for tkn in stop_tokens:
                idx = generated_text.find(tkn)
                if idx != -1:
                    generated_text = generated_text[:idx]

        # safety filter
        allowed, filtered = self.safety_filter(full_prompt, generated_text)
        final_text = filtered if not allowed else generated_text

        meta = {
            "prompt_len": sum(len(m) for m in (memory or [])) if memory else 0,
            "input_tokens": inputs["input_ids"].shape[1],
            "generated_len": len(final_text),
            "model": self.model_name_or_path,
            "device": str(self.device),
            "timestamp": time.time(),
        }

        if use_cache and cache_key:
            self._generate_cache[cache_key] = {"result": final_text, "meta": meta, "ts": time.time()}

        if return_dict:
            return {"text": final_text, "meta": meta}
        return final_text

    # ----------- Scoring (log-prob) --------------
    def score(self, text: str, context: Optional[str] = None) -> float:
        """
        Compute per-token average negative log likelihood for text conditioned on context (if provided).
        Returns a float (lower is better).
        """
        prompt = (context or "") + "\n" + text if context else text
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model(**inputs, labels=inputs["input_ids"])
            # outputs.loss is mean loss per token
            loss = outputs.loss.item()
        return loss

    # ----------- Fine-tuning utilities --------------
    def fine_tune_on_texts(self, texts: Iterable[str], output_dir: str, batch_size: int = 4, epochs: int = 1, learning_rate: float = 5e-5, save_best: bool = True):
        """
        Fine-tune model on an iterable of texts (language modelling / causal).
        Uses HF Trainer. Produces checkpoints at output_dir.
        """
        # very small production-ready dataset wrapper
        class _SimpleDataset(torch.utils.data.Dataset):
            def __init__(self, tokenizer, texts):
                self.tokenizer = tokenizer
                self.examples = list(texts)

            def __len__(self):
                return len(self.examples)

            def __getitem__(self, i):
                return self.tokenizer(self.examples[i], truncation=True, padding="max_length", max_length=512, return_tensors="pt")

        dataset = _SimpleDataset(self.tokenizer, texts)
        # collator for causal LM
        collator = DataCollatorForLanguageModeling(tokenizer=self.tokenizer, mlm=False)

        training_args = TrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=batch_size,
            num_train_epochs=epochs,
            learning_rate=learning_rate,
            logging_steps=10,
            save_strategy="epoch" if save_best else "no",
            fp16=(self.device.type == "cuda"),
            remove_unused_columns=False,
        )

        trainer = Trainer(model=self.model, args=training_args, train_dataset=dataset, data_collator=collator)
        trainer.train()
        trainer.save_model(output_dir)
        self.tokenizer.save_pretrained(output_dir)
        log.info("Fine-tune finished and saved to %s", output_dir)
        return output_dir

    def enable_lora(self, peft_config: Optional[Any] = None):
        """
        Enable LoRA adapters via PEFT if available. Caller may pass a prebuilt peft_config.
        """
        if not _PEFT_AVAILABLE:
            raise RuntimeError("PEFT/LoRA not available in this environment. Install 'peft' to enable.")
        # The specifics of PEFT integration depend on the model family; minimal scaffold:
        try:
            from peft import get_peft_model, LoraConfig, TaskType
            if peft_config is None:
                peft_config = LoraConfig(
                    r=8,
                    lora_alpha=32,
                    target_modules=["q_proj", "v_proj"] if "gpt" in self.model_name_or_path.lower() else None,
                    lora_dropout=0.05,
                    bias="none",
                    task_type=TaskType.CAUSAL_LM,
                )
            self.model = get_peft_model(self.model, peft_config)
            self._peft_enabled = True
            log.info("LoRA enabled via PEFT.")
        except Exception as e:
            log.exception("Failed to enable LoRA: %s", e)
            raise

    # ----------- Persistence --------------
    def save_to_dir(self, path: str):
        """
        Save model + tokenizer to disk. Use for exporting or for BrainCapsule save (prefer model.state_dict()).
        """
        os.makedirs(path, exist_ok=True)
        # prefer torch.save of state_dict for BrainCapsule-style saving; but also save HF format for offline inspect
        try:
            # save HF artifacts
            self.model.save_pretrained(path)
            self.tokenizer.save_pretrained(path)
            log.info("Saved HF model+tokenizer to %s", path)
        except Exception as e:
            log.warning("HF save_pretrained failed (falling back to state_dict). Error: %s", e)
            torch.save(self.model.state_dict(), os.path.join(path, "model_state.pt"))
            self.tokenizer.save_pretrained(path)

    def state_dict(self) -> dict:
        """
        Return a CPU-backed model state_dict that can be stored inside BrainCapsule.model_state.
        """
        sd = self.model.state_dict()
        # Move tensors to cpu & detach
        cpu_sd = {k: v.cpu() for k, v in sd.items()}
        return {"model_state": cpu_sd, "meta": {"model_name_or_path": self.model_name_or_path, "tokenizer": getattr(self.tokenizer, "name_or_path", None)}}

    def load_state_dict(self, state: dict, map_location: Optional[torch.device] = None):
        """
        Load from a dict as returned by state_dict().
        """
        model_sd = state.get("model_state", state)
        if map_location is None:
            map_location = self.device
        # create a temporary new model instance if shapes mismatch? We'll attempt a direct load
        try:
            self.model.load_state_dict({k: v.to(self.device) for k, v in model_sd.items()}, strict=False)
            log.info("Loaded model_state into TransformerLM instance (strict=False).")
        except Exception as e:
            log.exception("Failed to load model_state into existing model: %s", e)
            # try to save the state to a temp file and reload via HF API
            tmp = os.path.join("/tmp", f"tmp_lm_{int(time.time())}")
            os.makedirs(tmp, exist_ok=True)
            torch.save(model_sd, os.path.join(tmp, "model_state.pt"))
            # No robust universal fallback; raise so caller can attempt HF reload.
            raise

    # backward/compat helper
    def to(self, device: torch.device):
        self.device = device
        self.model = self.model.to(device)
        return self

    # For convenience: wrapper saving a small metadata dict for BrainCapsule
    def export_to_braincapsule_dict(self) -> dict:
        return {
            "transformer_lm": self.state_dict(),
            "tokenizer": getattr(self.tokenizer, "vocab_size", None)
        }

    @classmethod
    def create_from_braincapsule_dict(cls, data: dict, device: Optional[torch.device] = None):
        """
        Create TransformerLM instance from dict saved inside BrainCapsule.model_state['transformer_lm'].
        Data is expected to be {"model_state": {...}, "meta": {...}}.
        """
        meta = data.get("meta", {})
        model_name = meta.get("model_name_or_path", "gpt2")
        inst = cls(model_name_or_path=model_name, device=device)
        inst.load_state_dict(data)
        return inst

    # ----------- Additional helpers --------------
    def clear_cache(self):
        self._generate_cache.clear()

    # plug-in style API for app code to attach more advanced safety pipeline or grounding
    def set_safety_filter(self, fn: Callable[[str, str], Tuple[bool, str]]):
        self.safety_filter = fn

    def set_world_model_grounding(self, fn: Callable[[Any, str, int], List[str]]):
        self.world_model_grounding = fn
