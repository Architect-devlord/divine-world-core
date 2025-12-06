package com.divineworld.entity;

import com.divineworld.DWMod;
import com.google.gson.JsonObject;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraftforge.event.entity.living.BabyEntitySpawnEvent;

import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingEventHandler {

    private static final HttpClient HTTP_CLIENT = HttpClient.newHttpClient();
    private static final String PYTHON_BACKEND = "http://127.0.0.1:11400";

    private static final Map NPC_TRAITS = new HashMap<>();

    @SubscribeEvent
    public static void onBabySpawn(BabyEntitySpawnEvent event) {
        if (!(event.getParentA() instanceof DWNPCWithChat) ||
                !(event.getParentB() instanceof DWNPCWithChat)) {
            return;
        }

        DWNPCWithChat parentA = (DWNPCWithChat) event.getParentA();
        DWNPCWithChat parentB = (DWNPCWithChat) event.getParentB();

        PersonalityTraits traitsA = NPC_TRAITS.getOrDefault(
                parentA.getUUID(),
                PersonalityTraits.random()
        );
        PersonalityTraits traitsB = NPC_TRAITS.getOrDefault(
                parentB.getUUID(),
                PersonalityTraits.random()
        );

        PersonalityTraits childTraits = PersonalityTraits.inherit(traitsA, traitsB);

        if (event.getChild() instanceof Animal &&
                event.getCausedByPlayer() != null) {

            ServerLevel world = (ServerLevel) event.getChild().level();
            ServerPlayer breeder = (ServerPlayer) event.getCausedByPlayer();

            String childId = "npc_child_" + System.currentTimeMillis();

            DWMod.LOGGER.info("NPC breeding detected! Spawning child AI: " + childId);

            NPC_TRAITS.put(event.getChild().getUUID(), childTraits);

            CompletableFuture.runAsync(() -> {
                try {
                    spawnChildAI(childId, childTraits, world, parentA, parentB);
                } catch (Exception e) {
                    DWMod.LOGGER.error("Failed to spawn child AI: " + e.getMessage());
                }
            });

            breeder.sendSystemMessage(
                net.minecraft.network.chat.Component.literal(
                    "§6[DW] §eA new NPC AI (" + childId + ") is being created..."
                )
            );
        }
    }

    private static void spawnChildAI(String childId, PersonalityTraits traits,
                                     ServerLevel world, DWNPCWithChat parentA,
                                     DWNPCWithChat parentB) throws IOException, InterruptedException {

        JsonObject request = new JsonObject();
        request.addProperty("agent_id", childId);
        request.addProperty("spawn_type", "breeding");

        JsonObject persona = new JsonObject();
        persona.addProperty("curiosity", traits.curiosity);
        persona.addProperty("boldness", traits.boldness);
        persona.addProperty("sociability", traits.sociability);
        persona.addProperty("agreeableness", traits.agreeableness);
        persona.addProperty("conscientiousness", traits.conscientiousness);
        persona.addProperty("openness", traits.openness);
        persona.addProperty("neuroticism", traits.neuroticism);
        request.add("persona_traits", persona);

        JsonObject metadata = new JsonObject();
        metadata.addProperty("parent_a_id", parentA.getUUID().toString());
        metadata.addProperty("parent_a_name", parentA.getName().getString());
        metadata.addProperty("parent_b_id", parentB.getUUID().toString());
        metadata.addProperty("parent_b_name", parentB.getName().getString());
        metadata.addProperty("world", world.dimension().location().toString());
        metadata.addProperty("bred_at", System.currentTimeMillis());
        request.add("metadata", metadata);

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(PYTHON_BACKEND + "/api/agents/spawn"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(request.toString()))
                .build();

        HttpResponse response = HTTP_CLIENT.send(
                httpRequest,
                HttpResponse.BodyHandlers.ofString()
        );

        if (response.statusCode() == 200) {
            DWMod.LOGGER.info("✅ Child AI spawned successfully: " + childId);
        } else {
            DWMod.LOGGER.error("❌ Failed to spawn child AI: " + response.body());
        }
    }

    public static void registerNPCTraits(UUID npcId, PersonalityTraits traits) {
        NPC_TRAITS.put(npcId, traits);
    }

    public static PersonalityTraits getNPCTraits(UUID npcId) {
        return NPC_TRAITS.get(npcId);
    }

    public static class PersonalityTraits {
        public double curiosity;
        public double boldness;
        public double sociability;
        public double agreeableness;
        public double conscientiousness;
        public double openness;
        public double neuroticism;

        public PersonalityTraits(double curiosity, double boldness, double sociability,
                                 double agreeableness, double conscientiousness,
                                 double openness, double neuroticism) {
            this.curiosity = curiosity;
            this.boldness = boldness;
            this.sociability = sociability;
            this.agreeableness = agreeableness;
            this.conscientiousness = conscientiousness;
            this.openness = openness;
            this.neuroticism = neuroticism;
        }

        public static PersonalityTraits random() {
            return new PersonalityTraits(
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1,
                    Math.random() * 2 - 1
            );
        }

        public static PersonalityTraits inherit(PersonalityTraits a, PersonalityTraits b) {
            double MUTATION_RATE = 0.1;

            return new PersonalityTraits(
                    blend(a.curiosity, b.curiosity, MUTATION_RATE),
                    blend(a.boldness, b.boldness, MUTATION_RATE),
                    blend(a.sociability, b.sociability, MUTATION_RATE),
                    blend(a.agreeableness, b.agreeableness, MUTATION_RATE),
                    blend(a.conscientiousness, b.conscientiousness, MUTATION_RATE),
                    blend(a.openness, b.openness, MUTATION_RATE),
                    blend(a.neuroticism, b.neuroticism, MUTATION_RATE)
            );
        }

        private static double blend(double a, double b, double mutationRate) {
            double base = (a + b) / 2.0;
            double mutation = (Math.random() * 2 - 1) * mutationRate;
            return Math.max(-1.0, Math.min(1.0, base + mutation));
        }
    }
}