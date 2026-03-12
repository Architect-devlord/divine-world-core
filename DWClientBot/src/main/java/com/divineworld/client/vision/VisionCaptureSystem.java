package com.divineworld.client.vision;

import com.divineworld.client.DWClientMod;
import com.mojang.blaze3d.platform.NativeImage;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;

/**
 * Vision Capture System
 * Captures game screen for AI vision processing
 */
public class VisionCaptureSystem {
    private static int width = 640;
    private static int height = 480;
    private static float quality = 0.75f;

    private static NativeImage lastCapture = null;
    private static long lastCaptureTime = 0;
    private static final long CAPTURE_INTERVAL = 50; // 20 FPS max

    public static void initialize() {
        // Load config from system properties
        try {
            width = Integer.parseInt(System.getProperty("dw.vision.width", "640"));
            height = Integer.parseInt(System.getProperty("dw.vision.height", "480"));
            quality = Float.parseFloat(System.getProperty("dw.vision.quality", "0.75"));
        } catch (Exception e) {
            DWClientMod.LOGGER.warn("Failed to parse vision config, using defaults", e);
        }

        DWClientMod.LOGGER.info("Vision capture initialized: {}x{} @ {}", width, height, quality);

        // Initialise audio capture alongside vision
        AudioCaptureSystem.initialize();
    }

    /**
     * Capture screen as JPEG bytes
     * Must be called from render thread
     */
    public static byte[] captureScreenAsJPEG() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.getWindow() == null) return null;

        // Rate limiting
        long now = System.currentTimeMillis();
        if (now - lastCaptureTime < CAPTURE_INTERVAL) {
            return convertLastCaptureToJPEG();
        }
        lastCaptureTime = now;

        try {
            // Capture framebuffer
            int fbWidth = mc.getWindow().getWidth();
            int fbHeight = mc.getWindow().getHeight();

            NativeImage screenshot = Screenshot.takeScreenshot(mc.getMainRenderTarget());

            // Scale if needed
            if (fbWidth != width || fbHeight != height) {
                screenshot = scaleImage(screenshot, width, height);
            }

            lastCapture = screenshot;

            return convertToJPEG(screenshot);

        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to capture screen", e);
            return null;
        }
    }

    private static byte[] convertLastCaptureToJPEG() {
        if (lastCapture == null) return null;
        return convertToJPEG(lastCapture);
    }

    private static byte[] convertToJPEG(NativeImage image) {
        try {
            // Convert NativeImage to BufferedImage
            BufferedImage buffered = new BufferedImage(
                    image.getWidth(),
                    image.getHeight(),
                    BufferedImage.TYPE_INT_RGB
            );

            for (int y = 0; y < image.getHeight(); y++) {
                for (int x = 0; x < image.getWidth(); x++) {
                    int pixel = image.getPixelRGBA(x, y);
                    // Convert ABGR to RGB
                    int r = (pixel >> 0) & 0xFF;
                    int g = (pixel >> 8) & 0xFF;
                    int b = (pixel >> 16) & 0xFF;
                    int rgb = (r << 16) | (g << 8) | b;
                    buffered.setRGB(x, y, rgb);
                }
            }

            // Encode as JPEG
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            ImageIO.write(buffered, "JPEG", baos);
            return baos.toByteArray();

        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to convert to JPEG", e);
            return null;
        }
    }

    private static NativeImage scaleImage(NativeImage source, int targetWidth, int targetHeight) {
        NativeImage scaled = new NativeImage(targetWidth, targetHeight, false);

        float xRatio = (float) source.getWidth() / targetWidth;
        float yRatio = (float) source.getHeight() / targetHeight;

        for (int y = 0; y < targetHeight; y++) {
            for (int x = 0; x < targetWidth; x++) {
                int srcX = (int)(x * xRatio);
                int srcY = (int)(y * yRatio);
                int pixel = source.getPixelRGBA(srcX, srcY);
                scaled.setPixelRGBA(x, y, pixel);
            }
        }

        source.close();
        return scaled;
    }

    public static int getWidth() {
        return width;
    }

    public static int getHeight() {
        return height;
    }

    public static void cleanup() {
        if (lastCapture != null) {
            lastCapture.close();
            lastCapture = null;
        }
        AudioCaptureSystem.cleanup();
    }
}