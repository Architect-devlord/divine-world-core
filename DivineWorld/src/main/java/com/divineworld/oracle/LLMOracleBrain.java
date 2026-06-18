// src/main/java/com/divineworld/oracle/LLMOracleBrain.java
// DivineWorld server mod
package com.divineworld.oracle;

import com.divineworld.DWMod;
import net.minecraft.server.MinecraftServer;

import java.util.concurrent.CompletableFuture;
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

                String response = OllamaManager.generateWithOptions(
                        modelName,
                        prompt,
                        temperature,
                        contextTokens
                );

                future.complete(response);

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
