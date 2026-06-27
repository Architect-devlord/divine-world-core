# ai_core/brain_language.py - TRANSFORMER-BASED LANGUAGE LEARNING
"""
Brain Language Extension - Transformer-based Language Intelligence
Learns through experience, not pre-training.
"""

import time, re, numpy as np, torch, torch.nn as nn
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from pathlib import Path
import logging

log = logging.getLogger("brain.language")


class MultimodalGroundingTransformer(nn.Module):
    def __init__(self, concept_dim=256, context_dim=32,
                 n_heads=4, n_layers=2, vocab_size=5000):
        super().__init__()
        self.concept_dim = concept_dim
        self.vocab_size  = vocab_size
        self.word_embeddings  = nn.Embedding(vocab_size, concept_dim)
        self.context_encoder  = nn.Sequential(
            nn.Linear(context_dim, 128), nn.ReLU(), nn.Linear(128, concept_dim))
        enc_layer = nn.TransformerEncoderLayer(
            d_model=concept_dim, nhead=n_heads,
            dim_feedforward=concept_dim*2, dropout=0.1, batch_first=True)
        self.transformer      = nn.TransformerEncoder(enc_layer, num_layers=n_layers)
        self.word_predictor   = nn.Linear(concept_dim, vocab_size)
        self.context_predictor = nn.Linear(concept_dim, context_dim)

    def forward(self, word_ids, context):
        we  = self.word_embeddings(word_ids)
        ce  = self.context_encoder(context).unsqueeze(1)
        out = self.transformer(torch.cat([ce, we], dim=1))
        return {'word_logits':        self.word_predictor(out[:, 1:, :]),
                'predicted_context':  self.context_predictor(out[:, 0, :]),
                'concept_embeddings': out}

    def ground_word(self, word_id, context):
        wids = torch.tensor([[word_id]], dtype=torch.long, device=context.device)
        with torch.no_grad():
            out = self.forward(wids, context.unsqueeze(0))
        return out['concept_embeddings'][0, 1, :]


class OnlineBPETokenizer:
    """
    Online Byte-Pair Encoding tokenizer that learns from experience.

    Philosophy: mirrors how humans acquire language.
      Stage 0  — pure character-level perception (baby babbling)
      Stage 1  — frequent character pairs merge into syllable-like units
      Stage 2  — frequent subword units merge into morpheme-like units
      Stage 3  — common morpheme sequences merge into whole words/phrases

    No corpus needed upfront. The agent starts perceiving individual
    characters and discovers structure purely from what it encounters.
    Every merge is learned, not prescribed.

    Token ID layout (fixed at construction, never resized):
      0          <PAD>
      1          <UNK>   (should become rare as vocab grows)
      2          <START>
      3          <END>
      4 .. 259   ASCII characters (the bedrock — always available)
      260 .. max learned merge tokens (subwords, morphemes, words)

    The transformer embedding table is pre-allocated to max_vocab_size.
    BPE grows into that space as merges are discovered. The model never
    needs to be rebuilt.
    """

    # ID constants
    PAD_ID   = 0
    UNK_ID   = 1
    START_ID = 2
    END_ID   = 3
    CHAR_OFFSET = 4          # ASCII chars start here
    MERGE_OFFSET = 260       # learned merges start here (4 + 256)

    def __init__(self, max_vocab_size: int = 4096,
                 merge_every_n: int = 50,
                 min_pair_freq: int = 3):
        """
        max_vocab_size : must match the transformer embedding size
        merge_every_n  : learn new merges every N texts processed
        min_pair_freq  : a pair must appear at least this many times to merge
        """
        self.max_vocab_size = max_vocab_size
        self.merge_every_n  = merge_every_n
        self.min_pair_freq  = min_pair_freq

        # id -> surface string
        self.id_to_token: Dict[int, str] = {
            self.PAD_ID:   '<PAD>',
            self.UNK_ID:   '<UNK>',
            self.START_ID: '<START>',
            self.END_ID:   '<END>',
        }
        # Fill in the 256 ASCII character tokens
        for i in range(256):
            ch = chr(i) if chr(i).isprintable() and chr(i) != ' ' else '<0x{:02x}>'.format(i)
            self.id_to_token[self.CHAR_OFFSET + i] = ch

        # surface string -> id  (reverse of above, built lazily)
        self.token_to_id: Dict[str, int] = {
            v: k for k, v in self.id_to_token.items()
        }

        self.next_merge_id = self.MERGE_OFFSET   # next slot for a learned merge

        # Merge rules: (left_id, right_id) -> merged_id
        self.merges: Dict[tuple, int] = {}
        # Inverse: merged_id -> (left_id, right_id)
        self.merge_expansion: Dict[int, tuple] = {}

        # Pair co-occurrence counts (for learning new merges)
        self._pair_counts: Dict[tuple, int] = defaultdict(int)
        self._texts_since_merge = 0

        # Word-level frequency (for progress display and novelty)
        self.word_counts: Dict[str, int] = defaultdict(int)

        # Backwards-compat: expose these like the old Vocabulary
        self.word_to_id = self.token_to_id   # same dict, alias
        self.next_id    = self.next_merge_id  # updated in _maybe_learn_merges

        log.debug(f"OnlineBPETokenizer: {len(self.id_to_token)} base tokens, "
                  f"space for {max_vocab_size - self.MERGE_OFFSET} learned merges")

    # ------------------------------------------------------------------ #
    #  TOKENISATION                                                        #
    # ------------------------------------------------------------------ #

    def tokenize(self, text: str) -> List[int]:
        """
        Convert text to a list of token IDs using current BPE rules.

        Process:
          1. Split text into words
          2. Each word -> character IDs
          3. Apply all learned merge rules (greedy left-to-right)
          4. Return flat list of IDs
        """
        if not text:
            return []
        tokens = []
        for word in re.sub(r'[^\w\s]', ' ', text.lower()).split():
            tokens.extend(self._encode_word(word))
        return tokens

    def _encode_word(self, word: str) -> List[int]:
        """Encode a single word using BPE."""
        # Start with character IDs
        ids = [self.CHAR_OFFSET + ord(c) if ord(c) < 256
               else self.UNK_ID
               for c in word]
        if not ids:
            return [self.UNK_ID]

        # Apply merges greedily left-to-right
        # Keep applying until no more merges fire
        changed = True
        while changed and len(ids) > 1:
            changed = False
            new_ids = []
            i = 0
            while i < len(ids):
                if i < len(ids) - 1:
                    pair = (ids[i], ids[i+1])
                    if pair in self.merges:
                        new_ids.append(self.merges[pair])
                        i += 2
                        changed = True
                        continue
                new_ids.append(ids[i])
                i += 1
            ids = new_ids

        return ids

    # ------------------------------------------------------------------ #
    #  OBSERVATION (training signal — call for every text seen)           #
    # ------------------------------------------------------------------ #

    def observe(self, text: str):
        """
        Record this text for BPE learning.
        Call every time the agent reads or hears something.
        Pair counts accumulate; merges are learned every merge_every_n calls.
        """
        if not text:
            return

        # Count word frequencies (for novelty_score and progress display)
        for word in re.sub(r'[^\w\s]', ' ', text.lower()).split():
            if len(word) >= 2:
                self.word_counts[word] += 1

        # Count adjacent token pairs in the current encoding
        tokens = self.tokenize(text)
        for i in range(len(tokens) - 1):
            pair = (tokens[i], tokens[i+1])
            self._pair_counts[pair] += 1

        self._texts_since_merge += 1
        if self._texts_since_merge >= self.merge_every_n:
            self._maybe_learn_merges()
            self._texts_since_merge = 0

    def _maybe_learn_merges(self, max_new: int = 5):
        """
        Learn up to max_new new merge rules from accumulated pair counts.
        Only pairs that exceed min_pair_freq and fit in the vocab are merged.
        This is called automatically by observe() — never call directly.
        """
        if self.next_merge_id >= self.max_vocab_size:
            return   # vocab full

        # Sort pairs by frequency, highest first
        candidates = sorted(
            ((freq, pair) for pair, freq in self._pair_counts.items()
             if freq >= self.min_pair_freq and pair not in self.merges),
            reverse=True
        )

        learned = 0
        for freq, pair in candidates:
            if learned >= max_new:
                break
            if self.next_merge_id >= self.max_vocab_size:
                break

            left_tok  = self.id_to_token.get(pair[0], '?')
            right_tok = self.id_to_token.get(pair[1], '?')
            merged    = left_tok + right_tok

            # Skip if this surface string already has a token
            if merged in self.token_to_id:
                continue

            mid = self.next_merge_id
            self.merges[pair]            = mid
            self.merge_expansion[mid]    = pair
            self.id_to_token[mid]        = merged
            self.token_to_id[merged]     = mid
            self.next_merge_id          += 1
            self.next_id                 = self.next_merge_id  # compat alias
            learned += 1

            log.debug(f"BPE merge: {left_tok!r}+{right_tok!r} -> {merged!r} "
                      f"(id={mid}, freq={freq})")

        if learned > 0:
            log.info(f"Learned {learned} BPE merges. "
                     f"Vocab size: {self.next_merge_id}/{self.max_vocab_size}")
            # Decay pair counts to let new patterns emerge over time
            for pair in self._pair_counts:
                self._pair_counts[pair] = int(self._pair_counts[pair] * 0.8)

    # ------------------------------------------------------------------ #
    #  DECODING                                                            #
    # ------------------------------------------------------------------ #

    def decode(self, ids: List[int]) -> str:
        """Convert token IDs back to text."""
        skip = {self.PAD_ID, self.UNK_ID, self.START_ID, self.END_ID}
        parts = []
        for tid in ids:
            if tid in skip:
                continue
            tok = self.id_to_token.get(tid, '?')
            parts.append(tok)
        # Join and clean up: subwords naturally concatenate,
        # add spaces between word-boundary tokens
        text = ''.join(parts)
        # Re-add spaces: insert space before uppercase-equivalent boundaries
        # (simple heuristic — good enough for generation output)
        return re.sub(r'([a-z])([A-Z])', r'\1 \2', text).strip()

    def decode_readable(self, ids: List[int]) -> str:
        """
        Decode to readable text with word spaces.
        Groups character-level tokens into words, separates merged tokens.
        """
        skip = {self.PAD_ID, self.UNK_ID, self.START_ID, self.END_ID}
        parts = []
        for tid in ids:
            if tid in skip:
                continue
            tok = self.id_to_token.get(tid, '')
            if not tok:
                continue
            # If this token is a whole word (contains no char-level fragments)
            # add a space before it
            if len(tok) > 1 and tok.isalpha() and tok in self.word_counts:
                parts.append(' ' + tok)
            else:
                parts.append(tok)
        return ''.join(parts).strip()

    # ------------------------------------------------------------------ #
    #  BACKWARDS-COMPAT INTERFACE (same as old Vocabulary)               #
    # ------------------------------------------------------------------ #

    def add_word(self, word: str) -> int:
        """
        Backwards-compat: add a word and return its token ID.
        With BPE this just calls observe() on the word — the tokeniser
        learns the structure itself rather than storing whole-word tokens.
        """
        word = word.lower().strip()
        if not word or len(word) < 2:
            return self.UNK_ID
        self.observe(word)
        # Return the first token ID of this word's encoding
        ids = self.tokenize(word)
        return ids[0] if ids else self.UNK_ID

    def get_id(self, word: str) -> int:
        """Return the first BPE token ID for a word (backwards compat)."""
        ids = self.tokenize(word)
        return ids[0] if ids else self.UNK_ID

    def get_word(self, wid: int) -> str:
        """Return the surface string for a token ID (backwards compat)."""
        return self.id_to_token.get(wid, '<UNK>')

    # ------------------------------------------------------------------ #
    #  INTROSPECTION                                                       #
    # ------------------------------------------------------------------ #

    @property
    def max_size(self) -> int:
        """Backwards compat: max_size used as the vocab_size for the model."""
        return self.max_vocab_size

    def vocab_size(self) -> int:
        return self.next_merge_id

    def num_merges(self) -> int:
        return len(self.merges)

    def most_common_tokens(self, n: int = 20) -> List[tuple]:
        """The n most common word-level surface forms seen."""
        return sorted(self.word_counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def show_merges(self, n: int = 10) -> List[str]:
        """Show the most recently learned merges (for debugging / introspection)."""
        result = []
        for mid in range(self.next_merge_id - 1,
                         max(self.MERGE_OFFSET - 1, self.next_merge_id - n - 1), -1):
            if mid in self.id_to_token:
                result.append(f"[{mid}] {self.id_to_token[mid]!r}")
        return result

    def state_dict(self) -> Dict:
        return {
            'merges':          list(self.merges.items()),
            'id_to_token':     dict(self.id_to_token),
            'next_merge_id':   self.next_merge_id,
            'word_counts':     dict(self.word_counts),
            'pair_counts':     dict(self._pair_counts),
        }

    def load_state_dict(self, state: Dict):
        self.id_to_token     = {int(k): v for k, v in state['id_to_token'].items()}
        self.token_to_id     = {v: k for k, v in self.id_to_token.items()}
        self.next_merge_id   = state['next_merge_id']
        self.next_id         = self.next_merge_id
        self.word_counts     = defaultdict(int, state['word_counts'])
        self._pair_counts    = defaultdict(int, {
            eval(str(k)): v for k, v in state['pair_counts'].items()
        })
        self.merges = {}
        self.merge_expansion = {}
        for pair_str, mid in state['merges']:
            pair = tuple(pair_str) if isinstance(pair_str, (list, tuple)) else eval(str(pair_str))
            self.merges[pair]         = mid
            self.merge_expansion[mid] = pair
        self.word_to_id = self.token_to_id


# Backwards-compat alias — old code that does Vocabulary(...) still works
class Vocabulary(OnlineBPETokenizer):
    """Backwards-compatible alias for OnlineBPETokenizer."""
    def __init__(self, max_size: int = 4096, **kwargs):
        super().__init__(max_vocab_size=max_size, **kwargs)
        # word_counts is in the parent; expose it for old code that reads it
        self.word_to_id = self.token_to_id


class ContextSchema:
    """
    Extracts a fixed-size float32 vector from any context dict.

    Instead of hardcoding key names, it tries priority-ordered alias lists
    for each semantic slot, accepts nested or flat dicts, and lets you register
    custom extractors at runtime so this works for Minecraft, robotics,
    simulations, or any domain without changing core code.

    Slot map (32 dimensions):
      0-3   visual   mean, std, max, min
      4     health / battery / charge / hp              (divided by 20)
      5     hunger / fuel / food_level / energy         (divided by 20)
      6     saturation / stability / balance            (divided by 20)
      7-9   x, y, z position                           (divided by 100)
      10-17 joy, fear, surprise, anger,
            trust, anticipation, sadness, disgust
      18-21 personality[:4]
      22-31 overflow  any remaining numeric scalars
    """

    CONTEXT_DIM = 32

    _SCALAR_SLOTS = [
        (4,  20.,  ['health',     'hp',         'battery',   'charge',   'vitality']),
        (5,  20.,  ['hunger',     'food_level', 'fuel',      'energy',   'stamina']),
        (6,  20.,  ['saturation', 'stability',  'balance',   'saturation_level']),
        (7,  100., ['x',          'pos_x',      'position_x','longitude']),
        (8,  100., ['y',          'pos_y',      'position_y','altitude', 'height']),
        (9,  100., ['z',          'pos_z',      'position_z','latitude']),
    ]

    _EMOTION_SLOTS = {
        10: ['joy',          'happiness',   'pleasure'],
        11: ['fear',         'threat',      'anxiety'],
        12: ['surprise',     'novelty',     'shock'],
        13: ['anger',        'aggression',  'rage'],
        14: ['trust',        'confidence',  'certainty'],
        15: ['anticipation', 'expectation', 'hope'],
        16: ['sadness',      'grief',       'loss'],
        17: ['disgust',      'aversion',    'repulsion'],
    }

    def __init__(self):
        self._custom = {}

    def register(self, slot, extractor):
        """
        Register a custom extractor for a slot index.
        extractor: callable(context_dict) -> float

        Examples:
            schema.register(5, lambda ctx: ctx.get('foodLevel', 20) / 20.0)
            schema.register(4, lambda ctx: ctx.get('voltage', 12) / 12.0)
            schema.register(7, lambda ctx: ctx.get('gps', {}).get('lng', 0) / 180.0)
        """
        self._custom[slot] = extractor

    def extract(self, context):
        """Extract a 32-d float32 vector from any context dict."""
        vec = np.zeros(self.CONTEXT_DIM, dtype=np.float32)

        visual = (context.get('visual') or context.get('frame')
                  or context.get('image') or context.get('obs_image'))
        if isinstance(visual, np.ndarray) and visual.size >= 4:
            vec[0] = float(np.mean(visual))
            vec[1] = float(np.std(visual))
            vec[2] = float(np.max(visual))
            vec[3] = float(np.min(visual))

        pos = context.get('position', {})
        if not isinstance(pos, dict):
            pos = {}

        for slot, divisor, aliases in self._SCALAR_SLOTS:
            if slot in self._custom:
                try:
                    vec[slot] = float(self._custom[slot](context))
                    continue
                except Exception:
                    pass
            for src in (context, pos):
                for alias in aliases:
                    v = src.get(alias)
                    if v is not None:
                        vec[slot] = float(v) / divisor
                        break
                if vec[slot] != 0.0:
                    break

        emotions = (context.get('emotions') or context.get('emotion_state')
                    or context.get('affect') or {})
        if not isinstance(emotions, dict):
            emotions = {}

        for slot, aliases in self._EMOTION_SLOTS.items():
            if slot in self._custom:
                try:
                    vec[slot] = float(self._custom[slot](context))
                    continue
                except Exception:
                    pass
            for alias in aliases:
                val = emotions.get(alias, context.get(alias))
                if val is not None:
                    vec[slot] = float(np.clip(val, -1.0, 1.0))
                    break

        pers = context.get('personality')
        if pers is not None:
            try:
                arr = pers.as_array()[:4]
                vec[18:18 + len(arr)] = arr
            except Exception:
                pass

        skip = {'visual', 'frame', 'image', 'obs_image', 'position',
                'emotions', 'emotion_state', 'affect', 'personality'}
        for _, _, aliases in self._SCALAR_SLOTS:
            skip.update(aliases)
        for aliases in self._EMOTION_SLOTS.values():
            skip.update(aliases)

        overflow = 22
        for key, val in context.items():
            if overflow >= self.CONTEXT_DIM:
                break
            if key in skip:
                continue
            if isinstance(val, (int, float, bool)):
                vec[overflow] = float(val)
                overflow += 1
            elif isinstance(val, np.ndarray) and val.ndim == 0:
                vec[overflow] = float(val)
                overflow += 1

        return vec


_default_schema = ContextSchema()



class ConversationBuffer:
    """
    Tracks the actual back-and-forth of a conversation with full structure.

    Separate from context_window (which just stores tokenized inputs for the
    transformer).  This is what gives the agent genuine conversational memory:
    who said what, in what order, and which utterance was a reply to which.

    Each turn is stored as:
        {
            'role':      'user' | 'agent',
            'text':      str,
            'tokens':    List[int],
            'timestamp': float,
            'reply_to':  int | None,   # index of the turn this replies to
            'emotions':  Dict[str, float],
            'topic_words': List[str],  # most content-bearing words in this turn
        }
    """

    def __init__(self, maxlen: int = 40):
        self._turns: List[Dict[str, Any]] = []
        self.maxlen = maxlen
        self._topic_history: deque = deque(maxlen=60)  # recent topic words (60 = ~10 turns)

    # ------------------------------------------------------------------ #

    def add(self, role: str, text: str, tokens: List[int],
            emotions: Dict[str, float] = None, reply_to: int = None):
        idx = len(self._turns)
        topic_words = self._extract_topic_words(text)
        self._turns.append({
            'idx':        idx,
            'role':       role,
            'text':       text,
            'tokens':     tokens,
            'timestamp':  time.time(),
            'reply_to':   reply_to,
            'emotions':   emotions or {},
            'topic_words': topic_words,
        })
        self._topic_history.extend(topic_words)
        # Trim if over capacity (keep the tail — most recent turns)
        if len(self._turns) > self.maxlen:
            self._turns = self._turns[-self.maxlen:]
        return idx

    def last_user_turn(self) -> Optional[Dict]:
        for t in reversed(self._turns):
            if t['role'] == 'user':
                return t
        return None

    def last_agent_turn(self) -> Optional[Dict]:
        for t in reversed(self._turns):
            if t['role'] == 'agent':
                return t
        return None

    def recent_turns(self, n: int = 6) -> List[Dict]:
        """Last n turns in chronological order."""
        return self._turns[-n:]

    def current_topics(self) -> List[str]:
        """Most recent topic words across the active conversation."""
        seen, result = set(), []
        for w in reversed(self._topic_history):
            if w not in seen:
                seen.add(w); result.append(w)
            if len(result) >= 8:
                break
        return result

    def conversation_seed_tokens(self, vocab, max_tokens: int = 12) -> List[int]:
        """
        Build a seed token sequence from recent turns for generation.
        Interleaves the last user utterance and last agent utterance so
        the model generates conditioned on the actual conversational context,
        not just the last 3 raw tokens.
        """
        seed = []
        recent = self.recent_turns(4)
        for turn in recent:
            seed.extend(turn['tokens'][-4:])  # last 4 tokens from each turn
        return seed[-max_tokens:] if seed else [vocab.get_id('<START>')]

    def is_active(self, timeout: float = 120.0) -> bool:
        """Is there an ongoing conversation (last turn within timeout seconds)?"""
        if not self._turns:
            return False
        return (time.time() - self._turns[-1]['timestamp']) < timeout

    def reset(self):
        """Clear the conversation — call when conversation ends."""
        self._turns.clear()
        self._topic_history.clear()

    def to_text_summary(self, n: int = 4) -> str:
        """Short text summary of recent turns for memory storage."""
        parts = []
        for t in self.recent_turns(n):
            prefix = 'You' if t['role'] == 'user' else 'Agent'
            parts.append(f"{prefix}: {t['text'][:80]}")
        return ' | '.join(parts)

    @staticmethod
    def _extract_topic_words(text: str) -> List[str]:
        """
        Extract content-bearing words — the actual subject matter of the text.
        Aggressively filters function words, common verbs, and short words so
        only semantically meaningful nouns/adjectives/domain terms survive.
        """
        STOPWORDS = {
            # articles / determiners
            'the','a','an','this','that','these','those','some','any','each',
            'every','both','few','more','most','other','such','same',
            # prepositions
            'in','on','at','to','of','for','with','from','into','onto',
            'upon','over','under','about','above','below','between','through',
            'during','before','after','since','until','while','within','without',
            # conjunctions
            'and','or','but','nor','so','yet','both','either','neither',
            'although','because','since','unless','when','where','while',
            # pronouns
            'i','me','my','myself','we','our','you','your','he','him','his',
            'she','her','they','them','their','it','its','who','whom','which',
            # common verbs (not content words in most contexts)
            'is','are','was','were','be','been','being','have','has','had',
            'do','does','did','will','would','could','should','may','might',
            'shall','must','need','dare','used','can','cannot',
            'get','got','go','went','come','came','take','took','make','made',
            'know','think','want','use','find','give','tell','seem','feel',
            'keep','let','put','say','see','try','ask','work','play','move',
            # common adverbs / connectives
            'then','than','also','just','only','very','too','well','even',
            'back','still','way','also','here','there','now','how','when',
            'much','many','down','then','usually','really','quite','often',
            # numbers as words
            'one','two','three','four','five','six','seven','eight','nine','ten',
        }
        words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
        # min length 5 catches more noise; numbers and short words rarely content-bearing
        return [w for w in words
                if len(w) >= 5 and w not in STOPWORDS and not w.isdigit()][:8]

    def __len__(self):
        return len(self._turns)


# ──────────────────────────────────────────────────────────────────────────────
# Epistemic scoring (Chat & Web GRPO plan §3.3 / §6)
# ──────────────────────────────────────────────────────────────────────────────
# v1 lexical-heuristic proxy, not semantic entailment. A from-scratch 256-dim
# transformer with a 4096-token BPE vocabulary cannot judge arbitrary factual
# claims — these heuristics are the same epistemic status as the RND/ICM
# curiosity bonuses already used elsewhere in this codebase: cheap, imperfect,
# directionally useful signals, not ground truth. Self-referential throughout:
# every signal below comes from the agent's OWN memory and (if attached) its
# own cached web pages — never an external grader.

_AGREEMENT_PHRASES = (
    "you're right", "youre right", "you are right", "totally agree",
    "i agree", "that's true", "thats true", "exactly", "absolutely",
    "100%", "for sure", "couldn't agree more", "couldnt agree more",
    "you make a good point", "great point", "so true",
)

_NEGATION_MARKERS = (
    "not ", "n't", "never", "no ", "isn't", "doesn't", "wasn't",
    "wrong", "false", "incorrect", "untrue", "disagree",
)


def _agreement_marker(text: str) -> bool:
    """Cheap lexical check: does this reply read as reflexive agreement?"""
    low = text.lower()
    return any(p in low for p in _AGREEMENT_PHRASES)


def _contradicts(candidate_text: str, evidence: List[Dict]) -> bool:
    """
    Lexical heuristic for "this reply pushes against the agent's own
    retrieved evidence" — NOT semantic entailment. A negation marker present
    in the candidate AND meaningful content-word overlap with the evidence
    text is treated as a (weak) contradiction signal. Two false-positive-
    prone checks combined are still better than either alone, but this will
    misfire on real text sometimes — see the plan's §6 notes on iterating
    past v1 lexical heuristics toward something more semantic.
    """
    low_candidate = candidate_text.lower()
    if not any(neg in low_candidate for neg in _NEGATION_MARKERS):
        return False
    evidence_words = set()
    for ev in evidence:
        t = ev.get('text', '') or ev.get('summary', '') or str(ev.get('payload', ''))
        evidence_words.update(re.findall(r'[a-z]{4,}', t.lower()))
    candidate_words = set(re.findall(r'[a-z]{4,}', low_candidate))
    return len(evidence_words & candidate_words) >= 2


def epistemic_reward(candidate_text: str, user_text: str, agent,
                     sycophancy_w: float = 0.1) -> float:
    """
    Self-referential epistemic scorer for one candidate reply.

    Reads only the agent's own memory and (if attached) its own cached web
    pages — no external grader, no ground-truth labels. Three components:

      r_consistency           — penalised if the candidate contradicts the
                                 agent's own retrieved evidence; small bonus
                                 just for being grounded in something at all
      r_evidence               — more retrieved evidence -> higher score,
                                 capped (diminishing returns)
      r_unjustified_agreement — penalised for reflexive agreement language
                                 with NO supporting evidence behind it at all;
                                 scaled by sycophancy_w (personality-derived
                                 anti-sycophancy pressure, shared with
                                 RewardSystem via sycophancy_weight())

    A conscientious/low-agreeableness "skeptic" agent (high sycophancy_w)
    gets penalised harder for unjustified agreement than a high-agreeableness
    one — same character-consistent design as RewardSystem.sycophancy_weight().
    """
    mem = getattr(agent, 'memory', None)
    if mem is None:
        return 0.0

    topic = ConversationBuffer._extract_topic_words(candidate_text)
    query = ' '.join(topic[:3])

    evidence: List[Dict] = []
    if query:
        try:
            evidence.extend(mem.search(query, limit=5))
        except Exception:
            pass
        web_browser = getattr(agent, 'web_browser', None)
        if web_browser is not None:
            try:
                evidence.extend(web_browser.search_cached_pages(query, limit=5))
            except Exception:
                pass

    grounded            = len(evidence) > 0
    agrees              = _agreement_marker(candidate_text)
    contradicts_memory  = _contradicts(candidate_text, evidence)

    r_consistency           = -0.5 if contradicts_memory else (0.1 if grounded else 0.0)
    r_evidence              = 0.15 * min(1.0, len(evidence) / 3.0)
    r_unjustified_agreement = -sycophancy_w * 4.0 if (agrees and not grounded) else 0.0

    return r_consistency + r_evidence + r_unjustified_agreement


class LanguageIntelligence:
    """
    Transformer-based language learning. Learns through experience.

    Works with any context shape via ContextSchema.  Minecraft, robotics,
    simulations — just register aliases or custom extractors on the schema
    instead of modifying this class.
    """

    def __init__(self, agent_ref=None, device=None, schema=None):
        self.agent  = agent_ref
        self.device = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))
        self.vocab  = OnlineBPETokenizer(
            max_vocab_size=4096,  # transformer embedding is pre-allocated to this
            merge_every_n=50,     # learn new subword merges every 50 texts
            min_pair_freq=3,      # min occurrences before merging
        )
        self.model  = MultimodalGroundingTransformer(
            concept_dim=256, context_dim=ContextSchema.CONTEXT_DIM,
            n_heads=4, n_layers=2,
            vocab_size=self.vocab.max_vocab_size).to(self.device)
        self.optimizer        = torch.optim.AdamW(self.model.parameters(), lr=3e-4)
        self.training_buffer  = deque(maxlen=1000)
        self.updates_done     = 0
        self.language_stage   = 0
        self.experience_count = 0
        self.last_speech_time = 0.0
        self.speech_cooldown  = 10.0
        self.context_window   = deque(maxlen=20)
        self.schema           = schema or _default_schema

        # --- Memory & Conversation ---
        # conversation_buffer tracks structured multi-turn dialogue
        self.conversation_buffer = ConversationBuffer(maxlen=40)
        # how many recent memories to pull into context per call
        self.memory_recall_n     = 5
        # how many relevant memories to retrieve via search
        self.memory_search_n     = 3

        # --- Familiarity / repeat-visitor tracking (Chat & Web GRPO plan) ---
        # Self-referential: this is the agent's own record of its own
        # conversations, keyed by whatever speaker_id the caller passes in
        # (a name/UUID — no external identity database). A "visit" is counted
        # once VISIT_GAP_SECONDS has passed since the same partner last
        # talked — reusing ConversationBuffer.is_active()'s own 120s active-
        # conversation threshold, so "still mid-conversation" and "a new
        # visit" share one consistent definition instead of two competing ones.
        self._partner_visit_counts: Dict[str, int]   = defaultdict(int)
        self._partner_last_seen:    Dict[str, float] = {}
        self.VISIT_GAP_SECONDS = 120.0

        # --- Chat-GRPO background training state (§3.4/§3.5 of the plan) ---
        self.grpo_cooldown      = 45.0   # min seconds between background passes
        self.grpo_turn_stride   = 4      # also require >= N turns since last pass
        self._last_grpo_time    = 0.0
        self._turns_since_grpo  = 0
        self._pending_grpo      = False  # true while a background task is in flight
        # Rolling history of epistemic scores from completed background passes,
        # used as the baseline for gating self-imitation training (step 6).
        self._epistemic_score_history: deque = deque(maxlen=50)
        self._last_epistemic_score: float    = 0.0

        log.info(f"LanguageIntelligence initialized on {self.device}")

    # ---------- core ----------

    def process_input(self, text, context, speaker_id: str = 'unknown'):
        """
        Process incoming text with full memory and conversation awareness.

        FIX: this method previously crashed unconditionally on its 4th line
        of work — `'timestamp': time()` called the `time` MODULE (imported
        via `import time`, not `from time import time`) as if it were the
        function. Every single call raised TypeError. The only reason this
        went unnoticed is that chat_loop() (the console chat path) wraps its
        call in a broad `except Exception: log.error(...)` that silently
        swallowed it every time, and the REST /chat endpoint (process_chat()
        in agent.py) never called this method at all — it called
        generate_speech() instead, a separate bug fixed alongside this one.
        Net effect: this method, and everything gated behind it (the
        ConversationBuffer, training_buffer, and now the Chat & Web GRPO
        design below) had never actually executed successfully in this
        codebase. Fixed at all 4 call sites (here and in the bulk
        text-learning method further down).

        speaker_id identifies who this exchange is with — a name/UUID the
        caller supplies (e.g. a stable per-browser visitor id from the web
        UI, or another agent's id for agent-to-agent chat). Purely for this
        agent's own self-referential bookkeeping (familiarity/visit
        tracking below); no external identity system is assumed or required,
        and 'unknown' is a safe default for any caller that doesn't have one.

        Flow:
          1. Retrieve relevant memories (episodic + semantic search)
          2. Build memory-enriched context vector
          3. Record turn in conversation buffer
          3b. Update familiarity/visit tracking for speaker_id
          4. Train transformer on this exchange
          5. Generate reply seeded from conversational history
          6. Store exchange in agent memory
          6b. Self-imitation training, gated by the rolling epistemic-score
              baseline (Chat & Web GRPO plan §3.x)
          7. Fire brain reward event (now carries partner_id/
             partner_visit_count for RewardSystem's familiarity term)
          8. Schedule a fire-and-forget background GRPO pass — never adds
             latency to the reply the user actually sees
        """
        if not text or not text.strip(): return ""
        text = text.strip()

        # 1. Retrieve relevant memories before building context
        recalled    = self._recall_relevant(text)
        enriched_ctx = self._enrich_context(context, recalled)
        cv           = self._ctx_vec(enriched_ctx)
        toks         = self.vocab.tokenize(text)

        # 2. Record this user turn in the conversation buffer
        emotions = {}
        if self.agent and hasattr(self.agent, 'emotion'):
            emotions = self.agent.emotion.snapshot()
        last_agent = self.conversation_buffer.last_agent_turn()
        reply_to   = last_agent['idx'] if last_agent else None
        user_idx   = self.conversation_buffer.add(
            role='user', text=text, tokens=toks,
            emotions=emotions, reply_to=reply_to)

        # 3b. Familiarity / visit tracking (Chat & Web GRPO plan — extraversion
        # reward fix). A "visit" is counted once VISIT_GAP_SECONDS has passed
        # since this exact speaker_id last talked — same threshold
        # ConversationBuffer.is_active() uses, so "mid-conversation" and "a
        # new visit" share one definition. Pure self-bookkeeping: this agent's
        # own record of its own conversation history, nothing external.
        now_ts = time.time()
        last_seen = self._partner_last_seen.get(speaker_id)
        if last_seen is None or (now_ts - last_seen) > self.VISIT_GAP_SECONDS:
            self._partner_visit_counts[speaker_id] += 1
        self._partner_last_seen[speaker_id] = now_ts
        partner_visit_count = self._partner_visit_counts[speaker_id]

        # 3. Observe text — BPE tokenizer learns subword structure from full text
        #    observe() counts adjacent token pairs across word boundaries,
        #    which is what drives the BPE merge learning.
        self.vocab.observe(text)

        # 4. Add to training buffer and train
        self.training_buffer.append({
            'tokens': toks, 'context': cv.cpu().numpy(),
            'text': text, 'timestamp': time.time()})
        if len(self.training_buffer) >= 8: self._train_step()
        self.experience_count += 1
        self._update_stage()

        # Keep the raw context_window for backwards compat
        self.context_window.append({'text': text, 'tokens': toks,
                                    'context': cv.cpu().numpy(),
                                    'timestamp': time.time()})

        # 5. Generate reply — seeded from conversation history, not just raw tokens
        seed_tokens = self.conversation_buffer.conversation_seed_tokens(
            self.vocab, max_tokens=12)
        resp = self._generate(seed_tokens, cv, enriched_ctx)

        # 6. If we got a response, record it too
        if resp and len(resp.strip()) > 0:
            resp_toks = self.vocab.tokenize(resp)
            self.conversation_buffer.add(
                role='agent', text=resp, tokens=resp_toks,
                emotions=emotions, reply_to=user_idx)
            # FIX (Chat & Web GRPO plan): previously trained on the agent's own
            # output unconditionally — pure self-imitation with no check on
            # whether that output was any good, which is exactly the kind of
            # loop that entrenches sycophantic/low-substance replies once the
            # model starts producing them, since it then keeps re-training on
            # its own mediocrity. Gated by the rolling epistemic-score
            # baseline from completed background GRPO passes (§3.x): if the
            # agent's last evaluated batch scored at or above its own
            # historical average, keep self-imitating; otherwise skip this
            # training append. Self-referential — gates against the agent's
            # own trend, not an external grader. First-ever exchange (empty
            # history) falls through to baseline=0.0 and trains normally.
            baseline = (sum(self._epistemic_score_history) / len(self._epistemic_score_history)
                       if self._epistemic_score_history else 0.0)
            if self._last_epistemic_score >= baseline:
                resp_cv = self._ctx_vec(self._agent_context())
                self.training_buffer.append({
                    'tokens': resp_toks, 'context': resp_cv.cpu().numpy(),
                    'text': resp, 'timestamp': time.time()})

        # 7. Store exchange in agent memory
        self._store_exchange_in_memory(text, resp, recalled, context, speaker_id=speaker_id)

        # 8. Fire brain reward event
        if self.agent and hasattr(self.agent, 'brain'):
            try:
                event = {'type': 'language_input', 'tags': ['language', 'chat',
                          'conversation' if self.conversation_buffer.is_active() else 'monologue'],
                         'payload': {
                             'text': text, 'words': len(toks),
                             'stage': self.language_stage,
                             'vocab_size': self.vocab.next_id,
                             'memories_recalled': len(recalled),
                             'conversation_len': len(self.conversation_buffer),
                             # FIX: feeds RewardSystem's new familiarity_r term
                             # (extraversion reward fix) — was previously absent,
                             # so extraversion had no reward signal to scale.
                             'partner_id':           speaker_id,
                             'partner_visit_count':   partner_visit_count,
                         }}
                reward, emo = self.agent.brain.evaluate_event(event, context)
                if hasattr(self.agent, 'emotion'):
                    for k, v in emo.items(): self.agent.emotion.add(k, v)
            except Exception as e:
                log.warning(f"Brain event from language failed: {e}")

        # 9. Schedule a fire-and-forget background GRPO pass (Chat & Web GRPO
        # plan §3.4/§3.5). Always scheduled AFTER `resp` is already finalized
        # above, so this can never add latency to what the user actually
        # sees — it runs as a separate asyncio task on whatever event loop is
        # currently running (works the same whether process_input() was
        # called from the REST /chat handler or the console chat_loop(), both
        # of which are themselves async and already have a running loop).
        if self.should_grpo_chat():
            try:
                import asyncio
                asyncio.create_task(
                    self._background_grpo_step(text, enriched_ctx, cv)
                )
                self._pending_grpo     = True
                self._last_grpo_time   = time.time()
                self._turns_since_grpo = 0
            except RuntimeError:
                # No running event loop (e.g. called from fully sync test code)
                # — skip silently rather than crash the live reply path.
                log.debug("should_grpo_chat() fired but no running event loop; skipped")
        else:
            self._turns_since_grpo += 1

        return resp

    # backwards-compat alias
    process_language_input = process_input

    # ------------------------------------------------------------------ #
    #  CHAT & WEB GRPO (epistemic background training)                     #
    # ------------------------------------------------------------------ #

    def should_grpo_chat(self) -> bool:
        """
        Gate for scheduling a background GRPO pass after a live reply.

        Mirrors should_browse()'s existing convention (urgency > 0.70) for
        consistency, but the actual conditions here are specific to chat:
          - conversation must currently be active (is_active(), the same
            120s threshold familiarity tracking reuses) — no point
            background-training against a one-off monologue line.
          - cooldown: at least grpo_cooldown seconds since the last pass.
          - stride: at least grpo_turn_stride turns since the last pass —
            cooldown alone could still fire every reply in a fast back-and-
            forth; the turn count is the harder floor.
          - not already running a pass (_pending_grpo).
        """
        if not self.conversation_buffer.is_active():
            return False
        if self._pending_grpo:
            return False
        if (time.time() - self._last_grpo_time) < self.grpo_cooldown:
            return False
        if self._turns_since_grpo < self.grpo_turn_stride:
            return False
        return True

    def _sycophancy_weight(self) -> float:
        """
        Thin wrapper around reward_system.sycophancy_weight() so this class
        and RewardSystem compute the exact same trait→weight mapping from
        one shared formula instead of two that could silently drift apart.
        """
        try:
            from ai_core.reward_system import sycophancy_weight
            traits = {}
            if self.agent is not None and hasattr(self.agent, 'personality'):
                traits = self.agent.personality.traits
            return sycophancy_weight(traits)
        except Exception:
            return 0.1   # safe low-pressure default if personality unavailable

    async def _background_grpo_step(self, user_text: str, enriched_ctx: Dict, cv) -> None:
        """
        Sample K candidate replies to the SAME exchange that already got a
        live reply, score each with epistemic_reward() (self-referential —
        reads only this agent's own memory/web cache, no external grader),
        apply a GRPO update, and record the result for the self-imitation
        gate in process_input() step 6.

        Runs entirely after the live reply was already returned — pure
        background cost, zero added latency. Errors are caught and logged,
        never allowed to crash the cognitive loop or a future request.
        """
        try:
            K = 4
            candidates = []
            seed_tokens = self.conversation_buffer.conversation_seed_tokens(
                self.vocab, max_tokens=12)
            for _ in range(K):
                txt = self._generate(seed_tokens, cv, enriched_ctx)
                if txt and txt.strip():
                    candidates.append(txt.strip())

            if len(candidates) < 2:
                self._pending_grpo = False
                return   # not enough diversity to do relative scoring

            agent = self.agent
            scores = [epistemic_reward(c, user_text, agent, self._sycophancy_weight())
                     for c in candidates]

            # ── GRPO-style update: gradient-enabled replay of each candidate
            # through self.model, weighted by its relative (baseline-
            # subtracted) advantage. Reuses self.optimizer — no second
            # optimizer is created over the same parameters.
            baseline   = sum(scores) / len(scores)
            advantages = [s - baseline for s in scores]
            std        = (sum(a*a for a in advantages) / len(advantages)) ** 0.5 + 1e-8
            advantages = [a / std for a in advantages]

            total_loss = None
            for cand_text, adv in zip(candidates, advantages):
                cand_toks = self.vocab.tokenize(cand_text)
                if len(cand_toks) < 2:
                    continue   # need at least 2 tokens for a shifted target
                # FIX: mirror _train_step()'s exact input/target construction —
                # tgt is the SHIFTED token sequence (predict token t+1 from
                # tokens up to t), not the same tokens fed back at themselves.
                # An earlier draft scored each candidate against its own
                # un-shifted tokens, which collapses to "how confident is the
                # model in literally the input it was just given" rather than
                # an actual generation log-prob.
                tin  = cand_toks[:-1]
                tgt  = cand_toks[1:]
                tids = torch.tensor([tin], dtype=torch.long, device=self.device)
                tgts = torch.tensor([tgt], dtype=torch.long, device=self.device)
                ctxs = cv.unsqueeze(0) if cv.dim() == 1 else cv
                # FIX: self.model() returns a dict ({'word_logits':...,
                # 'predicted_context':...}), confirmed against _train_step()'s
                # own usage — an earlier draft unpacked it as a 2-tuple, which
                # would have raised on the very first background pass.
                out = self.model(tids, ctxs)
                word_logits = out['word_logits']
                logp = -nn.functional.cross_entropy(
                    word_logits.reshape(-1, self.vocab.max_vocab_size),
                    tgts.reshape(-1), ignore_index=0, reduction='mean'
                )
                term = -adv * logp   # push log-prob mass toward above-baseline replies
                total_loss = term if total_loss is None else total_loss + term

            if total_loss is not None:
                self.optimizer.zero_grad()
                total_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                self.updates_done += 1

            # ── Record outcome for process_input()'s self-imitation gate ──
            mean_score = sum(scores) / len(scores)
            self._last_epistemic_score = mean_score
            self._epistemic_score_history.append(mean_score)

            log.debug(
                f"[chat-GRPO] {len(candidates)} candidates, "
                f"mean_score={mean_score:.4f}, best={max(scores):.4f}"
            )

        except Exception as e:
            log.warning(f"Background chat-GRPO step failed (non-fatal): {e}")
        finally:
            self._pending_grpo = False

    # ------------------------------------------------------------------ #
    #  MEMORY INTEGRATION                                                  #
    # ------------------------------------------------------------------ #

    def _get_memory(self):
        """
        Safely retrieve the agent's memory store.
        Handles the case where agent has no memory yet (graceful degradation).
        """
        if self.agent is None:
            return None
        mem = getattr(self.agent, 'memory', None)
        if mem is None:
            # Some agents attach memory directly to brain
            brain = getattr(self.agent, 'brain', None)
            mem   = getattr(brain, 'memory', None)
        return mem

    def _recall_relevant(self, text: str) -> List[Dict]:
        """
        Retrieve memories relevant to the current input text.

        Two strategies combined:
          a) Recent memories (temporal context — what just happened)
          b) Semantic search (topical context — what relates to this topic)

        Returns a list of memory event dicts, most relevant first.
        """
        mem = self._get_memory()
        if mem is None:
            return []

        results = []
        seen_texts = set()

        try:
            # a) Most recent events (always relevant — temporal continuity)
            recent = mem.recall(n=self.memory_recall_n)
            for ev in reversed(recent):  # most recent first
                t = ev.get('text', str(ev.get('payload', '')))[:200]
                if t and t not in seen_texts:
                    seen_texts.add(t)
                    results.append(ev)

            # b) Semantic search — find memories that mention similar words
            # Extract the most content-bearing words from the input
            topic_words = ConversationBuffer._extract_topic_words(text)
            # Also include current conversation topics for continuity
            topic_words += self.conversation_buffer.current_topics()[:3]

            for word in topic_words[:4]:  # top 4 topic words
                if len(word) < 4:
                    continue
                found = mem.search(word, limit=self.memory_search_n)
                for ev in found:
                    t = ev.get('text', str(ev.get('payload', '')))[:200]
                    if t and t not in seen_texts:
                        seen_texts.add(t)
                        results.append(ev)
                    if len(results) >= self.memory_recall_n + self.memory_search_n:
                        break

        except Exception as e:
            log.debug(f"Memory recall failed: {e}")

        return results[:self.memory_recall_n + self.memory_search_n]

    def _enrich_context(self, context: Dict, recalled: List[Dict]) -> Dict:
        """
        Merge retrieved memories into the context dict so ContextSchema
        can pack them into the overflow slots of the context vector.

        We encode memories as:
          - memory_novelty: how novel the current input is vs memory
          - memory_recency: time since most recent relevant memory
          - memory_count:   how many relevant memories were found
          - memory_emotion_*: aggregated emotional tone of recalled memories
          - conversation_len: turns in current conversation
          - conversation_active: 1.0 if in active conversation else 0.0
          - topic_overlap: fraction of current topics seen in memory

        These land in the overflow slots (22-31) of the 32-d context vector,
        giving the transformer real signal about the agent's memory state.
        """
        enriched = dict(context)

        if not recalled:
            enriched['memory_count']    = 0.0
            enriched['memory_novelty']  = 1.0
            enriched['memory_recency']  = 1.0
            enriched['conversation_len']     = float(len(self.conversation_buffer))
            enriched['conversation_active']  = 1.0 if self.conversation_buffer.is_active() else 0.0
            return enriched

        now = time.time()

        # How many memories found (normalised)
        enriched['memory_count'] = min(1.0, len(recalled) / 10.0)

        # Recency of most recent relevant memory (1.0 = just now, 0.0 = long ago)
        timestamps = [ev.get('timestamp', 0) for ev in recalled if ev.get('timestamp')]
        if timestamps:
            most_recent = max(timestamps)
            age         = now - most_recent
            enriched['memory_recency'] = float(np.exp(-age / 300.0))  # half-life 5 min
        else:
            enriched['memory_recency'] = 0.0

        # Aggregate emotional tone from recalled memories
        agg_emotions: Dict[str, float] = defaultdict(float)
        count = 0
        for ev in recalled:
            emos = ev.get('emotions', {})
            if isinstance(emos, dict):
                for k, v in emos.items():
                    agg_emotions[k] += v
                count += 1
        if count > 0:
            for k in agg_emotions:
                agg_emotions[k] /= count
            enriched['memory_emotion_joy']  = float(agg_emotions.get('joy',  0))
            enriched['memory_emotion_fear'] = float(agg_emotions.get('fear', 0))

        # Conversation state
        enriched['conversation_len']    = min(1.0, len(self.conversation_buffer) / 20.0)
        enriched['conversation_active'] = 1.0 if self.conversation_buffer.is_active() else 0.0

        # Topic overlap: fraction of current topics that appear in recalled texts
        current_topics = set(self.conversation_buffer.current_topics())
        if current_topics:
            recalled_text  = ' '.join(
                ev.get('text', '') for ev in recalled).lower()
            overlap = sum(1 for t in current_topics if t in recalled_text)
            enriched['topic_overlap'] = float(overlap) / len(current_topics)
        else:
            enriched['topic_overlap'] = 0.0

        return enriched

    def _store_exchange_in_memory(self, user_text: str, agent_text: str,
                                    recalled: List[Dict], context: Dict,
                                    speaker_id: Optional[str] = None):
        """
        Store the exchange in the agent's memory so it can be recalled later.
        Tagged for easy retrieval: 'language', 'chat', 'conversation', and —
        when this is a real two-way exchange, not autonomous monologue — a
        'partner:{speaker_id}' tag.

        FIX (familiarity persistence gap, raised directly: "what about
        conversations that refer to old memories which are in ScyllaDB and
        not in the memory deque"): this is the actual method that reaches
        UnifiedMemoryStore.remember() -> ScyllaMemoryBackend.save_event(),
        i.e. real persistent storage, not just the capped in-RAM cache. The
        partner: tag is what makes a SPECIFIC partner's full conversation
        history queryable straight from ScyllaDB later via query_by_tags()
        — including everything that's aged out of the 10000-event in-memory
        deque — without requiring every chat message to pay a synchronous
        ScyllaDB round-trip cost on the live reply path. The fast in-RAM
        _partner_visit_counts dict (persisted across restarts via
        state_dict()/load_state_dict() above) stays the source of truth for
        moment-to-moment reward shaping; this tag is what keeps the FULL
        ground-truth history recoverable on top of that, the same
        fast-signal/full-fidelity-store split the rest of this memory
        architecture already uses elsewhere.
        """
        mem = self._get_memory()
        if mem is None:
            return
        try:
            emotions = {}
            if self.agent and hasattr(self.agent, 'emotion'):
                emotions = self.agent.emotion.snapshot()

            tags = ['language', 'chat', 'conversation']
            if speaker_id:
                tags.append(f'partner:{speaker_id}')

            mem.remember({
                'type':      'conversation_exchange',
                'text':       user_text,
                'response':   agent_text,
                'timestamp':  time.time(),
                'emotions':   emotions,
                'topic_words': ConversationBuffer._extract_topic_words(user_text),
                'memories_used': len(recalled),
                'conversation_turn': len(self.conversation_buffer),
                'language_stage': self.language_stage,
                'partner_id': speaker_id,
            }, tags=tags)
        except Exception as e:
            log.debug(f"Failed to store exchange in memory: {e}")

    def _train_step(self):
        if len(self.training_buffer) < 4: return
        batch   = list(self.training_buffer)[-8:]
        max_len = max(len(e['tokens']) for e in batch)
        if max_len == 0: return
        tids, ctxs, tgts = [], [], []
        for e in batch:
            t = (e['tokens'] + [0]*max_len)[:max_len]
            tids.append(t); ctxs.append(e['context'])
            tgts.append((t[1:] + [0])[:max_len])
        tids = torch.tensor(tids, dtype=torch.long,    device=self.device)
        ctxs = torch.tensor(np.array(ctxs), dtype=torch.float32, device=self.device)
        tgts = torch.tensor(tgts, dtype=torch.long,    device=self.device)
        self.model.train()
        out = self.model(tids, ctxs)
        wl  = nn.functional.cross_entropy(
            out['word_logits'].reshape(-1, self.vocab.max_vocab_size),
            tgts.reshape(-1), ignore_index=0)
        cl  = nn.functional.mse_loss(out['predicted_context'], ctxs)
        loss = wl + 0.5*cl
        self.optimizer.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step(); self.updates_done += 1
        if self.updates_done % 10 == 0:
            log.info(f"Lang update {self.updates_done}: wl={wl.item():.4f} cl={cl.item():.4f}")


    def _agent_context(self):
        """
        Build a context dict from whatever the agent currently exposes.
        Works even if attributes are missing — defaults to neutral values.
        The schema handles all key-name normalisation downstream.
        """
        ctx = {}
        if not self.agent:
            return ctx
        # Standard agent attributes — grab anything that exists
        for key in ('health', 'hunger', 'saturation', 'position',
                    'visual', 'audio', 'inventory'):
            val = getattr(self.agent, key, None)
            if val is not None:
                ctx[key] = val
        # Emotions
        if hasattr(self.agent, 'emotion'):
            ctx['emotions'] = self.agent.emotion.snapshot()
        # Personality (schema will call as_array on it)
        if hasattr(self.agent, 'personality'):
            ctx['personality'] = self.agent.personality
        return ctx

    def _ctx_vec(self, ctx):
        """
        Build the context vector via ContextSchema.
        Attach personality from agent if not already in context.
        """
        # Let the schema know where to find personality if not in ctx
        if self.agent and hasattr(self.agent, 'personality'):
            if 'personality' not in ctx:
                ctx = dict(ctx)
                ctx['personality'] = self.agent.personality
        arr = self.schema.extract(ctx)
        return torch.tensor(arr, dtype=torch.float32, device=self.device)

    def _update_stage(self):
        v, e = self.vocab.next_id, self.experience_count
        new  = self.language_stage
        if e >= 5   and v >= 15:  new = max(new, 1)
        if e >= 50  and v >= 50:  new = max(new, 2)
        if e >= 200 and v >= 200: new = max(new, 3)
        if new != self.language_stage:
            log.info(f"Language stage: {self.language_stage} -> {new}")
            self.language_stage = new

    def _generate(self, input_tokens, ctx_vec, context):
        if self.language_stage == 0: return ""
        self.model.eval()
        with torch.no_grad():
            seed = torch.tensor([input_tokens[-3:] or [2]],
                                dtype=torch.long, device=self.device)
            generated = []
            T = 0.8 if self.language_stage >= 2 else 1.2
            for _ in range(10):
                out  = self.model(seed, ctx_vec.unsqueeze(0))
                p    = torch.softmax(out['word_logits'][0,-1,:] / T, dim=0)
                tok  = torch.multinomial(p, 1).item()
                if tok in (0, 3): break
                generated.append(tok)
                seed = torch.cat([seed[:,-2:],
                    torch.tensor([[tok]], dtype=torch.long, device=self.device)], dim=1)
        return self.vocab.decode(generated) if generated else ""

    # ---------- speech ----------

    def should_speak(self):
        if self.language_stage < 1: return False
        if time.time() - self.last_speech_time < self.speech_cooldown: return False
        if not self.agent: return False
        if any(abs(v)>0.6 for v in self.agent.emotion.snapshot().values()): return True
        soc = getattr(self.agent.personality, 'traits', {}).get('sociability', 0.0)
        return np.random.rand() < (soc+1)/40

    def generate_speech(self, context):
        """
        Generate autonomous speech enriched with memory and conversation state.
        If a conversation is active, generates a contextually coherent continuation.
        If not, generates from recent memories as seed — making speech feel grounded
        in what the agent has actually experienced.
        """
        self.last_speech_time = time.time()
        if self.language_stage == 0: return None

        # Pull relevant memories to enrich context
        # For autonomous speech, use current conversation topics as query
        query = ' '.join(self.conversation_buffer.current_topics()[:3]) or 'recent experience'
        recalled     = self._recall_relevant(query)
        enriched_ctx = self._enrich_context(context, recalled)
        cv           = self._ctx_vec(enriched_ctx)

        if self.conversation_buffer.is_active():
            # In a conversation — generate from conversational history seed
            seed = self.conversation_buffer.conversation_seed_tokens(
                self.vocab, max_tokens=12)
        elif recalled:
            # Not in conversation — seed from most relevant recent memory
            mem_text = recalled[0].get('text', '')
            seed     = self.vocab.tokenize(mem_text)[-6:] or [self.vocab.get_id('<START>')]
        else:
            # Cold start — seed from most recent context window entry
            seed = (list(self.context_window)[-1]['tokens'][-3:]
                    if self.context_window else [self.vocab.get_id('<START>')])

        r = self._generate(seed, cv, enriched_ctx)
        if r and len(r) > 2:
            # Store autonomous speech in memory too
            self._store_exchange_in_memory('', r, recalled, context)
            return r
        return None

    # ---------- file learning ----------

    def learn_from_file(self, file_path, filetype='text/plain'):
        path = Path(file_path)
        if not path.exists(): return f"File not found: {file_path}"
        try:
            if filetype.startswith('text/') or path.suffix in ('.txt','.md'):
                return self._learn_text(path)
            return f"Unsupported: {filetype}"
        except Exception as e:
            return f"Error: {e}"

    def _learn_text(self, path):
        try: text = path.read_text(encoding='utf-8', errors='ignore')
        except Exception: return f"Failed to read: {path.name}"
        # Build context from whatever the agent currently knows about itself
        # _ctx_vec + schema handles all the key-name mapping
        ctx = self._agent_context()
        cv = self._ctx_vec(ctx)
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        words = 0
        for sent in sentences[:100]:
            self.training_buffer.append({'tokens': self.vocab.tokenize(sent),
                                         'context': cv.cpu().numpy(),
                                         'text': sent, 'timestamp': time.time()})
            self.vocab.observe(sent)
            words += len(sent.split())
            self.experience_count += 1
        for _ in range(10):
            if len(self.training_buffer) >= 8: self._train_step()
        self._update_stage()
        return (f"Learned: {words} words, {len(sentences)} sentences. "
                f"Stage={self.language_stage}, Vocab={self.vocab.next_id}")

    # ---------- progress & persistence ----------

    def get_language_progress(self):
        names = ['pre-linguistic','proto-language','linguistic','advanced']
        return {
            'stage': self.language_stage,
            'stage_name': names[self.language_stage],
            'vocabulary_size': self.vocab.next_merge_id,
            'bpe_merges_learned': self.vocab.num_merges(),
            'recent_merges': self.vocab.show_merges(5),
            'experience_count': self.experience_count,
            'updates_done': self.updates_done,
            'context_window_size': len(self.context_window),
            'training_buffer_size': len(self.training_buffer),
            'most_frequent_tokens': self.vocab.most_common_tokens(20),
        }

    def state_dict(self):
        return {'model': self.model.state_dict(),
                'optimizer': self.optimizer.state_dict(),
                'vocab_bpe_state': self.vocab.state_dict(),
                'vocab_next_id': self.vocab.next_merge_id,
                'language_stage': self.language_stage,
                'experience_count': self.experience_count,
                'updates_done': self.updates_done,
                'conversation_turns': self.conversation_buffer._turns[-20:],
                # FIX: brain_capsule sidecar JSON reads these keys for the
                # human-readable summary.  Without them it always shows 0.
                'vocabulary_size': len(self.vocab.id_to_token),
                'pattern_count': self.experience_count,
                # FIX (familiarity persistence gap): _partner_visit_counts/
                # _partner_last_seen were pure in-RAM state with no save path
                # at all — every agent restart silently reset every returning
                # visitor back to "visit #1", even though the underlying
                # conversation history itself survives fine (in ScyllaDB, via
                # UnifiedMemoryStore — see process_input()'s partner: tag).
                # Bounded by distinct partner identities (realistically dozens,
                # not message count), so no truncation needed unlike
                # conversation_turns above.
                'partner_visit_counts': dict(self._partner_visit_counts),
                'partner_last_seen':    dict(self._partner_last_seen)}

    def load_state_dict(self, state):
        self.model.load_state_dict(state['model'])
        self.optimizer.load_state_dict(state['optimizer'])
        if 'vocab_bpe_state' in state:
            self.vocab.load_state_dict(state['vocab_bpe_state'])
        elif 'vocab_word_to_id' in state:
            # migrate from old word-level vocabulary format
            # treat each old word as a text to observe, rebuilding BPE from scratch
            log.info("Migrating old word-level vocabulary to BPE...")
            for word in state['vocab_word_to_id']:
                if word not in ('<PAD>','<UNK>','<START>','<END>'):
                    count = state.get('vocab_counts', {}).get(word, 1)
                    for _ in range(min(count, 5)):
                        self.vocab.observe(word)
        self.language_stage     = state['language_stage']
        self.experience_count   = state['experience_count']
        self.updates_done       = state['updates_done']
        # Restore conversation continuity across saves
        if 'conversation_turns' in state:
            self.conversation_buffer._turns = state['conversation_turns']
        # FIX (familiarity persistence gap): restore partner visit history so
        # a returning visitor is still recognised after an agent restart.
        if 'partner_visit_counts' in state:
            self._partner_visit_counts = defaultdict(int, state['partner_visit_counts'])
        if 'partner_last_seen' in state:
            self._partner_last_seen = dict(state['partner_last_seen'])
        log.info("Language state loaded")


def add_language_to_brain(brain_instance):
    lang = LanguageIntelligence(agent_ref=brain_instance.agent)
    brain_instance.language              = lang
    brain_instance.process_language_input = lang.process_input
    brain_instance.should_speak           = lang.should_speak
    brain_instance.generate_speech        = lang.generate_speech
    brain_instance.learn_from_file        = lang.learn_from_file
    brain_instance.get_language_progress  = lang.get_language_progress
    log.info("Language capabilities added to BrainCore")