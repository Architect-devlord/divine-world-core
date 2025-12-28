package com.divineworld.oracle;

import com.divineworld.DWMod;
import net.minecraft.server.MinecraftServer;

import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

/**
 * SIMPLIFIED LLM Oracle Brain using OllamaManager
 * No more manual HTTP calls - uses ollama4j library
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
     * Async query - safe for Minecraft server thread
     */
    public void queryAsync(
            MinecraftServer server,
            String prompt,
            Consumer<String> callback
    ) {
        DWMod.LOGGER.debug("[LLMOracleBrain] Querying model: {}", modelName);
        DWMod.LOGGER.debug("[LLMOracleBrain] Prompt length: {} chars", prompt.length());

        // Run in separate thread
        CompletableFuture.runAsync(() -> {
            String response;

            try {
                // Check if Ollama is available
                if (!OllamaManager.isInitialized()) {
                    response = "§c[Oracle Error] Ollama not initialized";
                    DWMod.LOGGER.error("[LLMOracleBrain] Ollama not initialized");

                } else if (!OllamaManager.isOllamaRunning()) {
                    response = "§c[Oracle Error] Ollama is not running";
                    DWMod.LOGGER.error("[LLMOracleBrain] Ollama not running");

                } else if (!OllamaManager.isModelAvailable(modelName)) {
                    response = "§c[Oracle Error] Model '" + modelName + "' not found";
                    DWMod.LOGGER.error("[LLMOracleBrain] Model '{}' not available", modelName);

                } else {
                    // Generate response using ollama4j
                    response = OllamaManager.generateWithOptions(
                            modelName,
                            prompt,
                            temperature,
                            contextTokens
                    );

                    if (response == null || response.trim().isEmpty()) {
                        response = "§7[The Oracle remains silent.]";
                    }

                    DWMod.LOGGER.debug("[LLMOracleBrain] Got response: {} chars", response.length());
                }

            } catch (Exception e) {
                response = "§c[Oracle Error] " + e.getMessage();
                DWMod.LOGGER.error("[LLMOracleBrain] Query failed: {}", e.getMessage());
            }

            // Send response back on server thread
            final String finalResponse = response;
            server.execute(() -> callback.accept(finalResponse));
        });
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
        if (!OllamaManager.isInitialized()) {
            return false;
        }

        if (!OllamaManager.isOllamaRunning()) {
            return false;
        }

        return OllamaManager.isModelAvailable(modelName);
    }
}