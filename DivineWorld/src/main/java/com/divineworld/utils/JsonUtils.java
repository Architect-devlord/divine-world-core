package com.divineworld.utils;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextComponent; // for older MC versions adjust if needed

/**
 * Small JSON / text helpers used across the mod.
 * Minimal, safe, and will avoid NPEs where code expects JsonUtils.text(...)
 */
public final class JsonUtils {
    private JsonUtils() {}

    /**
     * Returns a Minecraft text Component from a string.
     * Use this instead of building Components inline to keep code consistent.
     */
    public static Component text(String s) {
        if (s == null) s = "";
        // For modern MC versions Component.literal is preferred,
        // but TextComponent is fairly compatible; swap if your MC mapping uses Component.literal
        try {
            // try preferred API if present
            return Component.literal(s);
        } catch (NoSuchMethodError | NoClassDefFoundError e) {
            // fallback to older constructor where available
            return new TextComponent(s);
        }
    }

    /**
     * Safe toString helper for objects used when building JSON manually.
     */
    public static String safeString(Object o) {
        return o == null ? "" : o.toString();
    }
}
