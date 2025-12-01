package com.divineworld.client;


import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;


/**
 * Handles periodic frame capture for the Divine World client bot.
 * Runs once per second (every 20 client ticks) and sends the frame to the backend.
 */
public class FrameCaptureHandler {

    private int tickCounter = 0;

    /**
     * Called before the client tick.
     */
    @SubscribeEvent
    public void onClientTickPre(TickEvent.ClientTickEvent.Pre event) {
        processTick();
    }

    /**
     * Called after the client tick.
     * You can optionally move processTick() here if you want post-tick capture.
     */
    // @SubscribeEvent
    // public void onClientTickPost(ClientTickEvent.Post event) {
    //     processTick();
    // }

    /**
     * Tick processing logic.
     * Captures a frame every 20 ticks (≈1 second) and sends to the backend.
     */
    private void processTick() {
        if (DWClientBot.AGENT_ID == null || DWClientBot.BACKEND == null) return;

        tickCounter++;
        if (tickCounter >= 20) { // ~1 second
            tickCounter = 0;
            FrameCapture.captureAndSend(DWClientBot.AGENT_ID, DWClientBot.BACKEND);
        }
    }
}
