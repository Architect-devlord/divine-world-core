package com.divineworld.utils;

import com.divineworld.DWMod;
import org.apache.logging.log4j.Level;

/**
 * Small wrapper over mod logger so other classes can reference Logger.info/warn/debug safely.
 * If your DWMod exposes a different static logger, change DWMod.LOGGER below.
 */
public final class Logger {
    private Logger() {}

    public static void info(String s) {
        try { DWMod.LOGGER.info(s); } catch (Throwable t) { System.out.println("[DW INFO] " + s); }
    }

    public static void warn(String s) {
        try { DWMod.LOGGER.warn(s); } catch (Throwable t) { System.out.println("[DW WARN] " + s); }
    }

    public static void debug(String s) {
        try { DWMod.LOGGER.debug(s); } catch (Throwable t) { System.out.println("[DW DEBUG] " + s); }
    }

    public static void error(String s) {
        try { DWMod.LOGGER.error(s); } catch (Throwable t) { System.err.println("[DW ERROR] " + s); }
    }

    public static void log(Level level, String s) {
        try { DWMod.LOGGER.log(level, s); } catch (Throwable t) { System.out.println("[" + level + "] " + s); }
    }
}
