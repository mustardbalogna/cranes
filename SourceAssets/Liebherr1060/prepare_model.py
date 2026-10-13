from pathlib import Path
import json
import math


def prepare_model() -> None:
    directory = Path(__file__).resolve().parent / "model"
    source = directory / "Untitled.obj"
    destination = directory / "Liebherr1060_Centered.obj"
    minimum = [math.inf] * 3
    maximum = [-math.inf] * 3
    vertex_count = 0
    group_count = 0
    face_count = 0

    with source.open(encoding="utf-8-sig") as model:
        for line in model:
            fields = line.split()
            if fields and fields[0] == "v":
                coordinates = [float(value) for value in fields[1:4]]
                for axis, coordinate in enumerate(coordinates):
                    minimum[axis] = min(minimum[axis], coordinate)
                    maximum[axis] = max(maximum[axis], coordinate)
                vertex_count += 1

    if vertex_count == 0:
        raise ValueError("Source OBJ contains no vertices")

    origin = [
        (minimum[0] + maximum[0]) / 2,
        minimum[1],
        (minimum[2] + maximum[2]) / 2,
    ]
    with source.open(encoding="utf-8-sig") as model:
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            for line in model:
                fields = line.split()
                if fields and fields[0] == "v":
                    coordinates = [
                        (float(fields[axis + 1]) - origin[axis]) * 100
                        for axis in range(3)
                    ]
                    coordinates = [coordinates[0], -coordinates[2], coordinates[1]]
                    suffix = " " + " ".join(fields[4:]) if len(fields) > 4 else ""
                    output.write("v " + " ".join(f"{value:.9f}" for value in coordinates) + suffix + "\n")
                elif fields and fields[0] == "vn":
                    normal = [float(value) for value in fields[1:4]]
                    output.write(f"vn {normal[0]:.9f} {-normal[2]:.9f} {normal[1]:.9f}\n")
                else:
                    output.write(line)
                if fields and fields[0] == "g":
                    group_count += 1
                if fields and fields[0] == "f":
                    face_count += 1

    report = {
        "output": str(destination),
        "vertices": vertex_count,
        "groups": group_count,
        "faces": face_count,
        "source_origin_m": origin,
        "axis_conversion": "Y-up to Z-up: (x, y, z) -> (x, -z, y)",
        "size_cm": [(maximum[axis] - minimum[axis]) * 100 for axis in (0, 2, 1)],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    prepare_model()