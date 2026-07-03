// src/main/java/com/divineworld/client/render/GodEntityRenderer.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.render;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.BaseGodEntity;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.PlayerModel;
import net.minecraft.client.model.geom.ModelLayers;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.client.renderer.entity.layers.*;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

/**
 * God Entity Renderer — three-way form dispatch.
 *
 * Three forms are possible (stored in NBT key "dw_form" on the player puppet):
 *
 *   "god"      The real boss body (vanilla entity, spawned by GodSpawnHandler).
 *              The player puppet is INVISIBLE (setInvisible(true)) — nothing
 *              to render here.  GodEntityRenderer is still registered for the
 *              puppet's EntityType in case the puppet ever flickers visible;
 *              in that case it renders as the god_default texture at full scale.
 *              Creaking's "god" form is handled by CreakingGeoRenderer registered
 *              separately for ModEntities.AI_CREAKING.
 *
 *   "humanoid" The player puppet is VISIBLE (setInvisible(false)).  This renderer
 *              delegates to a per-instance GodHumanoidGeoRenderer, which drives the
 *              god_*.geo.json / god_*.png / god_*.animation.json trio.  Scale is
 *              always 1.0× regardless of god type.  All god abilities work the same
 *              way in this form — useAbility() triggers the same animation names
 *              defined in the humanoid animation.json.
 *
 *   "disguise" The player puppet is VISIBLE at 1.0× with a vanilla player skin
 *              (Steve or Alex chosen randomly at disguise-entry time, stored in
 *              "dw_steve_or_alex" NBT).  PlayerModel path, same as before.
 *
 * RENDERER COMPOSITION — why the delegate rather than a registered GeoEntityRenderer:
 *   Forge's EntityRenderers.register() maps EntityType → renderer factory at load time
 *   and cannot be changed at runtime.  We can't swap renderers when a god changes form.
 *   Instead, GodEntityRenderer holds a lazily-initialised GodHumanoidGeoRenderer
 *   instance (constructed with the same EntityRendererProvider.Context) and calls its
 *   render() method directly for the humanoid path.  GeckoLib's render pipeline
 *   operates on the entity instance passed to render(), so the same entity object
 *   can be rendered by either path — there is no entity-type coupling at render time.
 */
@OnlyIn(Dist.CLIENT)
public class GodEntityRenderer extends LivingEntityRenderer<Player, PlayerModel<Player>> {

    private static final ResourceLocation DEFAULT_GOD_SKIN =
            new ResourceLocation(DWClientMod.MOD_ID, "textures/entity/god_default.png");

    // ── Humanoid GeckoLib delegate ──────────────────────────────────────────
    // Lazily initialised on first humanoid render.  A single instance is shared
    // across every render call for this renderer — GeoEntityRenderer is
    // stateless per render call (all animation state lives on the entity's
    // AnimatableInstanceCache, which is per-entity, not per-renderer).
    // Using a raw-typed reference because the generic T is BaseGodEntity and
    // GodEntityRenderer is parameterised on Player.  The cast inside
    // renderHumanoidForm() is safe whenever dw_form=humanoid, since only
    // BaseGodEntity subclasses ever get that flag set by GodFormToggleHandler.
    @SuppressWarnings("rawtypes")
    private GodHumanoidGeoRenderer humanoidDelegate;

    private final EntityRendererProvider.Context savedContext;

    public GodEntityRenderer(EntityRendererProvider.Context context) {
        super(context, new PlayerModel<>(context.bakeLayer(ModelLayers.PLAYER), false), 0.5F);
        this.savedContext = context;

        this.addLayer(new HumanoidArmorLayer<>(this,
                new net.minecraft.client.model.HumanoidModel<>(context.bakeLayer(ModelLayers.PLAYER_INNER_ARMOR)),
                new net.minecraft.client.model.HumanoidModel<>(context.bakeLayer(ModelLayers.PLAYER_OUTER_ARMOR)),
                context.getModelManager()));
        this.addLayer(new ItemInHandLayer<>(this, context.getItemInHandRenderer()));
        this.addLayer(new ArrowLayer<>(context, this));
        this.addLayer(new CustomHeadLayer<>(this, context.getModelSet(), context.getItemInHandRenderer()));
        this.addLayer(new ElytraLayer<>(this, context.getModelSet()));
        this.addLayer(new GodGlowLayer(this));
    }

    // =========================================================================
    // Form detection helpers
    // =========================================================================

    private static final String FORM_GOD      = "god";
    private static final String FORM_HUMANOID = "humanoid";
    private static final String FORM_DISGUISE = "disguise";

    private static String getForm(Player entity) {
        String form = entity.getPersistentData().getString("dw_form");
        return (form == null || form.isEmpty()) ? FORM_GOD : form;
    }

    private static boolean isHumanoidForm(Player entity) {
        return FORM_HUMANOID.equals(getForm(entity));
    }

    private static boolean isDisguiseForm(Player entity) {
        return FORM_DISGUISE.equals(getForm(entity));
    }

    // =========================================================================
    // Texture selection
    // =========================================================================

    @Override
    public ResourceLocation getTextureLocation(Player entity) {
        if (isDisguiseForm(entity)) {
            // Steve (wide/classic) or Alex (slim) chosen randomly at disguise-entry time
            // by GodDisguiseHandler.applyGodForm() and stored as a boolean in NBT.
            // dw_is_steve = true  → Steve — textures/entity/player/wide/steve.png
            // dw_is_steve = false → Alex  — textures/entity/player/slim/alex.png
            // These are vanilla Minecraft's own default player skin textures —
            // available in every 1.20.1 jar without any asset copy needed.
            boolean isSteve = entity.getPersistentData().getBoolean("dw_is_steve");
            return isSteve
                ? new ResourceLocation("minecraft",
                      "textures/entity/player/wide/steve.png")
                : new ResourceLocation("minecraft",
                      "textures/entity/player/slim/alex.png");
        }
        // Humanoid and god forms both use the per-type god skin for the
        // PlayerModel fallback (the humanoid geo path overrides texture via
        // GeoModel.getTextureResource(); this is only reached if GeoModel
        // lookup fails or we're in the god form nameplate-only path).
        String godType = entity.getPersistentData().getString("dw_god_type");
        if (godType != null && !godType.isEmpty()) {
            return new ResourceLocation(DWClientMod.MOD_ID,
                    "textures/entity/god_" + godType + ".png");
        }
        return DEFAULT_GOD_SKIN;
    }

    // =========================================================================
    // Main render — dispatches by form
    // =========================================================================

    @Override
    public void render(Player entity, float entityYaw, float partialTicks,
                       PoseStack poseStack, MultiBufferSource buffer, int packedLight) {

        if (!entity.getPersistentData().contains("dw_god")) {
            // Not a god puppet — render as normal player, no special handling
            super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);
            return;
        }

        String form = getForm(entity);

        switch (form) {
            case FORM_HUMANOID -> renderHumanoidForm(entity, entityYaw, partialTicks,
                    poseStack, buffer, packedLight);
            case FORM_DISGUISE -> renderDisguiseForm(entity, entityYaw, partialTicks,
                    poseStack, buffer, packedLight);
            default            -> {
                // GOD form — puppet is invisible server-side; only render nameplate
                renderGodNameplate(entity, poseStack, buffer, packedLight);
            }
        }
    }

    // ─── Humanoid form ───────────────────────────────────────────────────────

    /** Public entry-point for CreakingGeoRenderer's delegation. */
    @SuppressWarnings("unchecked")
    public void renderHumanoidFormPublic(Object entity, float entityYaw, float partialTick,
                                          PoseStack poseStack, MultiBufferSource buffer,
                                          int packedLight) {
        if (entity instanceof Player p) {
            renderHumanoidForm(p, entityYaw, partialTick, poseStack, buffer, packedLight);
        }
    }

    @SuppressWarnings("unchecked")
    private void renderHumanoidForm(Player entity, float entityYaw, float partialTicks,
                                     PoseStack poseStack, MultiBufferSource buffer,
                                     int packedLight) {
        if (!(entity instanceof BaseGodEntity godEntity)) {
            // Fallback: render as PlayerModel if entity is not a BaseGodEntity
            // (shouldn't happen in normal gameplay — only BaseGodEntity subclasses
            // ever get dw_form=humanoid set by GodFormToggleHandler).
            poseStack.pushPose();
            super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);
            poseStack.popPose();
            return;
        }

        // Lazily initialise the GeckoLib delegate the first time it's needed
        if (humanoidDelegate == null) {
            humanoidDelegate = new GodHumanoidGeoRenderer<>(savedContext);
        }

        // Humanoid form is always at 1.0× scale
        poseStack.pushPose();
        humanoidDelegate.renderAsHumanoid(
                godEntity, entityYaw, partialTicks, poseStack, buffer, packedLight);
        poseStack.popPose();

        renderGodNameplate(entity, poseStack, buffer, packedLight);
    }

    // ─── Disguise form (Steve / Alex) ─────────────────────────────────────

    /** Public entry-point for CreakingGeoRenderer's delegation. */
    public void renderDisguiseFormPublic(Object entity, float entityYaw, float partialTick,
                                          PoseStack poseStack, MultiBufferSource buffer,
                                          int packedLight) {
        if (entity instanceof Player p) {
            renderDisguiseForm(p, entityYaw, partialTick, poseStack, buffer, packedLight);
        }
    }

    private void renderDisguiseForm(Player entity, float entityYaw, float partialTicks,
                                     PoseStack poseStack, MultiBufferSource buffer,
                                     int packedLight) {
        // Always 1.0× scale, no nameplate — indistinguishable from a normal player
        poseStack.pushPose();
        super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);
        poseStack.popPose();
    }

    // ─── Scale helper (used by god form if the puppet ever becomes visible) ──

    private float getGodScale(Player entity) {
        if (!FORM_GOD.equals(getForm(entity))) return 1.0f;
        String godType = entity.getPersistentData().getString("dw_god_type");
        return switch (godType == null ? "" : godType) {
            case "ender_dragon" -> 4.0f;
            case "wither"       -> 1.8f;
            case "warden"       -> 1.5f;
            case "elder_guardian" -> 2.0f;
            case "creaking"     -> 1.2f;
            case "oracle"       -> 1.0f;
            default             -> 1.0f;
        };
    }

    // =========================================================================
    // Nameplate (shown in god and humanoid forms, hidden in disguise)
    // =========================================================================

    private void renderGodNameplate(Player entity, PoseStack poseStack,
                                     MultiBufferSource buffer, int packedLight) {
        if (!entity.getPersistentData().contains("dw_god")) return;
        if (isDisguiseForm(entity)) return;   // stealth form — no nameplate

        String godType = entity.getPersistentData().getString("dw_god_type");
        if (godType == null || godType.isEmpty()) return;

        poseStack.pushPose();
        poseStack.translate(0.0D, entity.getBbHeight() + 0.5D, 0.0D);
        poseStack.mulPose(this.entityRenderDispatcher.cameraOrientation());
        float scale = 0.025f;
        poseStack.scale(-scale, -scale, scale);

        var font = this.getFont();
        String text = "§5[" + godType.toUpperCase() + " GOD]";
        float x = -font.width(text) / 2.0f;
        font.drawInBatch(text, x, 0, 0xFFFFFF, false,
                poseStack.last().pose(), buffer,
                net.minecraft.client.gui.Font.DisplayMode.NORMAL,
                0, packedLight);
        poseStack.popPose();
    }

    // =========================================================================
    // Glow layer — suppressed in disguise form
    // =========================================================================

    private static class GodGlowLayer extends RenderLayer<Player, PlayerModel<Player>> {
        public GodGlowLayer(GodEntityRenderer renderer) { super(renderer); }

        @Override
        public void render(PoseStack poseStack, MultiBufferSource buffer, int packedLight,
                           Player entity, float limbSwing, float limbSwingAmount,
                           float partialTicks, float ageInTicks, float netHeadYaw, float headPitch) {
            if (!entity.getPersistentData().contains("dw_god")) return;
            if (isDisguiseForm(entity)) return;
            // Emissive / particle glow — implementation deferred to visual polish pass
        }
    }
}