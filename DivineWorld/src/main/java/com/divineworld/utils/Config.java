package com.divineworld.utils;

import com.divineworld.DWMod;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.HashMap;
import java.util.Map;

/**
 * Configuration loader for Oracle and agent settings
 * Simple YAML parser - no external libraries needed
 */
public class Config {

    private static Map<String, String> config = new HashMap<>();

    public static void load() {
        try {
            // Try loading from resources
            InputStream stream = Config.class.getResourceAsStream("/META-INF/config.yml");

            if (stream != null) {
                parseConfig(stream);
                stream.close();

                DWMod.LOGGER.info("[Config] ✅ Loaded from resources/META-INF/config.yml");
                logConfig();
            } else {
                DWMod.LOGGER.warn("[Config] config.yml not found in resources, using defaults");
                useDefaults();
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Config] Failed to load config.yml", e);
            useDefaults();
        }
    }

    /**
     * Simple YAML parser - handles basic key: value pairs
     */
    private static void parseConfig(InputStream stream) {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream))) {
            String line;
            String currentSection = "";

            while ((line = reader.readLine()) != null) {
                line = line.trim();

                // Skip comments and empty lines
                if (line.isEmpty() || line.startsWith("#") || line.startsWith("-")) {
                    continue;
                }

                // Section headers (e.g., "oracle:")
                if (line.endsWith(":") && !line.contains(" ")) {
                    currentSection = line.substring(0, line.length() - 1);
                    continue;
                }

                // Key-value pairs
                if (line.contains(":")) {
                    String[] parts = line.split(":", 2);
                    if (parts.length == 2) {
                        String key = parts[0].trim();
                        String value = parts[1].trim().replaceAll("\"", "");

                        // Store with section prefix
                        if (!currentSection.isEmpty()) {
                            config.put(currentSection + "." + key, value);
                        } else {
                            config.put(key, value);
                        }
                    }
                }
            }

        } catch (Exception e) {
            DWMod.LOGGER.error("[Config] Error parsing config.yml", e);
        }
    }

    private static void useDefaults() {
        config.put("oracle.context_tokens", "2048");
        config.put("oracle.temperature", "0.4");
        config.put("oracle.endpoint", "http://localhost:11434");
        config.put("oracle.active-model", "phi3:mini");
        config.put("agents.max_concurrent", "50");
        config.put("agents.decision_rate_hz", "10");
        config.put("agents.perception_batch_size", "32");

        DWMod.LOGGER.info("[Config] Using default configuration");
    }

    private static void logConfig() {
        DWMod.LOGGER.info("[Config] Oracle Settings:");
        DWMod.LOGGER.info("  - Model: {}", getOracleModel());
        DWMod.LOGGER.info("  - Endpoint: {}", getOracleEndpoint());
        DWMod.LOGGER.info("  - Context Tokens: {}", getContextTokens());
        DWMod.LOGGER.info("  - Temperature: {}", getTemperature());
    }

    public static String getOracleModel() {
        return config.getOrDefault("oracle.active-model", "phi3:mini");
    }

    public static String getOracleEndpoint() {
        return config.getOrDefault("oracle.endpoint", "http://localhost:11434");
    }

    public static int getContextTokens() {
        try {
            return Integer.parseInt(config.getOrDefault("oracle.context_tokens", "2048"));
        } catch (NumberFormatException e) {
            return 2048;
        }
    }

    public static double getTemperature() {
        try {
            return Double.parseDouble(config.getOrDefault("oracle.temperature", "0.4"));
        } catch (NumberFormatException e) {
            return 0.4;
        }
    }

    public static int getMaxConcurrentAgents() {
        try {
            return Integer.parseInt(config.getOrDefault("agents.max_concurrent", "50"));
        } catch (NumberFormatException e) {
            return 50;
        }
    }

    public static int getDecisionRateHz() {
        try {
            return Integer.parseInt(config.getOrDefault("agents.decision_rate_hz", "10"));
        } catch (NumberFormatException e) {
            return 10;
        }
    }

    public static int getPerceptionBatchSize() {
        try {
            return Integer.parseInt(config.getOrDefault("agents.perception_batch_size", "32"));
        } catch (NumberFormatException e) {
            return 32;
        }
    }
}