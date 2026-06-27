// src/main/java/com/divineworld/oracle/LLMOracleBrain.java
// DivineWorld server mod
package com.divineworld.oracle;

import com.divineworld.DWMod;
import net.minecraft.server.MinecraftServer;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/**
 * FIXED LLM Oracle Brain - Enhanced error handling and logging
 */
public class LLMOracleBrain {

    private String modelName;
    private String endpoint;
    private final boolean isSecondOracle;
    private double temperature;
    private int contextTokens;

    // FIX (plan-creaking-geckolib-and-oracle-teach.md, Part 4, step 1):
    // gates the teaching loop so the Oracle never starts (or continues)
    // teaching while it's mid-generation answering a direct question, and
    // vice versa — both would otherwise compete for the same Ollama
    // backend. Lives HERE rather than on OracleSystem because OracleSystem
    // is not the only caller: OracleCommandRegistrar.java also calls
    // oracleBrain.queryAsync() directly (the /oracle ask-style command),
    // and any future caller holding a reference to this same LLMOracleBrain
    // instance needs to see the same state. Managed automatically inside
    // queryAsync()/query() below rather than by each call site manually —
    // every existing AND future caller is covered for free, with no risk of
    // a call site forgetting to wrap itself.
    private final AtomicBoolean busy = new AtomicBoolean(false);

    public boolean isBusy() {
        return busy.get();
    }

    public LLMOracleBrain(String modelName, String endpoint, boolean isSecondOracle) {
        this.modelName = modelName;
        this.endpoint = endpoint;
        this.isSecondOracle = isSecondOracle;
        this.temperature = 0.4;
        this.contextTokens = 2048;

        DWMod.LOGGER.info("[LLMOracleBrain] Initialized - Model: {}, Endpoint: {}", modelName, endpoint);
    }

    public boolean isSecondOracle() {
        return isSecondOracle;
    }

    public String getModelName() {
        return modelName;
    }

    public void switchModel(String newModel, String newEndpoint) {
        this.modelName = newModel;
        this.endpoint = newEndpoint;
        DWMod.LOGGER.info("[LLMOracleBrain] Switched to model: {}, endpoint: {}", newModel, newEndpoint);
    }

    public void setTemperature(double temperature) {
        this.temperature = temperature;
    }

    public void setContextTokens(int tokens) {
        this.contextTokens = tokens;
    }

    /**
     * FIXED Async query - with proper error handling and timeout
     */
    public void queryAsync(
            MinecraftServer server,
            String prompt,
            Consumer<String> callback
    ) {
        DWMod.LOGGER.info("[LLMOracleBrain] ======================================");
        DWMod.LOGGER.info("[LLMOracleBrain] Starting query");
        DWMod.LOGGER.info("[LLMOracleBrain] Model: {}", modelName);
        DWMod.LOGGER.info("[LLMOracleBrain] Prompt length: {} chars", prompt.length());
        DWMod.LOGGER.info("[LLMOracleBrain] ======================================");

        // Pre-flight checks
        if (!OllamaManager.isInitialized()) {
            DWMod.LOGGER.error("[LLMOracleBrain] FAILED: Ollama not initialized");
            server.execute(() -> callback.accept("§c[Oracle Error] Ollama not initialized. Use /oracle restart"));
            return;
        }

        if (!OllamaManager.isOllamaRunning()) {
            DWMod.LOGGER.error("[LLMOracleBrain] FAILED: Ollama not running");
            server.execute(() -> callback.accept("§c[Oracle Error] Ollama is not running. Start with: ollama serve"));
            return;
        }

        if (!OllamaManager.isModelAvailable(modelName)) {
            DWMod.LOGGER.error("[LLMOracleBrain] FAILED: Model '{}' not available", modelName);
            server.execute(() -> callback.accept("§c[Oracle Error] Model '" + modelName + "' not found. Use /oracle pull " + modelName));
            return;
        }

        DWMod.LOGGER.info("[LLMOracleBrain] Pre-flight checks passed, starting async generation...");

        // FIX: set busy AFTER pre-flight checks pass (a check failure returns
        // immediately without ever touching Ollama, so it shouldn't claim the
        // resource at all) and clear it as soon as the actual generation call
        // returns — not after the callback runs, since the callback itself
        // doesn't touch the shared LLM resource, just delivers already-
        // computed text back to the caller.
        busy.set(true);

        // Run in separate thread with timeout
        CompletableFuture.runAsync(() -> {
            DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Generation started");
            String response;

            try {
                DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Calling OllamaManager.generateWithOptions()...");

                long startTime = System.currentTimeMillis();

                response = OllamaManager.generateWithOptions(
                        modelName,
                        prompt,
                        temperature,
                        contextTokens
                );

                long elapsedMs = System.currentTimeMillis() - startTime;

                DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Generation completed in {}ms", elapsedMs);
                DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Response length: {} chars",
                        response != null ? response.length() : 0);

                if (response == null || response.trim().isEmpty()) {
                    DWMod.LOGGER.warn("[LLMOracleBrain] [ASYNC THREAD] Empty response from LLM");
                    response = "§7[The Oracle remains silent, contemplating the mysteries...]";
                } else {
                    DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Valid response received: '{}'",
                            response.substring(0, Math.min(100, response.length())) + "...");
                }

            } catch (java.net.http.HttpTimeoutException e) {
                response = "§c[Oracle Error] Request timed out. The model may be too slow or busy.";
                DWMod.LOGGER.error("[LLMOracleBrain] [ASYNC THREAD] HTTP Timeout: {}", e.getMessage());

            } catch (java.net.ConnectException e) {
                response = "§c[Oracle Error] Cannot connect to Ollama. Is it running?";
                DWMod.LOGGER.error("[LLMOracleBrain] [ASYNC THREAD] Connection failed: {}", e.getMessage());

            } catch (Exception e) {
                response = "§c[Oracle Error] " + e.getMessage();
                DWMod.LOGGER.error("[LLMOracleBrain] [ASYNC THREAD] Generation failed", e);
                e.printStackTrace();
            } finally {
                // FIX: finally, not just the happy path — a thrown exception
                // must still release the busy flag or the teaching loop (and
                // any other caller) would stay locked out forever after a
                // single failed generation.
                busy.set(false);
            }

            // Send response back on server thread
            final String finalResponse = response;

            DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Scheduling callback on server thread...");

            server.execute(() -> {
                DWMod.LOGGER.info("[LLMOracleBrain] [SERVER THREAD] Executing callback with response");
                try {
                    callback.accept(finalResponse);
                    DWMod.LOGGER.info("[LLMOracleBrain] [SERVER THREAD] Callback executed successfully");
                } catch (Exception e) {
                    DWMod.LOGGER.error("[LLMOracleBrain] [SERVER THREAD] Callback execution failed", e);
                }
            });

            DWMod.LOGGER.info("[LLMOracleBrain] [ASYNC THREAD] Thread completing");
        });

        DWMod.LOGGER.info("[LLMOracleBrain] Async query initiated, returning to caller");
    }

    /**
     * CompletableFuture version (optional)
     */
    public CompletableFuture<String> query(String prompt) {
        CompletableFuture<String> future = new CompletableFuture<>();

        CompletableFuture.runAsync(() -> {
            try {
                if (!OllamaManager.isInitialized()) {
                    future.completeExceptionally(new Exception("Ollama not initialized"));
                    return;
                }

                if (!OllamaManager.isOllamaRunning()) {
                    future.completeExceptionally(new Exception("Ollama not running"));
                    return;
                }

                if (!OllamaManager.isModelAvailable(modelName)) {
                    future.completeExceptionally(new Exception("Model '" + modelName + "' not found"));
                    return;
                }

                // FIX: same busy-flag treatment as queryAsync() above — set
                // only after pre-flight checks pass, cleared in finally so a
                // thrown/completedExceptionally path still releases it.
                busy.set(true);
                try {
                    String response = OllamaManager.generateWithOptions(
                            modelName,
                            prompt,
                            temperature,
                            contextTokens
                    );

                    future.complete(response);
                } finally {
                    busy.set(false);
                }

            } catch (Exception e) {
                future.completeExceptionally(e);
            }
        });

        return future;
    }

    /**
     * Test if the LLM connection is working
     */
    public boolean testConnection() {
        DWMod.LOGGER.info("[LLMOracleBrain] Testing connection...");

        if (!OllamaManager.isInitialized()) {
            DWMod.LOGGER.warn("[LLMOracleBrain] Test failed: Not initialized");
            return false;
        }

        if (!OllamaManager.isOllamaRunning()) {
            DWMod.LOGGER.warn("[LLMOracleBrain] Test failed: Not running");
            return false;
        }

        boolean available = OllamaManager.isModelAvailable(modelName);
        DWMod.LOGGER.info("[LLMOracleBrain] Test result: Model '{}' available = {}", modelName, available);

        return available;
    }
}