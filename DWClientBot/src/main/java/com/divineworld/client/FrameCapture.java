package com.divineworld.client;

import com.mojang.blaze3d.systems.RenderSystem;
import net.minecraft.client.Minecraft;
import okhttp3.*;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL21;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FrameCapture {
    private static final Minecraft mc = Minecraft.getInstance();
    private static final OkHttpClient http = new OkHttpClient();
    private static final ExecutorService executor = Executors.newSingleThreadExecutor();

    // Persistent GPU PBO
    private static int pboId = -1;
    private static int lastWidth = -1;
    private static int lastHeight = -1;

    public static void captureAndSend(String agentId, String backendUrl) {
        mc.execute(() -> {
            try {
                int width = mc.getWindow().getWidth();
                int height = mc.getWindow().getHeight();
                if (width <= 0 || height <= 0) return;

                RenderSystem.assertOnRenderThread();

                // Initialize or resize PBO if needed
                if (pboId == -1 || width != lastWidth || height != lastHeight) {
                    if (pboId != -1) {
                        GL15.glDeleteBuffers(pboId);
                    }
                    pboId = GL15.glGenBuffers();
                    GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, pboId);
                    GL15.glBufferData(GL21.GL_PIXEL_PACK_BUFFER, width * height * 4L, GL15.GL_STREAM_READ);
                    GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
                    lastWidth = width;
                    lastHeight = height;
                }

                ByteBuffer buffer = BufferUtils.createByteBuffer(width * height * 4);

                boolean gpuSuccess = true;
                try {
                    GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, pboId);
                    GL11.glReadPixels(0, 0, width, height, GL11.GL_RGBA, GL11.GL_UNSIGNED_BYTE, 0);
                    GL15.glGetBufferSubData(GL21.GL_PIXEL_PACK_BUFFER, 0, buffer);
                    GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
                } catch (Throwable t) {
                    gpuSuccess = false;
                    GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
                    buffer.clear();
                    GL11.glReadPixels(0, 0, width, height, GL11.GL_RGBA, GL11.GL_UNSIGNED_BYTE, buffer);
                }

                buffer.rewind();
                executor.submit(() -> sendFrame(agentId, backendUrl, buffer, width, height));

            } catch (Throwable t) {
                t.printStackTrace();
            }
        });
    }

    private static void sendFrame(String agentId, String backendUrl, ByteBuffer buffer, int width, int height) {
        try {
            BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            for (int y = 0; y < height; y++) {
                for (int x = 0; x < width; x++) {
                    int i = (x + y * width) * 4;
                    int r = buffer.get(i) & 0xFF;
                    int g = buffer.get(i + 1) & 0xFF;
                    int b = buffer.get(i + 2) & 0xFF;
                    image.setRGB(x, height - 1 - y, (r << 16) | (g << 8) | b);
                }
            }

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            ImageIO.write(image, "png", baos);
            byte[] png = baos.toByteArray();

            RequestBody body = RequestBody.create(png, MediaType.get("image/png"));
            Request request = new Request.Builder()
                    .url(backendUrl + "/api/frame/" + agentId)
                    .post(body)
                    .build();

            http.newCall(request).enqueue(new Callback() {
                @Override public void onFailure(Call call, java.io.IOException e) { e.printStackTrace(); }
                @Override public void onResponse(Call call, Response response) { response.close(); }
            });

        } catch (Throwable t) {
            t.printStackTrace();
        }
    }
}
