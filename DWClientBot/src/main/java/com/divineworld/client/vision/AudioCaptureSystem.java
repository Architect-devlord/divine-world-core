package com.divineworld.client.vision;

import com.divineworld.client.DWClientMod;
import org.lwjgl.openal.AL10;
import org.lwjgl.openal.ALC10;
import org.lwjgl.openal.ALC11;

import javax.sound.sampled.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ShortBuffer;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Audio Capture System
 *
 * Captures Minecraft's rendered audio output so AI agents can "hear"
 * the game world just as a player would — footsteps, mob sounds,
 * ambient effects, music, etc.
 *
 * Strategy:
 *   Minecraft uses OpenAL for all game audio. We open a secondary
 *   "loopback" capture device via ALC_EXT_capture (ALC11) so we record
 *   exactly what OpenAL has already mixed and is about to play, without
 *   touching the normal playback path.
 *
 *   If ALC capture is unavailable (e.g. some Linux drivers) we fall back
 *   to Java's javax.sound.sampled TargetDataLine which captures from the
 *   system-default loopback monitor.
 *
 * Output format: 16-bit signed PCM, mono, 22 050 Hz, little-endian.
 *   Compact enough for ~20 FPS transmission yet rich enough for an AI to
 *   distinguish meaningful game sounds.
 *
 * The bytes returned by {@link #captureAudioFrame()} are inserted directly
 * into the perception frame built by {@link com.divineworld.client.network.WebSocketManager}.
 *
 */
public class AudioCaptureSystem {

    // ── Configuration ─────────────────────────────────────────────────
    private static final int SAMPLE_RATE     = 22_050; // Hz
    private static final int CHANNELS        = 1;      // mono
    private static final int BITS_PER_SAMPLE = 16;     // signed PCM

    /** Samples collected per perception tick (≈50 ms at 20 fps). */
    private static final int SAMPLES_PER_TICK = SAMPLE_RATE / 20; // 1 102 samples = 2 204 bytes

    // ── OpenAL capture handle ─────────────────────────────────────────
    private static long    captureDevice = 0L;
    private static boolean usingAlc      = false;

    // ── Fallback: javax.sound ─────────────────────────────────────────
    private static TargetDataLine     fallbackLine = null;
    private static final AtomicBoolean running     = new AtomicBoolean(false);

    /** Reusable scratch buffer (2 bytes per 16-bit sample). */
    private static final byte[] scratchBytes = new byte[SAMPLES_PER_TICK * 2];

    // ─────────────────────────────────────────────────────────────────

    /**
     * Initialise the capture pipeline.
     * Call once during mod client setup (e.g. from VisionCaptureSystem.initialize()).
     */
    public static void initialize() {
        if (tryInitALC()) {
            DWClientMod.LOGGER.info(
                "[AudioCapture] ALC loopback capture active — {} Hz, mono, 16-bit", SAMPLE_RATE);
            usingAlc = true;
        } else {
            DWClientMod.LOGGER.warn(
                "[AudioCapture] ALC capture unavailable, trying javax.sound fallback");
            usingAlc = false;
            tryInitJavaxSound();
        }

        running.set(captureDevice != 0L || fallbackLine != null);

        if (!running.get()) {
            DWClientMod.LOGGER.warn(
                "[AudioCapture] No audio capture available — perception frames will have silent audio");
        }
    }

    // ── OpenAL capture path ───────────────────────────────────────────

    /**
     * Attempt to open an ALC capture (loopback) device.
     * Passing NULL selects the driver's default capture endpoint, which
     * on most systems is the loopback/monitor of the current output device.
     */
    private static boolean tryInitALC() {
        try {
            captureDevice = ALC11.alcCaptureOpenDevice(
                    (ByteBuffer) null,          // NULL = default capture device
                    SAMPLE_RATE,
                    AL10.AL_FORMAT_MONO16,
                    SAMPLES_PER_TICK * 4        // ring-buffer: 4× tick size for safety
            );

            if (captureDevice == 0L) {
                return false;
            }

            ALC11.alcCaptureStart(captureDevice);
            int err = ALC10.alcGetError(captureDevice);
            if (err != ALC10.ALC_NO_ERROR) {
                DWClientMod.LOGGER.warn("[AudioCapture] ALC error after captureStart: {}", err);
                ALC11.alcCaptureCloseDevice(captureDevice);
                captureDevice = 0L;
                return false;
            }
            return true;

        } catch (Throwable t) {
            // LWJGL may throw if the ALC extension is absent
            DWClientMod.LOGGER.debug("[AudioCapture] ALC init error: {}", t.getMessage());
            captureDevice = 0L;
            return false;
        }
    }

    // ── javax.sound fallback ──────────────────────────────────────────

    private static void tryInitJavaxSound() {
        AudioFormat fmt = new AudioFormat(
                SAMPLE_RATE,
                BITS_PER_SAMPLE,
                CHANNELS,
                true,   // signed
                false   // little-endian
        );
        DataLine.Info info = new DataLine.Info(TargetDataLine.class, fmt);

        if (!AudioSystem.isLineSupported(info)) {
            DWClientMod.LOGGER.warn("[AudioCapture] javax.sound TargetDataLine not supported");
            return;
        }

        try {
            fallbackLine = (TargetDataLine) AudioSystem.getLine(info);
            fallbackLine.open(fmt, scratchBytes.length * 4);
            fallbackLine.start();
            DWClientMod.LOGGER.info("[AudioCapture] javax.sound fallback active");
        } catch (LineUnavailableException e) {
            DWClientMod.LOGGER.warn("[AudioCapture] Cannot open fallback audio line: {}", e.getMessage());
            fallbackLine = null;
        }
    }

    // ── Public API ────────────────────────────────────────────────────

    /**
     * Capture one perception-tick worth of audio.
     *
     * <p>Should be called from the same thread as
     * {@link VisionCaptureSystem#captureScreenAsJPEG()} (the main game thread).
     *
     * @return Raw 16-bit signed PCM bytes (little-endian, mono, 22 050 Hz).
     *         Returns an empty array when capture is unavailable or no new
     *         samples have accumulated since the last call.
     */
    public static byte[] captureAudioFrame() {
        if (!running.get()) return new byte[0];

        if (usingAlc && captureDevice != 0L) {
            return captureFromALC();
        }
        if (fallbackLine != null) {
            return captureFromJavaxSound();
        }
        return new byte[0];
    }

    // ── ALC capture ───────────────────────────────────────────────────

    private static byte[] captureFromALC() {
        try {
            // How many samples does ALC have ready?
            int[] available = new int[1];
            ALC10.alcGetIntegerv(captureDevice, ALC11.ALC_CAPTURE_SAMPLES, available);

            int toRead = Math.min(available[0], SAMPLES_PER_TICK);
            if (toRead <= 0) return new byte[0];

            // alcCaptureSamples writes interleaved 16-bit shorts.
            // Wrap our scratch byte array as a ShortBuffer so LWJGL is happy.
            ShortBuffer sb = ByteBuffer
                    .wrap(scratchBytes, 0, toRead * 2)
                    .order(ByteOrder.LITTLE_ENDIAN)
                    .asShortBuffer();

            ALC11.alcCaptureSamples(captureDevice, sb, toRead);

            if (ALC10.alcGetError(captureDevice) != ALC10.ALC_NO_ERROR) {
                return new byte[0];
            }

            byte[] result = new byte[toRead * 2];
            System.arraycopy(scratchBytes, 0, result, 0, result.length);
            return result;

        } catch (Throwable t) {
            DWClientMod.LOGGER.error("[AudioCapture] ALC read error", t);
            return new byte[0];
        }
    }

    // ── javax.sound capture ───────────────────────────────────────────

    private static byte[] captureFromJavaxSound() {
        try {
            int available = fallbackLine.available();
            if (available <= 0) return new byte[0];

            int toRead = Math.min(available, scratchBytes.length);
            int read   = fallbackLine.read(scratchBytes, 0, toRead);
            if (read <= 0) return new byte[0];

            byte[] result = new byte[read];
            System.arraycopy(scratchBytes, 0, result, 0, read);
            return result;

        } catch (Throwable t) {
            DWClientMod.LOGGER.error("[AudioCapture] javax.sound read error", t);
            return new byte[0];
        }
    }

    // ── Metadata ──────────────────────────────────────────────────────

    /** Sample rate of the returned PCM data (22 050 Hz). */
    public static int getSampleRate()    { return SAMPLE_RATE; }

    /** Channel count (always 1 = mono). */
    public static int getChannels()      { return CHANNELS; }

    /** Bits per sample (always 16). */
    public static int getBitsPerSample() { return BITS_PER_SAMPLE; }

    /** Whether capture is currently active. */
    public static boolean isActive()     { return running.get(); }

    // ── Shutdown ──────────────────────────────────────────────────────

    /**
     * Release all audio resources.
     * Called automatically by {@link VisionCaptureSystem#cleanup()}.
     */
    public static void cleanup() {
        running.set(false);

        if (usingAlc && captureDevice != 0L) {
            try {
                ALC11.alcCaptureStop(captureDevice);
                ALC11.alcCaptureCloseDevice(captureDevice);
            } catch (Throwable ignored) {}
            captureDevice = 0L;
        }

        if (fallbackLine != null) {
            try { fallbackLine.stop();  } catch (Throwable ignored) {}
            try { fallbackLine.close(); } catch (Throwable ignored) {}
            fallbackLine = null;
        }

        DWClientMod.LOGGER.info("[AudioCapture] Shutdown complete");
    }
}