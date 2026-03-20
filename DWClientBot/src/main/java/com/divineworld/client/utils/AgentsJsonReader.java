package com.divineworld.client.util;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Reads ~/Documents/agents.json (the same file AgentNameManager writes on
 * the Python side) to resolve port numbers by Minecraft player name.
 *
 * agents.json format  (each name maps to its unique TCP port):
 * {
 *   "NPCs": {
 *     "male":   {"Adam": 11401, "Abel": 11402, ...},
 *     "female": {"Alice": 11471, ...}
 *   },
 *   "GODs": {
 *     "dual": {
 *       "wither":   {"Mortis": 11441, ...},
 *       "oracle":   {"Zeus":   11453, ...},
 *       ...
 *     }
 *   }
 * }
 *
 * Port scheme (mirrors mc_uuid.py constants):
 *   TCP action-server port  = agents.json value          (e.g. 11471)
 *   WebSocket backend port  = TCP port + WS_PORT_OFFSET  (e.g. 21471)
 *
 * Usage:
 *   AgentsJsonReader.PortPair ports = AgentsJsonReader.lookupPorts("Alice");
 *   if (ports != null) {
 *       int tcpPort = ports.tcpPort;    // 11471
 *       int wsPort  = ports.wsPort;     // 21471
 *   }
 */
public final class AgentsJsonReader {

    private static final Logger LOGGER = LogManager.getLogger("AgentsJsonReader");

    /** Matches PORT_START in mc_uuid.py */
    public static final int PORT_START      = 11401;

    /** Matches WS_BACKEND_PORT_OFFSET in main.py / agent.py */
    public static final int WS_PORT_OFFSET  = 10000;

    /** Default TCP port if agents.json lookup fails */
    public static final int DEFAULT_TCP_PORT = PORT_START;

    /** Default WebSocket port if agents.json lookup fails */
    public static final int DEFAULT_WS_PORT  = PORT_START + WS_PORT_OFFSET;

    // Cached result — re-read at most once per player session
    private static PortPair cachedResult  = null;
    private static String   cachedForName = null;

    private AgentsJsonReader() {}

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /** Holds both the TCP port and the derived WebSocket backend port. */
    public static final class PortPair {
        public final String name;
        public final int    tcpPort;
        public final int    wsPort;

        PortPair(String name, int tcpPort) {
            this.name    = name;
            this.tcpPort = tcpPort;
            this.wsPort  = tcpPort + WS_PORT_OFFSET;
        }

        @Override public String toString() {
            return "PortPair{name=" + name + ", tcp=" + tcpPort + ", ws=" + wsPort + "}";
        }
    }

    /**
     * Look up the ports for a given Minecraft display name.
     *
     * @param playerName  Minecraft account display name (e.g. "Alice")
     * @return PortPair with tcpPort and wsPort, or null if name not found
     */
    public static PortPair lookupPorts(String playerName) {
        if (playerName == null || playerName.isEmpty()) return null;

        // Return cached result if name matches
        if (playerName.equals(cachedForName) && cachedResult != null) {
            return cachedResult;
        }

        Path jsonPath = findAgentsJson();
        if (jsonPath == null) {
            LOGGER.warn("[AgentsJson] agents.json not found in any candidate path");
            return null;
        }

        try {
            JsonObject root = parseJson(jsonPath);
            int port = searchAllCategories(root, playerName);
            if (port > 0) {
                cachedResult  = new PortPair(playerName, port);
                cachedForName = playerName;
                LOGGER.info("[AgentsJson] Resolved '{}' → TCP {} / WS {}",
                        playerName, port, port + WS_PORT_OFFSET);
                return cachedResult;
            }
            LOGGER.warn("[AgentsJson] '{}' not found in agents.json", playerName);
        } catch (Exception e) {
            LOGGER.error("[AgentsJson] Failed to read {}: {}", jsonPath, e.getMessage());
        }
        return null;
    }

    /**
     * Invalidate the in-memory cache — call when the player logs out so the
     * next session re-reads the file (in case names were added).
     */
    public static void invalidateCache() {
        cachedResult  = null;
        cachedForName = null;
    }

    // -------------------------------------------------------------------------
    // File discovery
    // -------------------------------------------------------------------------

    /**
     * Search for agents.json in the same candidate paths AgentNameManager uses.
     * Returns the first existing path, or null if none found.
     */
    static Path findAgentsJson() {
        String home = System.getProperty("user.home", "");
        if (home.isEmpty()) return null;

        String[] candidates = {
            home + "/Documents/agents.json",
            home + "/Desktop/agents.json",
            home + "/OneDrive/Documents/agents.json",
            home + "/OneDrive/Desktop/agents.json",
        };

        for (String c : candidates) {
            Path p = Paths.get(c);
            if (p.toFile().exists()) {
                LOGGER.debug("[AgentsJson] Found: {}", p);
                return p;
            }
        }
        return null;
    }

    // -------------------------------------------------------------------------
    // JSON parsing  (GSON is bundled with Forge/Minecraft)
    // -------------------------------------------------------------------------

    private static JsonObject parseJson(Path path) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader br = new BufferedReader(new FileReader(path.toFile()))) {
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
        }
        return JsonParser.parseString(sb.toString()).getAsJsonObject();
    }

    /**
     * Walk every category in the agents.json tree looking for playerName.
     * Returns the integer port value, or -1 if not found.
     *
     * Tree shape:
     *   root
     *     "NPCs"
     *       "male"   → {name: port, ...}
     *       "female" → {name: port, ...}
     *     "GODs"
     *       "dual"
     *         "wither"  → {name: port, ...}
     *         "oracle"  → {name: port, ...}
     *         ...
     */
    private static int searchAllCategories(JsonObject root, String name) {
        // NPCs section: root.NPCs.{gender}.{name}
        if (root.has("NPCs")) {
            JsonObject npcs = root.getAsJsonObject("NPCs");
            for (String gender : new String[]{"male", "female"}) {
                if (npcs.has(gender)) {
                    int port = findInObject(npcs.getAsJsonObject(gender), name);
                    if (port > 0) return port;
                }
            }
        }

        // GODs section: root.GODs.dual.{godType}.{name}
        if (root.has("GODs")) {
            JsonObject gods = root.getAsJsonObject("GODs");
            if (gods.has("dual")) {
                JsonObject dual = gods.getAsJsonObject("dual");
                for (String godType : dual.keySet()) {
                    JsonElement typeElem = dual.get(godType);
                    if (typeElem.isJsonObject()) {
                        int port = findInObject(typeElem.getAsJsonObject(), name);
                        if (port > 0) return port;
                    }
                }
            }
        }

        return -1;
    }

    /**
     * Look for name as a key in a flat {name: port} JsonObject.
     * Returns the port as int, or -1 if not found.
     */
    private static int findInObject(JsonObject obj, String name) {
        if (obj.has(name)) {
            JsonElement val = obj.get(name);
            if (val.isJsonPrimitive()) {
                try {
                    return val.getAsInt();
                } catch (NumberFormatException ignored) {}
            }
        }
        return -1;
    }
}