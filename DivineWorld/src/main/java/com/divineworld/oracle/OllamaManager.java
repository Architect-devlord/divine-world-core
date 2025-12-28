package com.divineworld.oracle;

import com.divineworld.DWMod;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * DIAGNOSTIC Ollama Manager - Enhanced logging to debug connection issues
 */
public class OllamaManager {

    private static final String[] OLLAMA_HOSTS = {
            "http://127.0.0.1:11434"  // Only use IPv4, avoid localhost IPv6 issues
            //IPv6 localhost address for ollama endpoint= "http://192.168.255.192:11434"
            // to apply this remove the added section in the user_jvm_args.txt in the DW_Server folder
    };
    private static String OLLAMA_HOST = null;
    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)  // Force HTTP/1.1 instead of 2
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    private static final Gson GSON = new Gson();
    private static boolean initialized = false;

    /**
     * Initialize Ollama API client with detailed diagnostics
     */
    public static void initialize(String defaultModel) {
        DWMod.LOGGER.info("[Ollama] ╔═══════════════════════════════════════╗");
        DWMod.LOGGER.info("[Ollama] Initializing Ollama Connection");
        DWMod.LOGGER.info("[Ollama] ╚═══════════════════════════════════════╝");

        // Try different host addresses
        for (String host : OLLAMA_HOSTS) {
            DWMod.LOGGER.info("[Ollama] Trying: {}", host);

            try {
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(host + "/api/tags"))
                        .timeout(Duration.ofSeconds(5))
                        .GET()
                        .build();

                DWMod.LOGGER.info("[Ollama] Sending request...");

                HttpResponse<String> response = HTTP_CLIENT.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

                DWMod.LOGGER.info("[Ollama] Response code: {}", response.statusCode());

                if (response.statusCode() == 200) {
                    OLLAMA_HOST = host;
                    DWMod.LOGGER.info("[Ollama] ✅ Successfully connected to Ollama at {}", host);
                    initialized = true;

                    // Log available models
                    listAvailableModels();

                    // Check if default model exists
                    ModelStatus status = checkModelStatus(defaultModel);

                    switch (status) {
                        case AVAILABLE:
                            DWMod.LOGGER.info("[Ollama] ✅ Default model '{}' is ready", defaultModel);
                            break;
                        case NOT_DOWNLOADED:
                            DWMod.LOGGER.warn("[Ollama] ⚠️ Model '{}' not found", defaultModel);
                            DWMod.LOGGER.warn("[Ollama] Run: ollama pull {}", defaultModel);
                            DWMod.LOGGER.warn("[Ollama] Or use in-game: /oracle pull {}", defaultModel);
                            break;
                        case ERROR:
                            DWMod.LOGGER.error("[Ollama] ❌ Error checking model status");
                            break;
                    }

                    DWMod.LOGGER.info("[Ollama] ╚═══════════════════════════════════════╝");
                    return; // Success, exit early

                } else {
                    DWMod.LOGGER.warn("[Ollama] Unexpected status code: {} from {}", response.statusCode(), host);
                }

            } catch (java.net.ConnectException e) {
                DWMod.LOGGER.warn("[Ollama] Connection refused at {} - trying next...", host);

            } catch (java.net.http.HttpTimeoutException e) {
                DWMod.LOGGER.warn("[Ollama] Connection timeout at {} - trying next...", host);

            } catch (Exception e) {
                DWMod.LOGGER.warn("[Ollama] Failed to connect to {}: {}", host, e.getMessage());
            }
        }

        // If we get here, all connection attempts failed
        DWMod.LOGGER.error("[Ollama] ❌ Failed to connect to any Ollama endpoint!");
        DWMod.LOGGER.error("[Ollama] Tried: {}", String.join(", ", OLLAMA_HOSTS));
        DWMod.LOGGER.error("[Ollama] ");
        DWMod.LOGGER.error("[Ollama] Troubleshooting steps:");
        DWMod.LOGGER.error("[Ollama]   1. Check if Ollama is running: sudo systemctl status ollama");
        DWMod.LOGGER.error("[Ollama]   2. Check listening ports: sudo netstat -tlnp | grep ollama");
        DWMod.LOGGER.error("[Ollama]   3. Test manually: curl http://127.0.0.1:11434/api/tags");
        DWMod.LOGGER.error("[Ollama]   4. Check Java version (needs 11+): java --version");
        DWMod.LOGGER.error("[Ollama]   5. Use /oracle restart in-game after fixing");
        initialized = false;

        DWMod.LOGGER.info("[Ollama] ╚═══════════════════════════════════════╝");
    }

    /**
     * Check if Ollama is running by pinging the API
     */
    public static boolean isOllamaRunning() {
        if (OLLAMA_HOST == null) {
            return false;
        }

        try {
            DWMod.LOGGER.debug("[Ollama] Checking if Ollama is running...");

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(OLLAMA_HOST + "/api/tags"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            boolean running = response.statusCode() == 200;
            DWMod.LOGGER.debug("[Ollama] Ping result: {} (status: {})",
                    running ? "RUNNING" : "NOT RUNNING",
                    response.statusCode());

            return running;

        } catch (java.net.ConnectException e) {
            DWMod.LOGGER.debug("[Ollama] Connection refused - daemon not running");
            return false;
        } catch (Exception e) {
            DWMod.LOGGER.debug("[Ollama] Ping failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Get list of available models
     */
    public static List<String> getAvailableModels() {
        if (!initialized) {
            DWMod.LOGGER.warn("[Ollama] Cannot list models - not initialized");
            return List.of();
        }

        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(OLLAMA_HOST + "/api/tags"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            if (response.statusCode() == 200) {
                DWMod.LOGGER.debug("[Ollama] Models response: {}", response.body());

                JsonObject json = GSON.fromJson(response.body(), JsonObject.class);
                JsonArray models = json.getAsJsonArray("models");

                List<String> modelNames = new ArrayList<>();
                for (int i = 0; i < models.size(); i++) {
                    JsonObject model = models.get(i).getAsJsonObject();
                    modelNames.add(model.get("name").getAsString());
                }

                return modelNames;
            } else {
                DWMod.LOGGER.warn("[Ollama] Failed to list models: HTTP {}", response.statusCode());
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Ollama] Failed to list models: {}", e.getMessage());
        }

        return List.of();
    }

    /**
     * Check if a specific model is available
     */
    public static boolean isModelAvailable(String modelName) {
        List<String> models = getAvailableModels();
        boolean available = models.contains(modelName);
        DWMod.LOGGER.debug("[Ollama] Model '{}' available: {}", modelName, available);
        return available;
    }

    /**
     * List available models (for logging)
     */
    private static void listAvailableModels() {
        try {
            List<String> models = getAvailableModels();

            if (models.isEmpty()) {
                DWMod.LOGGER.warn("[Ollama] No models found. Pull models with 'ollama pull <model>'");
            } else {
                DWMod.LOGGER.info("[Ollama] Available models: {}", String.join(", ", models));
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Ollama] Failed to list models: {}", e.getMessage());
        }
    }

    /**
     * Pull a model from Ollama
     */
    public static boolean pullModel(String modelName) {
        if (!initialized) {
            DWMod.LOGGER.error("[Ollama] Cannot pull model - not initialized");
            return false;
        }

        try {
            DWMod.LOGGER.info("[Ollama] Pulling model: {} (this may take a while)...", modelName);

            JsonObject requestBody = new JsonObject();
            requestBody.addProperty("name", modelName);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(OLLAMA_HOST + "/api/pull"))
                    .timeout(Duration.ofMinutes(30)) // Long timeout for model downloads
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody.toString()))
                    .build();

            HttpResponse<String> response = HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            DWMod.LOGGER.info("[Ollama] Pull response: {}", response.statusCode());

            if (response.statusCode() == 200) {
                DWMod.LOGGER.info("[Ollama] ✅ Successfully pulled model: {}", modelName);
                return true;
            } else {
                DWMod.LOGGER.error("[Ollama] Failed to pull model: HTTP {} - {}",
                        response.statusCode(), response.body());
                return false;
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Ollama] Failed to pull model '{}': {}", modelName, e.getMessage());
            return false;
        }
    }

    /**
     * Generate with options (temperature, context, etc.)
     */
    public static String generateWithOptions(String modelName, String prompt,
                                             double temperature, int contextTokens) throws Exception {
        DWMod.LOGGER.debug("[Ollama] Generate request - Model: {}, Prompt length: {}, Temp: {}, Context: {}",
                modelName, prompt.length(), temperature, contextTokens);

        if (!initialized) {
            throw new Exception("Ollama not initialized");
        }

        if (!isOllamaRunning()) {
            throw new Exception("Ollama is not running");
        }

        if (!isModelAvailable(modelName)) {
            throw new Exception("Model '" + modelName + "' not found");
        }

        try {
            JsonObject requestBody = new JsonObject();
            requestBody.addProperty("model", modelName);
            requestBody.addProperty("prompt", prompt);
            requestBody.addProperty("stream", false);

            // Add options
            JsonObject options = new JsonObject();
            options.addProperty("temperature", temperature);
            options.addProperty("num_ctx", contextTokens);
            requestBody.add("options", options);

            DWMod.LOGGER.debug("[Ollama] Sending generation request...");

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(OLLAMA_HOST + "/api/generate"))
                    .timeout(Duration.ofMinutes(2))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody.toString()))
                    .build();

            HttpResponse<String> response = HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            DWMod.LOGGER.debug("[Ollama] Generation response status: {}", response.statusCode());

            if (response.statusCode() == 200) {
                JsonObject json = GSON.fromJson(response.body(), JsonObject.class);
                String result = json.get("response").getAsString();
                DWMod.LOGGER.debug("[Ollama] Generated {} characters", result.length());
                return result;
            } else {
                throw new Exception("HTTP " + response.statusCode() + ": " + response.body());
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Ollama] Generation failed: {}", e.getMessage());
            throw new Exception("Failed to generate response: " + e.getMessage());
        }
    }

    /**
     * Check if initialized
     */
    public static boolean isInitialized() {
        return initialized;
    }

    /**
     * Get the current Ollama host being used
     */
    public static String getHost() {
        return OLLAMA_HOST != null ? OLLAMA_HOST : "NOT CONNECTED";
    }

    /**
     * Get status string
     */
    public static String getStatus() {
        if (!initialized) {
            return "§cNot initialized";
        }

        if (isOllamaRunning()) {
            return "§aRunning";
        } else {
            return "§cNot responding";
        }
    }

    /**
     * Shutdown (nothing to cleanup for HTTP client)
     */
    public static void shutdown() {
        DWMod.LOGGER.info("[Ollama] Shutting down...");
        initialized = false;
        DWMod.LOGGER.info("[Ollama] ✅ Shutdown complete");
    }

    /**
     * Refresh - check connection with detailed diagnostics
     */
    public static boolean refresh() {
        DWMod.LOGGER.info("[Ollama] Refreshing connection...");

        // Try all possible hosts again
        for (String host : OLLAMA_HOSTS) {
            DWMod.LOGGER.info("[Ollama] Testing: {}", host);

            try {
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(host + "/api/tags"))
                        .timeout(Duration.ofSeconds(5))
                        .GET()
                        .build();

                DWMod.LOGGER.info("[Ollama] Sending test request...");

                HttpResponse<String> response = HTTP_CLIENT.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

                DWMod.LOGGER.info("[Ollama] Response status: {}", response.statusCode());

                if (response.statusCode() == 200) {
                    OLLAMA_HOST = host;
                    initialized = true;
                    DWMod.LOGGER.info("[Ollama] ✅ Connection successful at {}", host);
                    listAvailableModels();
                    return true;
                }

            } catch (java.net.ConnectException e) {
                DWMod.LOGGER.warn("[Ollama] Connection refused at {}", host);

            } catch (Exception e) {
                DWMod.LOGGER.warn("[Ollama] Failed to connect to {}: {}", host, e.getMessage());
            }
        }

        // All attempts failed
        initialized = false;
        DWMod.LOGGER.error("[Ollama] ❌ All connection attempts failed");
        DWMod.LOGGER.error("[Ollama] Check: sudo systemctl status ollama");
        DWMod.LOGGER.error("[Ollama] Check: curl http://127.0.0.1:11434/api/tags");
        return false;
    }

    /**
     * Check model status
     */
    public static ModelStatus checkModelStatus(String model) {
        try {
            if (!initialized) {
                DWMod.LOGGER.debug("[Ollama] Cannot check model - not initialized");
                return ModelStatus.OLLAMA_NOT_RUNNING;
            }

            if (!isOllamaRunning()) {
                return ModelStatus.OLLAMA_NOT_RUNNING;
            }

            List<String> models = getAvailableModels();
            DWMod.LOGGER.debug("[Ollama] Checking if '{}' is in: {}", model, models);

            if (models.contains(model)) {
                return ModelStatus.AVAILABLE;
            } else {
                return ModelStatus.NOT_DOWNLOADED;
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Ollama] Error checking model status '{}': {}", model, e.getMessage());
            return ModelStatus.ERROR;
        }
    }

    public enum ModelStatus {
        AVAILABLE,
        NOT_DOWNLOADED,
        OLLAMA_NOT_RUNNING,
        ERROR
    }
}