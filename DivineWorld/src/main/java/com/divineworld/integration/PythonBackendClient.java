// src/main/java/com/divineworld/integration/PythonBackendClient.java
// DivineWorld server mod
package com.divineworld.integration;

import com.divineworld.DWMod;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;

/**
 * HTTP client for Python backend communication
 * UPDATED with single agent spawn endpoint
 */
public class PythonBackendClient {

    private static final String BACKEND_URL = System.getProperty("dw.backend", "http://127.0.0.1:11400");
    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();

    /**
     * ✅ NEW: Spawn a single NPC agent (NOT genesis)
     * Used by /dw npc spawn command
     */
    public static void spawnSingleAgent(String agentName, String spawnerName,
                                        String worldName, BlockPos spawnPos) {
        JsonObject json = new JsonObject();
        json.addProperty("agent_name", agentName);
        json.addProperty("spawner", spawnerName);
        json.addProperty("world", worldName);

        JsonObject pos = new JsonObject();
        pos.addProperty("x", spawnPos.getX());
        pos.addProperty("y", spawnPos.getY());
        pos.addProperty("z", spawnPos.getZ());
        json.add("spawn_position", pos);

        sendAsync(json, "/api/agents/spawn_single");
    }

    /**
     * Spawn 2 Genesis agents (male + female) via Python backend
     * Used by /genesis command ONLY
     */
    public static void spawnGenesisAgents(String spawnerName, String worldName,
                                          BlockPos spawn1, BlockPos spawn2) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "genesis");
        json.addProperty("spawner", spawnerName);
        json.addProperty("world", worldName);
        json.addProperty("spawn_count", 2);

        JsonArray spawns = new JsonArray();
        JsonObject pos1 = new JsonObject();
        pos1.addProperty("x", spawn1.getX());
        pos1.addProperty("y", spawn1.getY());
        pos1.addProperty("z", spawn1.getZ());
        pos1.addProperty("gender", "male");
        spawns.add(pos1);

        JsonObject pos2 = new JsonObject();
        pos2.addProperty("x", spawn2.getX());
        pos2.addProperty("y", spawn2.getY());
        pos2.addProperty("z", spawn2.getZ());
        pos2.addProperty("gender", "female");
        spawns.add(pos2);

        json.add("spawn_positions", spawns);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/genesis/spawn");
    }

    /**
     * Notify backend of Divine Reset - Delete agent memories
     */
    public static void notifyDivineReset(String worldName, List<String> agentIds) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "divine_reset");
        json.addProperty("world", worldName);
        json.addProperty("agent_count", agentIds.size());

        JsonArray agents = new JsonArray();
        for (String id : agentIds) {
            agents.add(id);
        }
        json.add("agent_ids", agents);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/divine_reset");
    }

    /**
     * Clear specific agent memories (with exceptions)
     */
    public static void clearAgentMemories(List<String> agentIds, List<String> exceptions) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "clear_memories");

        JsonArray targets = new JsonArray();
        for (String id : agentIds) {
            if (!exceptions.contains(id)) {
                targets.add(id);
            }
        }
        json.add("agent_ids", targets);

        JsonArray except = new JsonArray();
        for (String id : exceptions) {
            except.add(id);
        }
        json.add("exceptions", except);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/agents/clear_memories");
    }

    /**
     * Spawn a god agent via Python backend
     */
    public static void spawnGodAgent(String godType, String spawnerName,
                                     String worldName, BlockPos spawnPos) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "spawn_god");
        json.addProperty("god_type", godType);
        json.addProperty("spawner", spawnerName);
        json.addProperty("world", worldName);

        JsonObject pos = new JsonObject();
        pos.addProperty("x", spawnPos.getX());
        pos.addProperty("y", spawnPos.getY());
        pos.addProperty("z", spawnPos.getZ());
        json.add("spawn_position", pos);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/gods/spawn");
    }

    /**
     * Command a god to use an ability
     */
    public static void godUseAbility(String agentId, String abilityName, String... params) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "god_ability");
        json.addProperty("agent_id", agentId);
        json.addProperty("ability", abilityName);

        JsonArray parameters = new JsonArray();
        for (String param : params) {
            parameters.add(param);
        }
        json.add("parameters", parameters);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/gods/ability");
    }

    /**
     * Command a god to transform
     */
    public static void godTransform(String agentId, String targetMob) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "god_transform");
        json.addProperty("agent_id", agentId);
        json.addProperty("target_mob", targetMob);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/gods/transform");
    }

    /**
     * Notify breeding event
     */
    public static void notifyBreeding(String parentAId, String parentBId,
                                      String parentAType, String parentBType) {
        JsonObject json = new JsonObject();
        json.addProperty("event", "breeding");
        json.addProperty("parent_a_id", parentAId);
        json.addProperty("parent_b_id", parentBId);
        json.addProperty("parent_a_type", parentAType);
        json.addProperty("parent_b_type", parentBType);
        json.addProperty("timestamp", System.currentTimeMillis());

        sendAsync(json, "/api/breeding/event");
    }

    /**
     * Notify a DW agent that it overheard a nearby chat message.
     * Called by ProximityChatHandler for every agent within PROXIMITY_RADIUS.
     * The Python cognitive loop receives this via /api/agents/chat_heard.
     *
     * @param hearerAgentId  clean name of the agent that heard the message
     * @param speakerName    display name of whoever spoke
     * @param message        the raw chat string
     */
    public static void notifyChatHeard(String hearerAgentId, String speakerName, String message) {
        JsonObject json = new JsonObject();
        json.addProperty("hearer_id",    hearerAgentId);
        json.addProperty("speaker_name", speakerName);
        json.addProperty("message",      message);
        json.addProperty("timestamp",    System.currentTimeMillis());
        sendAsync(json, "/api/agents/chat_heard");
    }

    private static void sendAsync(JsonObject json, String endpoint) {
        new Thread(() -> {
            try {
                // Generous timeout: 600 seconds for agent spawning, breeding, executable generation
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(BACKEND_URL + endpoint))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(json.toString()))
                        .timeout(java.time.Duration.ofSeconds(600))  // INCREASED: 10s → 600s
                        .build();

                HttpResponse<String> response = HTTP_CLIENT.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

                if (response.statusCode() == 200) {
                    DWMod.LOGGER.info("✅ Backend: {}", endpoint);
                } else {
                    DWMod.LOGGER.warn("⚠️ Backend {} - Status: {}",
                            endpoint, response.statusCode());
                }

            } catch (Exception e) {
                DWMod.LOGGER.error("Backend request failed {}: {}", endpoint, e.getMessage());
            }
        }, "DW-Backend-" + endpoint.replace("/", "-")).start();
    }
}
