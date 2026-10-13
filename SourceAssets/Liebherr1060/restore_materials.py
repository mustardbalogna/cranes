from pathlib import Path

import unreal


def restore_materials() -> None:
    material_source = Path(__file__).resolve().parent / "model" / "Untitled.mtl"
    textured = {"Blinds_R", "_Fenci01", "_Fenci02", "_Fencing", "_Metal_A", "_Metal_S"}
    material_name = ""
    restored = []

    with material_source.open(encoding="utf-8-sig") as source:
        for line in source:
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "newmtl":
                material_name = fields[1]
            elif fields[0] == "Kd" and material_name not in textured:
                material_path = f"/Game/Liebherr1060/{material_name}"
                material = unreal.load_asset(material_path)
                if not isinstance(material, (unreal.Material, unreal.MaterialInstanceConstant)):
                    raise RuntimeError(f"Expected imported material: {material_path}")
                red, green, blue = [float(value) for value in fields[1:4]]
                source_color = unreal.LinearColor(red, green, blue, 1.0)
                if isinstance(material, unreal.MaterialInstanceConstant):
                    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
                        material, "BaseColor", source_color
                    )
                    actual_color = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(
                        material, "BaseColor"
                    )
                    if any(
                        abs(actual - expected) > 0.00001
                        for actual, expected in zip(
                            (actual_color.r, actual_color.g, actual_color.b), (red, green, blue)
                        )
                    ):
                        raise RuntimeError(f"Base color verification failed: {material_path}")
                    unreal.MaterialEditingLibrary.update_material_instance(material)
                else:
                    color = unreal.MaterialEditingLibrary.create_material_expression(
                        material, unreal.MaterialExpressionConstant3Vector, -300, 0
                    )
                    color.set_editor_property("constant", source_color)
                    if not unreal.MaterialEditingLibrary.connect_material_property(
                        color, "", unreal.MaterialProperty.MP_BASE_COLOR
                    ):
                        raise RuntimeError(f"Unable to connect base color: {material_path}")
                    unreal.MaterialEditingLibrary.recompile_material(material)
                if not unreal.EditorAssetLibrary.save_asset(material_path):
                    raise RuntimeError(f"Unable to save material: {material_path}")
                restored.append(material_name)

    if len(restored) != 26:
        raise RuntimeError(f"Expected 26 solid-color materials, restored {len(restored)}")
    unreal.log(f"LIEBHERR_MATERIALS_RESTORED: {len(restored)}; red paint and source colors restored")


restore_materials()