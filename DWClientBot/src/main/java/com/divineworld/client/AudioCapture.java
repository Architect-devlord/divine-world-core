package com.divineworld.client;

import net.minecraftforge.client.event.sound.PlaySoundEvent;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import okhttp3.*;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

public class AudioCapture {
    private static final OkHttpClient http = new OkHttpClient();
    private static final Minecraft mc = Minecraft.getInstance();

    @SubscribeEvent
    public void onPlaySound(PlaySoundEvent evt) {
        try {
            if (mc.player == null || evt.getSound() == null) return;

            String name = evt.getSound().getLocation().toString();
            String agentId = DWClientBot.AGENT_ID;
            String backend = DWClientBot.BACKEND;

            if (agentId == null || backend == null) return;

            // Try to load raw OGG from resources
            ResourceLocation soundLoc = evt.getSound().getLocation();
            String path = "sounds/" + soundLoc.getPath() + ".ogg";

            try {
                // Use factory method instead of constructor
                ResourceLocation resourcePath = ResourceLocation.fromNamespaceAndPath(soundLoc.getNamespace(), path);

                InputStream is = mc.getResourceManager().getResource(resourcePath)
                        .orElseThrow().open();

                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                byte[] buf = new byte[4096];
                int r;
                while ((r = is.read(buf)) > 0) {
                    baos.write(buf, 0, r);
                }
                is.close();
                byte[] ogg = baos.toByteArray();

                RequestBody body = RequestBody.create(ogg, MediaType.get("audio/ogg"));
                Request req = new Request.Builder()
                        .url(backend + "/api/audio/" + agentId)
                        .post(body)
                        .build();
                http.newCall(req).enqueue(new Callback() {
                    @Override public void onFailure(Call call, java.io.IOException e) {}
                    @Override public void onResponse(Call call, Response response) { response.close(); }
                });
                return;
            } catch (Exception e) {
                // Fall back to metadata if raw OGG fails
            }

            // Fallback: send JSON metadata
            String json = "{\"sound\":\"" + name + "\"}";
            RequestBody body = RequestBody.create(json, MediaType.get("application/json"));
            Request req = new Request.Builder()
                    .url(backend + "/api/audio_meta/" + agentId)
                    .post(body)
                    .build();
            http.newCall(req).enqueue(new Callback() {
                @Override public void onFailure(Call call, java.io.IOException e) {}
                @Override public void onResponse(Call call, Response response) { response.close(); }
            });
        } catch (Throwable t) {
            t.printStackTrace();
        }
    }
}
