package com.divineworld.utils;

import com.divineworld.DWMod;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;

import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

/**
 * Agent Configuration Loader
 * Loads agent names and god types from agents.json file
 * Searches in Documents and Desktop folders (cross-platform)
 */
public class AgentConfigLoader {

    private static final String CONFIG_FILE_NAME = "agents.json";
    private static final Gson GSON = new Gson();

    private static AgentConfig cachedConfig = null;
    private static long lastLoadTime = 0;
    private static final long CACHE_DURATION_MS = 30000; // 30 seconds cache

    /**
     * Load agent configuration from agents.json
     * Searches in Documents and Desktop folders
     */
    public static AgentConfig loadConfig() {
        // Return cached config if still valid
        long currentTime = System.currentTimeMillis();
        if (cachedConfig != null && (currentTime - lastLoadTime) < CACHE_DURATION_MS) {
            return cachedConfig;
        }

        Path configPath = findConfigFile();

        if (configPath == null) {
            DWMod.LOGGER.warn("[AgentConfig] agents.json not found in Documents or Desktop. Using defaults.");
            cachedConfig = getDefaultConfig();
            lastLoadTime = currentTime;
            return cachedConfig;
        }

        try (FileReader reader = new FileReader(configPath.toFile())) {
            JsonObject root = GSON.fromJson(reader, JsonObject.class);
            cachedConfig = parseConfig(root);
            lastLoadTime = currentTime;

            DWMod.LOGGER.info("[AgentConfig] Successfully loaded from: {}", configPath);
            DWMod.LOGGER.info("[AgentConfig] Male NPCs: {}", cachedConfig.getMaleNPCNames().size());
            DWMod.LOGGER.info("[AgentConfig] Female NPCs: {}", cachedConfig.getFemaleNPCNames().size());
            DWMod.LOGGER.info("[AgentConfig] Gods: {}", cachedConfig.getGodTypes().size());

            return cachedConfig;

        } catch (Exception e) {
            DWMod.LOGGER.error("[AgentConfig] Failed to load agents.json: {}", e.getMessage());
            cachedConfig = getDefaultConfig();
            lastLoadTime = currentTime;
            return cachedConfig;
        }
    }

    /**
     * Find agents.json in common locations
     * Searches: Documents, Desktop (cross-platform)
     */
    private static Path findConfigFile() {
        String userHome = System.getProperty("user.home");
        String os = System.getProperty("os.name").toLowerCase();

        List<Path> searchPaths = new ArrayList<>();

        if (os.contains("win")) {
            // Windows paths
            searchPaths.add(Paths.get(userHome, "Documents", CONFIG_FILE_NAME));
            searchPaths.add(Paths.get(userHome, "Desktop", CONFIG_FILE_NAME));
            searchPaths.add(Paths.get(userHome, "OneDrive", "Documents", CONFIG_FILE_NAME));
            searchPaths.add(Paths.get(userHome, "OneDrive", "Desktop", CONFIG_FILE_NAME));
        } else if (os.contains("mac")) {
            // macOS paths
            searchPaths.add(Paths.get(userHome, "Documents", CONFIG_FILE_NAME));
            searchPaths.add(Paths.get(userHome, "Desktop", CONFIG_FILE_NAME));
        } else {
            // Linux/Unix paths
            searchPaths.add(Paths.get(userHome, "Documents", CONFIG_FILE_NAME));
            searchPaths.add(Paths.get(userHome, "Desktop", CONFIG_FILE_NAME));
        }

        // Search for the file
        for (Path path : searchPaths) {
            if (Files.exists(path) && Files.isRegularFile(path)) {
                DWMod.LOGGER.info("[AgentConfig] Found config at: {}", path);
                return path;
            }
        }

        // Log all searched paths
        DWMod.LOGGER.debug("[AgentConfig] Searched paths:");
        for (Path path : searchPaths) {
            DWMod.LOGGER.debug("  - {}", path);
        }

        return null;
    }

    /**
     * Parse the JSON configuration
     * Format:
     * {
     *   "NPCs": {
     *     "male": ["Adam", "Bob", "Charlie"],
     *     "female": ["Eve", "Alice", "Diana"]
     *   },
     *   "GODs": {
     *     "dual": ["Zeus", "Odin", "Ra"]
     *   }
     * }
     */
    private static AgentConfig parseConfig(JsonObject root) {
        AgentConfig config = new AgentConfig();

        // Parse NPCs
        if (root.has("NPCs")) {
            JsonObject npcs = root.getAsJsonObject("NPCs");

            if (npcs.has("male")) {
                JsonArray maleArray = npcs.getAsJsonArray("male");
                for (JsonElement element : maleArray) {
                    config.maleNPCNames.add(element.getAsString());
                }
            }

            if (npcs.has("female")) {
                JsonArray femaleArray = npcs.getAsJsonArray("female");
                for (JsonElement element : femaleArray) {
                    config.femaleNPCNames.add(element.getAsString());
                }
            }
        }

        // Parse GODs
        if (root.has("GODs")) {
            JsonObject gods = root.getAsJsonObject("GODs");

            if (gods.has("dual")) {
                JsonArray godArray = gods.getAsJsonArray("dual");
                for (JsonElement element : godArray) {
                    config.godTypes.add(element.getAsString());
                }
            }
        }

        return config;
    }

    /**
     * Get default configuration if file not found
     */
    private static AgentConfig getDefaultConfig() {
        AgentConfig config = new AgentConfig();

        // Default male NPC names
        config.maleNPCNames.addAll(Arrays.asList(
                "Adam", "Bob", "Charlie", "David", "Ethan",
                "Frank", "George", "Henry", "Isaac", "Jack"
        ));

        // Default female NPC names
        config.femaleNPCNames.addAll(Arrays.asList(
                "Eve", "Alice", "Diana", "Emily", "Fiona",
                "Grace", "Hannah", "Iris", "Julia", "Kate"
        ));

        // Default god types
        config.godTypes.addAll(Arrays.asList(
                "Zeus", "Odin", "Ra", "Amaterasu", "Shiva",
                "Quetzalcoatl", "Anubis", "Thor", "Athena", "Freya"
        ));

        return config;
    }

    /**
     * Force reload configuration (bypasses cache)
     */
    public static AgentConfig reloadConfig() {
        cachedConfig = null;
        lastLoadTime = 0;
        return loadConfig();
    }

    /**
     * Get a random male NPC name
     */
    public static String getRandomMaleNPCName() {
        AgentConfig config = loadConfig();
        List<String> names = config.getMaleNPCNames();
        if (names.isEmpty()) return "Agent_M_" + UUID.randomUUID().toString().substring(0, 8);
        return names.get(new Random().nextInt(names.size()));
    }

    /**
     * Get a random female NPC name
     */
    public static String getRandomFemaleNPCName() {
        AgentConfig config = loadConfig();
        List<String> names = config.getFemaleNPCNames();
        if (names.isEmpty()) return "Agent_F_" + UUID.randomUUID().toString().substring(0, 8);
        return names.get(new Random().nextInt(names.size()));
    }

    /**
     * Check if a god type is valid
     */
    public static boolean isValidGodType(String godType) {
        AgentConfig config = loadConfig();
        return config.getGodTypes().contains(godType.toLowerCase());
    }

    /**
     * Get all available god types
     */
    public static List<String> getGodTypes() {
        AgentConfig config = loadConfig();
        return new ArrayList<>(config.getGodTypes());
    }

    /**
     * Agent Configuration Data Class
     */
    public static class AgentConfig {
        private final List<String> maleNPCNames = new ArrayList<>();
        private final List<String> femaleNPCNames = new ArrayList<>();
        private final List<String> godTypes = new ArrayList<>();

        public List<String> getMaleNPCNames() {
            return new ArrayList<>(maleNPCNames);
        }

        public List<String> getFemaleNPCNames() {
            return new ArrayList<>(femaleNPCNames);
        }

        public List<String> getGodTypes() {
            return new ArrayList<>(godTypes);
        }
    }
}