package com.divineworld.oracle;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import okhttp3.*;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;

public class LLMOracleBrain {
    private String modelName;
    private String endpoint;
    private final OkHttpClient http;
    private final boolean isSecondOracle;

    public LLMOracleBrain(String modelName, String endpoint, boolean isSecondOracle) {
        this.modelName = modelName;
        this.endpoint = endpoint;
        this.http = new OkHttpClient();
        this.isSecondOracle = isSecondOracle;
    }

    public boolean isSecondOracle() { 
        return isSecondOracle; 
    }

    public void switchModel(String newModel, String newEndpoint) {
        this.modelName = newModel;
        this.endpoint = newEndpoint;
    }

    public String getModelName() { return modelName; }

    /**
     * Query asynchronously and callback on the main server thread
     */
    public void queryAsync(MinecraftServer server, String prompt, Consumer<String> callback) {
        JsonObject json = new JsonObject();
        json.addProperty("model", modelName);
        json.addProperty("prompt", prompt);

        RequestBody body = RequestBody.create(json.toString(), MediaType.get("application/json; charset=utf-8"));
        Request request = new Request.Builder().url(endpoint + "/v1/generate").post(body).build();

        http.newCall(request).enqueue(new Callback() {
            @Override public void onFailure(Call call, IOException e) {
                server.submit(() -> callback.accept("§c[Oracle Error] Could not reach model: " + e.getMessage()));
            }

            @Override public void onResponse(Call call, Response response) throws IOException {
                String answer;
                try (response) {
                    if (!response.isSuccessful()) throw new IOException("HTTP " + response.code());
                    answer = response.body().string().trim();
                    if (answer.isEmpty()) answer = "§c[Oracle Error] Empty response from model.";
                } catch (Exception ex) {
                    answer = "§c[Oracle Error] " + ex.getMessage();
                }
                final String finalAnswer = answer;
                server.submit(() -> callback.accept(finalAnswer));
            }
        });
    }

    /**
     * Optional: return CompletableFuture if you want chaining
     */
    public CompletableFuture<String> query(String prompt) {
        CompletableFuture<String> cf = new CompletableFuture<>();
        http.newCall(new Request.Builder()
                .url(endpoint + "/v1/generate")
                .post(RequestBody.create("{\"model\":\"" + modelName + "\",\"prompt\":\"" + prompt + "\"}",
                        MediaType.get("application/json; charset=utf-8"))).build())
                .enqueue(new Callback() {
                    @Override public void onFailure(Call call, IOException e) { cf.completeExceptionally(e); }
                    @Override public void onResponse(Call call, Response response) throws IOException {
                        try (response) { cf.complete(response.body().string()); }
                    }
                });
        return cf;
    }
}
