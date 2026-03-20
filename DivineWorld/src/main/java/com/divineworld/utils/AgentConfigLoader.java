package com.divineworld.utils;

import com.divineworld.DWMod;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;

import java.io.FileReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

/**
 * Agent Configuration Loader
 * ==========================
 * Reads agents.json produced by the Python backend (mc_uuid.AgentNameManager).
 *
 * Expected schema (canonical format from mc_uuid.py):
 * {
 *   "NPCs": {
 *     "male":   ["Adam", "Abel", ...],
 *     "female": ["Eve", "Sarah", ...]
 *   },
 *   "GODs": {
 *     "dual": {
 *       "wither":         ["Mortis", "Necros"],
 *       "ender_dragon":   ["Draconis", "Voidwing"],
 *       "warden":         ["Tenebris", "Obsidius"],
 *       "oracle":         ["Zeus", "Odin", "Ra"],
 *       "elder_guardian": ["Pelagius", "Thetis"],
 *       "creaking":       ["Sylvanus", "Arbor"]
 *     }
 *   }
 * }
 *
 * NO default name lists are defined here.  The Python main.py creates
 * agents.json on startup via AgentNameManager._ensure_config_exists().
 * If the file is absent the config will be empty — agents will be tagged
 * only by username prefix (DW_ / DWGOD_) until the file appears.
 *
 * Cache: 30 seconds.  Call reloadConfig() to force an immediate refresh.
 */
public class AgentConfigLoader {

    private static final String   CONFIG_FILE_NAME   = "agents.json";
    private static final Gson     GSON               = new Gson();
    private static final long     CACHE_DURATION_MS  = 30_000L;

    private static AgentConfig cachedConfig  = null;
    private static long        lastLoadTime  = 0;

    // -------------------------------------------------------------------------
    // Public load entry-point
    // -------------------------------------------------------------------------

    public static AgentConfig loadConfig() {
        long now = System.currentTimeMillis();
        if (cachedConfig != null && (now - lastLoadTime) < CACHE_DURATION_MS) {
            return cachedConfig;
        }

        Path configPath = findConfigFile();
        if (configPath == null) {
            DWMod.LOGGER.warn("[AgentConfig] agents.json not found — tagging by prefix only until Python backend creates it.");
            cachedConfig  = new AgentConfig();   // empty
            lastLoadTime  = now;
            return cachedConfig;
        }

        try (FileReader reader = new FileReader(configPath.toFile())) {
            JsonObject root = GSON.fromJson(reader, JsonObject.class);
            cachedConfig  = parseConfig(root);
            lastLoadTime  = now;

            DWMod.LOGGER.info("[AgentConfig] Loaded from: {}", configPath);
            DWMod.LOGGER.info("[AgentConfig]  male NPCs={} female NPCs={} god types={}",
                    cachedConfig.getMaleNPCNames().size(),
                    cachedConfig.getFemaleNPCNames().size(),
                    cachedConfig.getGodTypes().size());
            return cachedConfig;

        } catch (Exception e) {
            DWMod.LOGGER.error("[AgentConfig] Failed to parse agents.json: {}", e.getMessage());
            if (cachedConfig == null) cachedConfig = new AgentConfig();
            lastLoadTime = now;
            return cachedConfig;
        }
    }

    /** Force cache invalidation and re-read. */
    public static AgentConfig reloadConfig() {
        cachedConfig = null;
        lastLoadTime = 0;
        return loadConfig();
    }

    // -------------------------------------------------------------------------
    // File discovery  (mirrors AgentNameManager._find_config_path in mc_uuid.py)
    // -------------------------------------------------------------------------

    private static Path findConfigFile() {
        String userHome = System.getProperty("user.home");
        String os       = System.getProperty("os.name").toLowerCase();

        List<Path> candidates = new ArrayList<>();
        if (os.contains("win")) {
            candidates.add(Paths.get(userHome, "Documents",           CONFIG_FILE_NAME));
            candidates.add(Paths.get(userHome, "Desktop",             CONFIG_FILE_NAME));
            candidates.add(Paths.get(userHome, "OneDrive", "Documents", CONFIG_FILE_NAME));
            candidates.add(Paths.get(userHome, "OneDrive", "Desktop",   CONFIG_FILE_NAME));
        } else {
            // macOS + Linux
            candidates.add(Paths.get(userHome, "Documents", CONFIG_FILE_NAME));
            candidates.add(Paths.get(userHome, "Desktop",   CONFIG_FILE_NAME));
        }

        for (Path p : candidates) {
            if (Files.exists(p) && Files.isRegularFile(p)) {
                return p;
            }
        }
        return null;
    }

    // -------------------------------------------------------------------------
    // JSON parsing
    // -------------------------------------------------------------------------

    /**
     * Parses the agents.json structure produced by mc_uuid.AgentNameManager.
     *
     * ACTUAL format (from mc_uuid.py):
     *   NPCs.male   → {"Adam": 11401, "Abel": 11402}   (JsonObject: name → port)
     *   NPCs.female → {"Eve": 11420, ...}              (JsonObject: name → port)
     *   GODs.dual.<type> → {"Mortis": 11440, ...}      (JsonObject: name → port)
     *
     * The old code called parseStringArray() which checked isJsonArray() — always
     * false for this format, so all lists came back empty and every connecting agent
     * was classified as REAL_PLAYER. (FIX S-01)
     *
     * Legacy flat JsonArray is still accepted with a warning.
     */
    private static AgentConfig parseConfig(JsonObject root) {
        AgentConfig cfg = new AgentConfig();

        // NPCs
        if (root.has("NPCs")) {
            JsonObject npcs = root.getAsJsonObject("NPCs");
            parseNamesFromElem(npcs, "male")  .forEach(cfg.maleNPCNames::add);
            parseNamesFromElem(npcs, "female").forEach(cfg.femaleNPCNames::add);
        }

        // GODs
        if (root.has("GODs")) {
            JsonObject gods = root.getAsJsonObject("GODs");
            if (gods.has("dual")) {
                JsonElement dualElem = gods.get("dual");

                if (dualElem.isJsonObject()) {
                    // Canonical: GODs.dual.{type} = {"Name": port, ...}
                    for (Map.Entry<String, JsonElement> entry : dualElem.getAsJsonObject().entrySet()) {
                        String       type  = entry.getKey().toLowerCase();
                        List<String> names = extractNames(entry.getValue());
                        cfg.godTypes.add(type);
                        cfg.godNamesByType.put(type, names);
                    }
                } else if (dualElem.isJsonArray()) {
                    // Legacy flat array — treat all as oracle names
                    DWMod.LOGGER.warn("[AgentConfig] Legacy flat GODs.dual array — treating as 'oracle' names.");
                    List<String> names = new ArrayList<>();
                    for (JsonElement ne : dualElem.getAsJsonArray()) names.add(ne.getAsString());
                    cfg.godTypes.add("oracle");
                    cfg.godNamesByType.put("oracle", names);
                }
            }
        }

        return cfg;
    }

    /**
     * Extract name strings from a JsonElement that is either:
     *   - JsonObject: {"Name": port, ...}   → keys are the names  (mc_uuid.py format)
     *   - JsonArray:  ["Name", ...]          → elements are names  (legacy format)
     */
    private static List<String> extractNames(JsonElement elem) {
        List<String> list = new ArrayList<>();
        if (elem == null) return list;
        if (elem.isJsonObject()) {
            // Standard mc_uuid.py format: keys are names, values are ports (ignored)
            for (String name : elem.getAsJsonObject().keySet()) {
                if (!name.isEmpty()) list.add(name);
            }
        } else if (elem.isJsonArray()) {
            for (JsonElement e : elem.getAsJsonArray()) {
                if (e.isJsonPrimitive()) list.add(e.getAsString());
            }
        }
        return list;
    }

    /**
     * Read names from obj.get(key), accepting both JsonObject (canonical)
     * and JsonArray (legacy) under the given key.
     */
    private static List<String> parseNamesFromElem(JsonObject obj, String key) {
        if (!obj.has(key)) return new ArrayList<>();
        return extractNames(obj.get(key));
    }

    // -------------------------------------------------------------------------
    // Convenience lookups
    // -------------------------------------------------------------------------

    /** True if name is in NPCs.male. */
    public static boolean isMaleNPC(String name)    { return loadConfig().isMaleNPC(name); }

    /** True if name is in NPCs.female. */
    public static boolean isFemaleNPC(String name)  { return loadConfig().isFemaleNPC(name); }

    /** True if name is in any GODs.dual.* pool. */
    public static boolean isGodName(String name)    { return loadConfig().isGodName(name); }

    /**
     * True if the string is a valid entity-type key
     * ("wither", "ender_dragon", "oracle", etc.).
     * Used by DivineCommands.executeSpawnGod to validate /spawn_god <type>.
     */
    public static boolean isValidGodType(String key) {
        return loadConfig().getGodTypes().contains(key.toLowerCase());
    }

    /** All valid entity-type keys from agents.json. */
    public static List<String> getGodTypes() { return loadConfig().getGodTypes(); }

    /**
     * Given a display name ("Zeus"), return its god entity-type key ("oracle"),
     * or null if not found.
     */
    public static String getGodTypeForName(String name) { return loadConfig().getGodTypeForName(name); }

    /**
     * Classify a display name against agents.json.
     * Returns null when the name is absent from all lists (= real player or
     * freshly packaged agent whose name hasn't been registered yet).
     */
    public static AgentType getAgentTypeForName(String displayName) {
        AgentConfig cfg = loadConfig();
        if (cfg.isMaleNPC(displayName))   return AgentType.NPC_MALE;
        if (cfg.isFemaleNPC(displayName)) return AgentType.NPC_FEMALE;
        if (cfg.isGodName(displayName))   return AgentType.GOD;
        return null;
    }

    /** Agent type as read from agents.json. */
    public enum AgentType { NPC_MALE, NPC_FEMALE, GOD }

    // -------------------------------------------------------------------------
    // AgentConfig inner class
    // -------------------------------------------------------------------------

    public static class AgentConfig {
        final List<String>              maleNPCNames   = new ArrayList<>();
        final List<String>              femaleNPCNames = new ArrayList<>();
        /** Entity-type keys: "wither", "ender_dragon", "oracle", etc. */
        final List<String>              godTypes       = new ArrayList<>();
        /** Name pools keyed by entity-type. */
        final Map<String, List<String>> godNamesByType = new LinkedHashMap<>();

        public List<String> getMaleNPCNames()   { return Collections.unmodifiableList(maleNPCNames); }
        public List<String> getFemaleNPCNames() { return Collections.unmodifiableList(femaleNPCNames); }
        public List<String> getGodTypes()       { return Collections.unmodifiableList(godTypes); }

        public List<String> getGodNamesForType(String type) {
            return godNamesByType.getOrDefault(type.toLowerCase(), Collections.emptyList());
        }

        public List<String> getAllGodNames() {
            List<String> all = new ArrayList<>();
            godNamesByType.values().forEach(all::addAll);
            return all;
        }

        public String getGodTypeForName(String name) {
            for (Map.Entry<String, List<String>> e : godNamesByType.entrySet()) {
                if (e.getValue().contains(name)) return e.getKey();
            }
            return null;
        }

        public boolean isMaleNPC(String name)  { return maleNPCNames.contains(name); }
        public boolean isFemaleNPC(String name){ return femaleNPCNames.contains(name); }
        public boolean isGodName(String name)  { return getGodTypeForName(name) != null; }
        public boolean isNpcName(String name)  { return isMaleNPC(name) || isFemaleNPC(name); }
    }
}