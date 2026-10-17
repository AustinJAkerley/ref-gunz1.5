#!/usr/bin/env python3
"""Convert verified GunZ data into bounded native meshes and baked ANI poses.

Uses common NumPy/Pillow for matrix and image data; never runs game binaries.
Mansion: Z-up cm -> Y-up metres. ELU characters are already Y-up cm.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from asset_formats import ani, bsp, collision as read_collision, elu, unpack_mrs
from katana_clips import CLIPS

ROOT = Path(__file__).resolve().parents[2] / "native/assets"
OUT = ROOT / "converted"


def texture(source, name):
    target = OUT / name
    if not source.is_file():
        raise ValueError(f"Missing texture {source}")
    with Image.open(source) as image:
        if image.width > 4096 or image.height > 4096:
            raise ValueError("Oversized texture")
        image.convert("RGBA").save(target)
    return name


def write_model(path, groups, frames=1, fps=1):
    # Per material: name, vertex count, UVs, then frame-major XYZ positions.
    with path.open("wb") as f:
        f.write(struct.pack("<4sIII", b"GZA1", len(groups), frames, fps))
        for name, uv, positions in groups:
            name = name.encode("utf-8")
            positions = np.asarray(positions, dtype="<f4")
            uv = np.asarray(uv, dtype="<f4")
            if positions.shape != (frames, len(uv), 3) or len(uv) % 3:
                raise ValueError("Model array shape")
            if not np.isfinite(positions).all() or not np.isfinite(uv).all():
                raise ValueError("Invalid converted geometry")
            f.write(struct.pack("<I", len(name)))
            f.write(name)
            f.write(struct.pack("<I", len(uv)))
            f.write(uv.tobytes())
            f.write(positions.tobytes())


def convert_map():
    files = unpack_mrs((ROOT / "raw/Maps/mansion.mrs").read_bytes())
    extracted = ROOT / "extracted/mansion"
    for name, data in files.items():
        target = extracted / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    triangles = bsp(files["mansion.rs.bsp"])
    xml = ET.fromstring(files["mansion.rs.xml"])
    materials = xml.find("MATERIALLIST").findall("MATERIAL")
    batches = defaultdict(list)
    collision = [[(v[0]*.01, v[2]*.01, v[1]*.01) for v in tri]
                 for tri in read_collision(files["mansion.rs.col"]) ]
    for mat, flags, vertices in triangles:
        if flags & 0x80 or mat < 0:
            continue
        if mat >= len(materials):
            raise ValueError("Map material index")
        # Swap axes reverses winding, so reorder vertices.
        vertices = [vertices[0], vertices[2], vertices[1]]
        positions = [(v[0]*.01, v[2]*.01, v[1]*.01) for v in vertices]
        uv = [(v[6], v[7]) for v in vertices]
        batches[mat].append((positions, uv))
    groups = []
    for mat, batch in sorted(batches.items()):
        source_name = materials[mat].findtext("DIFFUSEMAP", "").replace("\\", "/").split("/")[-1].lower()
        source = extracted / (source_name + ".dds")
        if not source.exists():
            source = extracted / source_name
        name = texture(source, f"map_{mat:03}.png")
        groups.append((name, [v for _, uv in batch for v in uv], [[v for pos, _ in batch for v in pos]]))
    write_model(OUT / "mansion.gza", groups)
    # Use original central-hall dummy. Player 1 faces the long hall; later spawns offset.
    spawns = []
    for dummy in xml.find("DUMMYLIST"):
        name = dummy.attrib.get("name", "")
        if name.startswith("spawn_solo_"):
            x, y, z = map(float, dummy.findtext("POSITION").split())
            dx, dy, dz = map(float, dummy.findtext("DIRECTION").split())
            spawns.append((name, (x*.01, z*.01, y*.01, math.atan2(dx,dy))))
    spawns.sort(key=lambda pair: (pair[0] != "spawn_solo_109", pair[0]))
    with (OUT / "mansion.collision").open("wb") as f:
        f.write(struct.pack("<4sII", b"GZC1", len(collision), len(spawns)))
        for _, point in spawns:
            f.write(struct.pack("<4f", *point))
        f.write(np.asarray(collision, dtype="<f4").tobytes())
    return {"triangles": len(triangles), "rendered_triangles": sum(len(v) for v in batches.values()),
            "collision_triangles": len(collision), "textures": len(groups), "spawns": len(spawns)}


def quaternion_matrix(q):
    q = np.array(q, dtype=float)
    q /= max(np.linalg.norm(q), 1e-8)
    x, y, z, w = q
    # DirectX row-vector rotation matrix.
    return np.array([[1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w), 0],
                     [2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w), 0],
                     [2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y), 0],
                     [0, 0, 0, 1]], dtype=float)


def sample(keys, time, quaternion=False):
    if len(keys) == 1 or time <= keys[0][-1]:
        return np.array(keys[0][:-1], dtype=float)
    for a, b in zip(keys, keys[1:]):
        if time <= b[-1]:
            t = (time-a[-1])/max(1,b[-1]-a[-1])
            x, y = np.array(a[:-1]), np.array(b[:-1])
            if quaternion and x.dot(y) < 0:
                y = -y
            return x*(1-t)+y*t
    return np.array(keys[-1][:-1], dtype=float)


def convert_character():
    folder = ROOT / "raw/Model/man"
    parts = elu((folder / "man-parts_assassin.elu").read_bytes())
    base = elu((folder / "man_lo01.elu").read_bytes())
    nodes = {node["name"]: node for node in base["nodes"]}
    nodes.update({node["name"]: node for node in parts["nodes"]})
    mesh_nodes = [node for node in parts["nodes"] if node["name"].startswith("eq_") and node["weights"]]
    weapon = dict(nodes["eq_wd_katana"])
    weapon["material"] = 99
    mesh_nodes.append(weapon)
    files = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    textures = {}
    for mat in parts["materials"]:
        textures[mat["id"]] = texture(files[mat["diffuse"].lower()+".dds"], f"character_{mat['id']}.png")
    textures[99] = texture(ROOT / "raw/Model/weapon/katana/katana01.bmp.dds", "katana.png")
    bounds = {}
    for clip, filename in CLIPS.items():
        animation = ani((folder / filename).read_bytes())
        keys = animation["nodes"]
        matrices = {name: np.array(keys.get(name, {}).get("matrix", node["matrix"])).reshape(4,4) for name,node in nodes.items()}
        local = {}
        for name, node in nodes.items():
            parent = node["parent"]
            local[name] = matrices[name] @ np.linalg.inv(matrices[parent]) if parent in matrices else matrices[name].copy()
        duration_ticks = max([key[-1] for value in keys.values() for kind in ("positions", "rotations") for key in value[kind]] or [160])
        frames = min(120, max(2, round(duration_ticks/160)+1))
        output = [[] for _ in mesh_nodes]
        uv_arrays = []
        indices = []
        for node in mesh_nodes:
            indices.append(np.array([i for face in node["faces"] for i in face[0]], dtype=int))
            uv_arrays.append([(face[1][3*i], face[1][3*i+1]) for face in node["faces"] for i in range(3)])
        for frame in range(frames):
            time = frame * duration_ticks / max(1, frames-1)
            posed = {}

            def pose(name, depth=0):
                if name in posed:
                    return posed[name]
                if depth > 100:
                    raise ValueError("Cyclic skeleton")
                matrix = local[name].copy()
                key = keys.get(name)
                if key:
                    if key["rotations"]:
                        matrix[:3,:3] = quaternion_matrix(sample(key["rotations"],time,True))[:3,:3]
                    if key["positions"]:
                        matrix[3,:3] = sample(key["positions"],time)
                parent = nodes[name]["parent"]
                if parent in nodes:
                    matrix = matrix @ pose(parent,depth+1)
                posed[name] = matrix
                return matrix

            for name in nodes:
                pose(name)
            for mesh_index, node in enumerate(mesh_nodes):
                points = []
                if not node["weights"]:
                    points = [(np.array([*point,1]) @ posed[node["name"]])[:3]*.01 for point in node["points"]]
                for point, influences in zip(node["points"], node["weights"]):
                    result = np.zeros(3)
                    total = 0
                    for bone, weight, offset in influences:
                        if bone not in posed or weight < 0 or weight > 1.001:
                            raise ValueError(f"Invalid influence {bone}")
                        result += (np.array([*offset,1]) @ posed[bone])[:3]*weight
                        total += weight
                    if not .95 <= total <= 1.05:
                        raise ValueError("Skin weights not normalized")
                    points.append(result*.01/total)
                output[mesh_index].append(np.array(points)[indices[mesh_index]])
        groups = [(textures[n["material"]], uv_arrays[i], output[i]) for i,n in enumerate(mesh_nodes)]
        write_model(OUT / f"character_{clip}.gza", groups, frames, 30)
        all_points = np.concatenate([np.array(poses).reshape(-1,3) for poses in output])
        bounds[clip] = {"source": filename, "frames": frames, "ticks": duration_ticks,
                "seconds": duration_ticks/4800.0,
                "min": all_points.min(axis=0).tolist(), "max": all_points.max(axis=0).tolist()}
    return bounds


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"map": convert_map(), "character": convert_character()}
    (OUT / "conversion.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()