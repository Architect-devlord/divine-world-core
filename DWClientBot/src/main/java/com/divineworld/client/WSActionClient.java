package com.divineworld.client;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.divineworld.network.ClientNetworkHandler;
import com.divineworld.client.network.ChatSayPacket;
import net.minecraft.client.Minecraft;

import java.net.URI;

public class WSActionClient {
    private static WebSocketClient ws;
    private static final Gson gson = new Gson();

    public static void start(String agentId, String wsUrl) {
        try {
            ws = new WebSocketClient(new URI(wsUrl)) {
                @Override
                public void onOpen(ServerHandshake handshakedata) {
                    System.out.println("[DWClientBot][WS] Connected");
                    JsonObject reg = new JsonObject();
                    reg.addProperty("type", "register");
                    reg.addProperty("agent", agentId);
                    send(reg.toString());
                }
                
                @Override
                public void onMessage(String message) {
                    try {
                        JsonObject obj = gson.fromJson(message, JsonObject.class);
                        String type = obj.has("type") ? obj.get("type").getAsString() : "";
                        
                        if ("action".equals(type)) {
                            String target = obj.has("agent") ? obj.get("agent").getAsString() : "";
                            if (agentId.equals(target) && obj.has("action")) {
                                if (obj.get("action").isJsonPrimitive()) {
                                    ActionExecutor.applyAction(obj.get("action").getAsString());
                                } else {
                                    ActionExecutor.applyActionJson(obj.getAsJsonObject("action"));
                                }
                            }
                        }
                        else if ("say".equals(type)) {
                            String msg = obj.has("message") ? obj.get("message").getAsString() : "";
                            String msgAgentId = obj.has("agent") ? obj.get("agent").getAsString() : "";

                            // Show bubble locally
                            Minecraft.getInstance().execute(() -> {
                                ChatBubbleManager.showAgentMessage(msgAgentId, msg);
                            });

                            // Send to server so everyone sees it
                            ChatSayPacket packet = new ChatSayPacket(msgAgentId, msg);
                            ClientNetworkHandler.INSTANCE.sendToServer(packet);
                        }

                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }
                
                @Override
                public void onClose(int code, String reason, boolean remote) {
                    System.out.println("[DWClientBot][WS] Closed: " + reason);
                }
                
                @Override
                public void onError(Exception ex) {
                    ex.printStackTrace();
                }
            };
            ws.connect();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    public static void send(String s) {
        if (ws != null && ws.isOpen()) {
            ws.send(s);
        }
    }
}