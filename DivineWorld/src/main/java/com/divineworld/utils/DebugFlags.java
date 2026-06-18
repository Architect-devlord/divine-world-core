// src/main/java/com/divineworld/utils/DebugFlags.java
// DivineWorld server mod
package com.divineworld.utils;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

public final class DebugFlags {
    private static final Set<UUID> ACTIONBAR = new HashSet<>();

    public static boolean isActionbarEnabled(UUID id) { return ACTIONBAR.contains(id); }

    public static boolean toggleActionbar(UUID id) {
        if (ACTIONBAR.contains(id)) {
            ACTIONBAR.remove(id); return false;
        } else {
            ACTIONBAR.add(id); return true;
        }
    }
}
