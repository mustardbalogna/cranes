from pathlib import Path
import json

import unreal


def import_parts() -> None:
    directory = Path(__file__).resolve().parent / "model" / "Parts"
    manifest = json.loads((directory / "parts.json").read_text(encoding="utf-8"))
    tasks = []
    for part, entry in manifest["parts"].items():
        task = unreal.AssetImportTask()
        task.filename = entry["file"]
        task.destination_path = "/Game/Liebherr1060/Parts"
        task.destination_name = f"SM_Liebherr_{part}"
        task.automated = True
        task.replace_existing = True
        task.replace_existing_settings = True
        task.save = True
        options = unreal.FbxImportUI()
        options.import_as_skeletal = False
        options.automated_import_should_detect_type = False
        options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
        options.import_materials = False
        options.import_textures = False
        options.static_mesh_import_data.combine_meshes = True
        task.options = options
        tasks.append(task)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    imported = []
    for part in manifest["parts"]:
        asset_path = f"/Game/Liebherr1060/Parts/SM_Liebherr_{part}"
        mesh = unreal.load_asset(asset_path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError(f"Part import failed: {asset_path}")
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            name = str(slot.material_slot_name)
            material = unreal.load_asset(f"/Game/Liebherr1060/{name}")
            if not isinstance(material, unreal.MaterialInterface):
                raise RuntimeError(f"Missing source material {name} on {part}")
            mesh.set_material(index, material)
        unreal.EditorAssetLibrary.save_asset(asset_path)
        imported.append(asset_path)
    unreal.log("LIEBHERR_PARTS_IMPORTED: " + json.dumps(imported))


import_parts()