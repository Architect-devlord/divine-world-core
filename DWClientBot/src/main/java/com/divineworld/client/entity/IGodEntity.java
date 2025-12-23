package com.divineworld.client.entity;

/**
 * Interface for all god entities
 * Defines common abilities that all god types must implement
 */
public interface IGodEntity {
    /**
     * Use a god-specific ability
     * @param abilityName Name of the ability to use
     * @param params Additional parameters for the ability
     */
    void useAbility(String abilityName, Object... params);

    /**
     * Toggle flight mode (if supported by this god type)
     * @param enable true to enable flight, false to disable
     */
    void toggleFlight(boolean enable);

    /**
     * Add player inventory capabilities to this entity
     * Gods can use items like players
     */
    void addPlayerInventory();

    /**
     * Check if this god is currently in player form
     * @return true if in player form, false if in god form
     */
    default boolean isInPlayerForm() {
        return false;
    }

    /**
     * Get the god type identifier
     * @return God type (e.g., "creaking", "ender_dragon")
     */
    default String getGodType() {
        return "unknown";
    }
}