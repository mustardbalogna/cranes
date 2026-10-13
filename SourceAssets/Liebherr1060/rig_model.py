from collections import defaultdict
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Saved" / "LiebherrTools"))

import numpy as np
import trimesh


def read_groups():
    source = Path(__file__).resolve().parent / "model" / "Liebherr1060_Centered.obj"
    vertices = []
    texture_coordinates = []
    normals = []
    groups = defaultdict(list)
    records = defaultdict(list)
    group_name = "Default"
    material_name = ""
    with source.open(encoding="utf-8-sig") as model:
        for line in model:
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "v":
                vertices.append([float(value) for value in fields[1:4]])
            elif fields[0] == "vt":
                texture_coordinates.append(fields[1:])
            elif fields[0] == "vn":
                normals.append(fields[1:])
            elif fields[0] == "g":
                group_name = " ".join(fields[1:])
            elif fields[0] == "usemtl":
                material_name = fields[1]
            elif fields[0] == "f":
                if len(fields) != 4:
                    raise ValueError("Expected the source model's triangular faces")
                triangle = []
                for corner in fields[1:]:
                    index = int(corner.split("/")[0])
                    triangle.append(index - 1 if index > 0 else len(vertices) + index)
                groups[group_name].append(triangle)
                records[group_name].append((material_name, fields[1:]))
    vertices = np.asarray(vertices, dtype=float)
    meshes = {}
    for name, faces in groups.items():
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.remove_unreferenced_vertices()
        meshes[name] = mesh
    if sum(len(mesh.faces) for mesh in meshes.values()) != 61621:
        raise ValueError("Mesh grouping changed the source face count")
    return meshes, records, (vertices, texture_coordinates, normals)


def report_groups():
    meshes, _, _ = read_groups()
    report = {
        name: {
            "faces": len(mesh.faces),
            "bounds_cm": mesh.bounds.round(3).tolist(),
            "center_cm": mesh.bounds.mean(axis=0).round(3).tolist(),
            "size_cm": mesh.extents.round(3).tolist(),
        }
        for name, mesh in meshes.items()
    }
    destination = ROOT / "Saved" / "Liebherr1060" / "groups.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "groups_with_faces": len(report),
        "total_faces": sum(entry["faces"] for entry in report.values()),
        "hook": {name: entry for name, entry in report.items() if "hook" in name.lower()},
        "report": str(destination),
    }, indent=2))


def split_parts():
    meshes, records, attributes = read_groups()
    tires = ["Mesh13", "Mesh15", "Mesh17", "Mesh19", "Mesh21", "Mesh23"]
    parts = {
        "Chassis": [],
        "Turntable": [],
        "BoomSec0": [],
        "BoomSec1": [],
        "BoomSec2": [],
        "BoomSec3": [],
        "BoomSec4": [],
        "BoomSec5": [],
        "Hook": [],
    }
    
    hinge_pin = np.array([-921.631, 1.868, 432.164])
    pivots = {
        "Chassis": np.array([-600.0, 0.0, 0.0]),
        "Turntable": np.array([-785.0, 0.0, 195.0]),
        "BoomSec0": hinge_pin,
        "BoomSec1": hinge_pin,
        "BoomSec2": hinge_pin,
        "BoomSec3": hinge_pin,
        "BoomSec4": hinge_pin,
        "BoomSec5": hinge_pin,
        "Hook": np.array([946.0, 2.0, 3830.0]),
    }
    omitted = {f"Mesh{index}" for index in range(68, 74)}
    wheel_bounds = {}
    for index, tire_name in enumerate(tires, start=1):
        name = f"Wheel{index:02d}"
        parts[name] = []
        pivots[name] = meshes[tire_name].bounds.mean(axis=0)
        wheel_bounds[name] = meshes[tire_name].bounds + np.array([[-2, -2, -2], [2, 2, 2]])

    u_boom = np.array([0.460255, 0.000544, 0.887787])
    boom_limits = [895.0, 1511.4, 2103.8, 2678.5, 3390.9, 5000.0]

    for name, mesh in meshes.items():
        if name in omitted:
            continue
        lower, upper = mesh.bounds
        center = mesh.bounds.mean(axis=0)
        wheel = next((
            wheel_name for wheel_name, bounds in wheel_bounds.items()
            if np.all(lower >= bounds[0]) and np.all(upper <= bounds[1])
        ), None)
        if wheel:
            parts[wheel].append(name)
            continue
        if lower[0] > 900 and upper[0] < 985 and lower[2] > 3760 and upper[2] < 3870:
            parts["Hook"].append(name)
            continue
            
        is_boom = (upper[2] > 415 or name in ["Mesh96", "Mesh558", "Mesh519", "Mesh529"]) and (lower[2] >= 240 or upper[0] >= -440)
        
        if is_boom:
            dist = np.dot(center - hinge_pin, u_boom)
            sec_idx = 5
            for idx, lim in enumerate(boom_limits):
                if dist <= lim:
                    sec_idx = idx
                    break
            parts[f"BoomSec{sec_idx}"].append(name)
        elif upper[2] <= 430 and lower[2] < 195:
            parts["Chassis"].append(name)
        elif upper[2] <= 415 and (center[0] < -440 or upper[0] < -400):
            parts["Turntable"].append(name)
        else:
            parts["Chassis"].append(name)

    if "Hook2_1" not in parts["Hook"]:
        raise ValueError("Hook was not assigned to the hook assembly")
    for index, tire_name in enumerate(tires, start=1):
        if tire_name not in parts[f"Wheel{index:02d}"]:
            raise ValueError(f"Missing tire: {tire_name}")
            
    exported_faces = sum(len(meshes[name].faces) for names in parts.values() for name in names)
    omitted_faces = sum(len(meshes[name].faces) for name in omitted)
    if exported_faces + omitted_faces != 61621 or omitted_faces != 12:
        raise ValueError(f"Articulation lost or duplicated source faces: {exported_faces} + {omitted_faces}")

    directory = Path(__file__).resolve().parent / "model" / "Parts"
    directory.mkdir(exist_ok=True)
    manifest = {"parts": {}, "omitted_cable_groups": sorted(omitted), "total_source_faces": 61621}
    for part, names in parts.items():
        pivot = pivots[part]
        pools = attributes
        maps = [{}, {}, {}]
        faces = []
        for name in names:
            for material, corners in records[name]:
                remapped = []
                for corner in corners:
                    indices = corner.split("/")
                    new_indices = []
                    for pool_index, index in enumerate(indices):
                        if not index:
                            new_indices.append("")
                            continue
                        original = int(index)
                        original = original - 1 if original > 0 else len(pools[pool_index]) + original
                        maps[pool_index].setdefault(original, len(maps[pool_index]) + 1)
                        new_indices.append(str(maps[pool_index][original]))
                    remapped.append("/".join(new_indices))
                faces.append((name, material, remapped))
        destination = directory / f"SM_Liebherr_{part}.obj"
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            output.write("mtllib ../Untitled.mtl\n")
            for pool_index, tag in enumerate(("v", "vt", "vn")):
                for original in maps[pool_index]:
                    value = pools[pool_index][original]
                    if pool_index == 0:
                        value = [f"{coordinate:.9f}" for coordinate in value - pivot]
                    output.write(tag + " " + " ".join(value) + "\n")
            previous_group = previous_material = None
            for name, material, corners in faces:
                if name != previous_group:
                    output.write(f"g {name}\n")
                    previous_group = name
                if material != previous_material:
                    output.write(f"usemtl {material}\n")
                    previous_material = material
                output.write("f " + " ".join(corners) + "\n")
        local_vertices = np.array([pools[0][original] - pivot for original in maps[0]])
        manifest["parts"][part] = {
            "file": str(destination),
            "pivot_ue_cm": [float(pivot[0]), float(-pivot[1]), float(pivot[2])],
            "groups": names,
            "faces": len(faces),
            "local_bounds_obj_cm": [local_vertices.min(axis=0).tolist(), local_vertices.max(axis=0).tolist()],
        }
    manifest["retraction_steps_cm"] = [
        0.0,
        616.7,
        1209.1,
        1783.8,
        2496.2,
        3162.9
    ]
    manifest["boom_dir_ue"] = [0.460255, -0.000544, 0.887787]
    manifest_path = directory / "parts.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for part, entry in manifest["parts"].items():
        print(f"{part}: {entry['faces']} faces, {len(entry['groups'])} groups, pivot {entry['pivot_ue_cm']}")
    print(f"PASS: {exported_faces} exported faces + {omitted_faces} replaced cable faces = 61621")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    if "--split" in sys.argv:
        split_parts()
    else:
        report_groups()