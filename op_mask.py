import bpy
import bmesh
import numpy as np
from bpy.types import Operator, Panel
from bpy.props import BoolProperty
import time


class Mio3Debug:
    _start_time = 0

    def start_time(self):
        self._start_time = time.time()

    def print_time(self):
        # print("Time: {:.5f}".format(time.time() - self._start_time))
        pass


class Mio3SclputOperator(Mio3Debug):
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "SCULPT"

    @staticmethod
    def get_maks_layer(bm):
        mask_layer = bm.verts.layers.float.get(".sculpt_mask")
        if not mask_layer:
            mask_layer = bm.verts.layers.float.new(".sculpt_mask")
        return mask_layer

    @staticmethod
    def use_multires(obj):
        for mod in obj.modifiers:
            if mod.type == "MULTIRES" and mod.show_viewport and mod.sculpt_levels >= 1:
                return True
        return False

    @staticmethod
    def store_multires(obj):
        multires = None
        for mod in obj.modifiers:
            if mod.type == "MULTIRES":
                multires = (mod, int(mod.sculpt_levels))
                break
        obj.data.update()
        return multires

    @staticmethod
    def restore_multires(multires):
        pass
        # if multires is not None:
        #     mod, sculpt_levels = multires
        #     mod.sculpt_levels = sculpt_levels


class PAINT_OT_mio3sc_mask_from_selection(Mio3SclputOperator, Operator):
    bl_idname = "paint.mio3sc_mask_from_selection"
    bl_label = "Selection Mesh"
    bl_description = "Create mask from selected mesh in edit mode\n[Shift] Add\n[Alt] Remove\n[Ctrl] Invert"
    bl_options = {"REGISTER", "UNDO"}
    invert: BoolProperty(name="Invert", default=False, options={"SKIP_SAVE", "HIDDEN"})
    clear: BoolProperty(name="Clear", default=False, options={"SKIP_SAVE", "HIDDEN"})
    add: BoolProperty(name="Add", default=False, options={"SKIP_SAVE", "HIDDEN"})

    def invoke(self, context, event):
        if event.shift:
            self.add = True
        if event.ctrl:
            self.invert = True
        if event.alt:
            self.clear = True
        bpy.ops.ed.undo_push(message="Mio3 Sculpt")
        return self.execute(context)

    def execute(self, context):
        self.start_time()
        obj = context.active_object

        if not self.add and not self.clear:
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0)

        if self.use_multires(obj):
            p_len = len(obj.data.polygons)
            p_sel = np.empty(p_len, dtype=bool)
            obj.data.polygons.foreach_get("select", p_sel)
            p_sel = p_sel if self.invert else ~p_sel
            obj.data.polygons.foreach_set("hide", p_sel.astype(np.uint8))
            multires = self.store_multires(obj)
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0 if self.clear else 1)
            bpy.ops.paint.hide_show_all(action="SHOW")
            self.restore_multires(multires)
        else:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            mask_layer = self.get_maks_layer(bm)
            v_len = len(obj.data.vertices)
            v_sel = np.empty(v_len, dtype=bool)
            obj.data.vertices.foreach_get("select", v_sel)
            (target_indices,) = np.where(v_sel)
            mask_value = 0 if self.clear else 1
            for idx in target_indices:
                bm.verts[idx][mask_layer] = mask_value
            bm.to_mesh(obj.data)

        if self.invert:
            bpy.ops.paint.mask_flood_fill(mode="INVERT")
        obj.data.update()
        self.print_time()
        return {"FINISHED"}


class PAINT_OT_mio3sc_mask_from_vertex_group(Mio3SclputOperator, Operator):
    bl_idname = "paint.mio3sc_mask_from_vertex_group"
    bl_label = "Vertex Group"
    bl_description = "Create mask from active vertex group\n[Shift] Add\n[Alt] Remove\n[Ctrl] Invert"
    bl_options = {"REGISTER", "UNDO"}
    invert: BoolProperty(name="Invert", default=False, options={"SKIP_SAVE", "HIDDEN"})
    clear: BoolProperty(name="Clear", default=False, options={"SKIP_SAVE", "HIDDEN"})
    add: BoolProperty(name="Add", default=False, options={"SKIP_SAVE", "HIDDEN"})

    def invoke(self, context, event):
        if event.shift:
            self.add = True
        if event.ctrl:
            self.invert = True
        if event.alt:
            self.clear = True
        bpy.ops.ed.undo_push(message="Mio3 Sculpt")
        return self.execute(context)

    def execute(self, context):
        self.start_time()
        obj = context.active_object
        if (vg := obj.vertex_groups.active) is None:
            return {"CANCELLED"}
        active_vg_index = vg.index

        if not self.add and not self.clear:
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0)

        if self.use_multires(obj):
            v_len = len(obj.data.vertices)
            hide_v = np.ones(v_len, dtype=np.uint8)
            for v in obj.data.vertices:
                if any(g.group == active_vg_index for g in v.groups):
                    hide_v[v.index] = 0
            hide_p = [any(hide_v[i] for i in p.vertices) for p in obj.data.polygons]
            obj.data.polygons.foreach_set("hide", hide_p)
            multires = self.store_multires(obj)
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0 if self.clear else 1)
            bpy.ops.paint.hide_show_all(action="SHOW")
            self.restore_multires(multires)
        else:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            mask_layer = self.get_maks_layer(bm)
            deform_layer = bm.verts.layers.deform.active
            val = 0 if self.clear else 1
            for v in bm.verts:
                groups = v[deform_layer]
                if active_vg_index in groups:
                    v[mask_layer] = val
            bm.to_mesh(obj.data)

        if self.invert:
            bpy.ops.paint.mask_flood_fill(mode="INVERT")

        obj.data.update()
        self.print_time()
        return {"FINISHED"}


class PAINT_PT_mio3sc_mask(Panel):
    bl_label = "Mio3 Sculpt Mask"
    bl_idname = "PAINT_PT_mio3sc_mask"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mio3"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "SCULPT"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        split = col.split(factor=0.68, align=True)
        split.operator("paint.mio3sc_mask_from_selection")
        split.operator("paint.mio3sc_mask_from_selection", text="Add").add = True
        split = col.split(factor=0.68, align=True)
        split.operator("paint.mio3sc_mask_from_vertex_group")
        split.operator("paint.mio3sc_mask_from_vertex_group", text="Add").add = True
        row = layout.row(align=True)
        op = row.operator("paint.mask_flood_fill", text="Fill")
        op.mode = "VALUE"
        op.value = 1
        op = row.operator("paint.mask_flood_fill", text="Clear")
        op.mode = "VALUE"
        op.value = 0
        op = row.operator("paint.mask_flood_fill", text="Invert")
        op.mode = "INVERT"


classes = [
    PAINT_OT_mio3sc_mask_from_selection,
    PAINT_OT_mio3sc_mask_from_vertex_group,
    PAINT_PT_mio3sc_mask,
]

translation_dict = {
    "ja_JP": {
        ("Operator", "Selection Mesh"): "選択メッシュ",
        ("*", "Create mask from selected mesh in edit mode\n[Shift] Add\n[Alt] Remove\n[Ctrl] Invert"):
            "編集モードで選択したメッシュからマスクを作成\n[Shift] 追加\n[Alt] 削除\n[Ctrl] 反転",
        ("Operator", "Vertex Group"): "頂点グループ",
        ("*", "Create mask from active vertex group\n[Shift] Add\n[Alt] Remove\n[Ctrl] Invert"):
            "アクティブな頂点グループからマスクを作成\n[Shift] 追加\n[Alt] 削除\n[Ctrl] 反転",
        ("*", "Fill with or clear a mask"): "マスクを塗りつぶすかクリアする",
    }
}  # fmt: skip


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.translations.register(__package__, translation_dict)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.app.translations.unregister(__package__)
