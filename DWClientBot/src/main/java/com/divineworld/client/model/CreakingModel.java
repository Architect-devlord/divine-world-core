// src/main/java/com/divineworld/client/model/CreakingModel.java
package com.divineworld.client.model;

import com.divineworld.client.entity.gods.AICreaking;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import net.minecraft.client.model.HierarchicalModel;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.model.geom.PartPose;
import net.minecraft.client.model.geom.builders.*;
import net.minecraft.world.entity.Entity;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

/**
 * Creaking Model - Custom entity for Minecraft 1.20.1
 * Tall, slender, tree-like entity with tentacles
 */
@OnlyIn(Dist.CLIENT)
public class CreakingModel<T extends AICreaking> extends HierarchicalModel<T> {

    private final ModelPart root;
    private final ModelPart body;
    private final ModelPart head;
    private final ModelPart leftArm;
    private final ModelPart rightArm;
    private final ModelPart leftLeg;
    private final ModelPart rightLeg;

    // Tentacles (4 animated appendages)
    private final ModelPart tentacle1;
    private final ModelPart tentacle2;
    private final ModelPart tentacle3;
    private final ModelPart tentacle4;

    public CreakingModel(ModelPart root) {
        this.root = root;
        this.body = root.getChild("body");
        this.head = body.getChild("head");
        this.leftArm = body.getChild("left_arm");
        this.rightArm = body.getChild("right_arm");
        this.leftLeg = root.getChild("left_leg");
        this.rightLeg = root.getChild("right_leg");

        this.tentacle1 = body.getChild("tentacle1");
        this.tentacle2 = body.getChild("tentacle2");
        this.tentacle3 = body.getChild("tentacle3");
        this.tentacle4 = body.getChild("tentacle4");
    }

    public static LayerDefinition createBodyLayer() {
        MeshDefinition meshdefinition = new MeshDefinition();
        PartDefinition partdefinition = meshdefinition.getRoot();

        // Body - Tall and slender (tree-like)
        PartDefinition body = partdefinition.addOrReplaceChild("body",
                CubeListBuilder.create()
                        .texOffs(0, 16)
                        .addBox(-4.0F, -12.0F, -2.0F, 8.0F, 24.0F, 4.0F),
                PartPose.offset(0.0F, 0.0F, 0.0F));

        // Head - Small, angular
        PartDefinition head = body.addOrReplaceChild("head",
                CubeListBuilder.create()
                        .texOffs(0, 0)
                        .addBox(-3.0F, -6.0F, -3.0F, 6.0F, 6.0F, 6.0F),
                PartPose.offset(0.0F, -12.0F, 0.0F));

        // Arms - Long, thin
        PartDefinition leftArm = body.addOrReplaceChild("left_arm",
                CubeListBuilder.create()
                        .texOffs(40, 16)
                        .addBox(0.0F, -2.0F, -1.0F, 2.0F, 16.0F, 2.0F),
                PartPose.offset(4.0F, -10.0F, 0.0F));

        PartDefinition rightArm = body.addOrReplaceChild("right_arm",
                CubeListBuilder.create()
                        .texOffs(40, 16)
                        .addBox(-2.0F, -2.0F, -1.0F, 2.0F, 16.0F, 2.0F),
                PartPose.offset(-4.0F, -10.0F, 0.0F));

        // Legs - Long, thin
        PartDefinition leftLeg = partdefinition.addOrReplaceChild("left_leg",
                CubeListBuilder.create()
                        .texOffs(0, 44)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 18.0F, 2.0F),
                PartPose.offset(2.0F, 6.0F, 0.0F));

        PartDefinition rightLeg = partdefinition.addOrReplaceChild("right_leg",
                CubeListBuilder.create()
                        .texOffs(0, 44)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 18.0F, 2.0F),
                PartPose.offset(-2.0F, 6.0F, 0.0F));

        // Tentacles - 4 flexible appendages from body
        PartDefinition tentacle1 = body.addOrReplaceChild("tentacle1",
                CubeListBuilder.create()
                        .texOffs(24, 0)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 12.0F, 2.0F),
                PartPose.offset(3.0F, 0.0F, 2.0F));

        PartDefinition tentacle2 = body.addOrReplaceChild("tentacle2",
                CubeListBuilder.create()
                        .texOffs(24, 0)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 12.0F, 2.0F),
                PartPose.offset(-3.0F, 0.0F, 2.0F));

        PartDefinition tentacle3 = body.addOrReplaceChild("tentacle3",
                CubeListBuilder.create()
                        .texOffs(24, 0)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 12.0F, 2.0F),
                PartPose.offset(3.0F, 0.0F, -2.0F));

        PartDefinition tentacle4 = body.addOrReplaceChild("tentacle4",
                CubeListBuilder.create()
                        .texOffs(24, 0)
                        .addBox(-1.0F, 0.0F, -1.0F, 2.0F, 12.0F, 2.0F),
                PartPose.offset(-3.0F, 0.0F, -2.0F));

        return LayerDefinition.create(meshdefinition, 64, 64);
    }

    @Override
    public void setupAnim(T entity, float limbSwing, float limbSwingAmount,
                          float ageInTicks, float netHeadYaw, float headPitch) {

        // Head rotation
        this.head.yRot = netHeadYaw * ((float)Math.PI / 180F);
        this.head.xRot = headPitch * ((float)Math.PI / 180F);

        // Leg animation (walking)
        this.rightLeg.xRot = (float) (Math.cos(limbSwing * 0.6662F) * 1.4F * limbSwingAmount);
        this.leftLeg.xRot = (float) (Math.cos(limbSwing * 0.6662F + Math.PI) * 1.4F * limbSwingAmount);

        // Arm swing
        this.rightArm.xRot = (float) (Math.cos(limbSwing * 0.6662F + Math.PI) * 2.0F * limbSwingAmount);
        this.leftArm.xRot = (float) (Math.cos(limbSwing * 0.6662F) * 2.0F * limbSwingAmount);

        // Tentacle animation (wave motion)
        float tentacleSwing = (float) Math.sin(ageInTicks * 0.1F);

        this.tentacle1.xRot = tentacleSwing * 0.3F;
        this.tentacle1.zRot = (float) Math.sin(ageInTicks * 0.15F) * 0.2F;

        this.tentacle2.xRot = tentacleSwing * 0.3F;
        this.tentacle2.zRot = (float) Math.sin(ageInTicks * 0.15F + Math.PI) * 0.2F;

        this.tentacle3.xRot = tentacleSwing * 0.3F;
        this.tentacle3.zRot = (float) Math.sin(ageInTicks * 0.15F + Math.PI * 0.5F) * 0.2F;

        this.tentacle4.xRot = tentacleSwing * 0.3F;
        this.tentacle4.zRot = (float) Math.sin(ageInTicks * 0.15F + Math.PI * 1.5F) * 0.2F;
    }

    @Override
    public void renderToBuffer(PoseStack poseStack, VertexConsumer buffer,
                               int packedLight, int packedOverlay,
                               float red, float green, float blue, float alpha) {
        root.render(poseStack, buffer, packedLight, packedOverlay, red, green, blue, alpha);
    }

    @Override
    public ModelPart root() {
        return this.root;
    }
}

