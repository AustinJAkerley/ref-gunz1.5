"""Bounded readers for the actual MRS2, RealSpace BSP, ELU and ANI data formats.

Layouts are derived from the checked-in original MZip/RBspObject/RMesh loaders.
Never imports or executes code from assets. Unknown versions fail closed.
"""
import math
from pathlib import Path, PurePosixPath
import struct
import zlib


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError(f"Truncated data at {self.pos}, requested {count}")
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def read(self, fmt):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))

    def u32(self):
        return self.read("I")[0]

    def count(self, maximum=1_000_000):
        count = self.read("i")[0]
        if not 0 <= count <= maximum:
            raise ValueError(f"Invalid count {count} at {self.pos}")
        return count

    def floats(self, n):
        result = self.read(f"{n}f")
        if not all(math.isfinite(x) and abs(x) < 1e10 for x in result):
            raise ValueError("Invalid floating point data")
        return result

    def text(self, length):
        return self.take(length).split(b"\0", 1)[0].decode("cp949", errors="replace")

    def end(self):
        if self.pos != len(self.data):
            raise ValueError(f"Unconsumed bytes: {len(self.data) - self.pos}")


def recover(data):
    return bytes((((b & 7) << 5) | (b >> 3)) ^ 255 for b in data)


def unpack_mrs(data):
    if len(data) < 22 or len(data) > 50_000_000:
        raise ValueError("MRS size out of bounds")
    first = struct.unpack_from("<I", data)[0]
    encoded = first not in (0x04034B50, 0x85840000)
    transform = recover if encoded else lambda b: b
    end = Reader(transform(data[-22:]))
    signature, disk, disk2, entries, total, directory_size, directory_offset, comment = end.read("I4H2IH")
    if signature not in (0x06054B50, 0x05030207, 0x05030208) or disk or disk2 or comment or entries != total:
        raise ValueError("Unsupported MRS directory")
    if entries > 4096 or directory_size > len(data) - 22:
        raise ValueError("MRS directory out of bounds")
    start = len(data) - 22 - directory_size
    directory = Reader(transform(data[start:-22]))
    output = {}
    total_output = 0
    for _ in range(entries):
        fields = directory.read("I6H3I5H2I")
        sig, _, _, flags, method, _, _, crc, compressed, size, name_len, extra_len, comment_len, _, _, _, offset = fields
        if sig not in (0x02014B50, 0x05024B80) or flags & 1 or method not in (0, 8):
            raise ValueError(f"Unsupported MRS entry {sig:x}, {method}")
        name = directory.text(name_len).replace("\\", "/").lower()
        directory.take(extra_len + comment_len)
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or ":" in name or name in output:
            raise ValueError("Unsafe/duplicate MRS entry name")
        total_output += size
        if size > 64_000_000 or total_output > 256_000_000 or offset + 30 > start:
            raise ValueError("MRS entry size or offset out of bounds")
        local = Reader(transform(data[offset:offset + 30]))
        local_fields = local.read("I5H3I2H")
        if local_fields[0] not in (0x04034B50, 0x85840000) or local_fields[3] != method:
            raise ValueError("MRS local header mismatch")
        content_start = offset + 30 + local_fields[-2] + local_fields[-1]
        if content_start + compressed > start:
            raise ValueError("MRS payload outside data region")
        content = data[content_start:content_start + compressed]
        if method == 8:
            decoder = zlib.decompressobj(-15)
            content = decoder.decompress(content, size + 1)
            if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError("MRS deflate bounds/trailing data")
        if len(content) != size or zlib.crc32(content) != crc:
            raise ValueError("MRS CRC/size mismatch")
        if content.startswith((b"MZ", b"\x7fELF")):
            raise ValueError("Executable content rejected")
        output[name] = content
    directory.end()
    return output


def bsp(data):
    r = Reader(data)
    if r.read("2I") != (0x35849298, 2):
        raise ValueError("Unsupported BSP version")
    node_limit, polygon_limit = r.count(100_000), r.count(500_000)
    vertex_limit, index_limit = r.count(2_000_000), r.count(3_000_000)
    triangles = []
    nodes = 0
    polygons = 0
    vertices_total = 0

    def node(depth=0):
        nonlocal nodes, polygons, vertices_total
        nodes += 1
        if nodes > node_limit or depth > 200:
            raise ValueError("BSP depth/node budget")
        # We flatten geometry, not the old visibility tree. Degenerate exporter
        # split planes/bounds may be non-finite; do not use them for allocation,
        # collision, or GPU data. Child/count/position bounds remain validated.
        r.take(40)
        for _ in range(2):
            child = r.take(1)[0]
            if child > 1:
                raise ValueError("BSP child flag")
            if child:
                node(depth + 1)
        count = r.count(polygon_limit)
        polygons += count
        if polygons > polygon_limit:
            raise ValueError("BSP polygon budget")
        for _ in range(count):
            material, convex, flags = r.read("iiI")
            n = r.count(4096)
            if n < 3:
                raise ValueError("Invalid polygon")
            vertices_total += n
            if vertices_total > vertex_limit:
                raise ValueError("BSP vertex budget")
            # UV2 is populated from .lm by the original renderer; the BSP's
            # placeholder UV2 may contain uninitialized exporter bytes.
            vertices = []
            for _ in range(n):
                position = r.floats(3)
                r.take(12)  # Degenerate legacy normals can be NaN; recompute from positions.
                vertices.append(position + (0., 0., 0.) + r.floats(2))
                r.take(8)
            r.take(12)  # Likewise the optional exported face normal.
            for i in range(1, n - 1):
                triangles.append((material, flags, [vertices[0], vertices[i], vertices[i + 1]]))

    node()
    r.end()
    if nodes != node_limit or polygons != polygon_limit or vertices_total != vertex_limit or len(triangles) * 3 != index_limit:
        raise ValueError("BSP declared totals mismatch")
    return triangles


def elu(data):
    r = Reader(data)
    sig, version, materials, nodes = r.read("4I")
    if sig != 0x0107F060 or version not in range(0x5005, 0x5008) or materials > 1024 or nodes > 512:
        raise ValueError(f"Unsupported ELU header {version:x}")
    result = {"version": version, "materials": [], "nodes": []}
    for _ in range(materials):
        mat, sub = r.read("2i")
        colors = r.floats(12)
        power = r.floats(1)[0]
        subs = r.count(1024)
        length = 256 if version >= 0x5006 else 40
        diffuse, opacity = r.text(length), r.text(length)
        two_sided, additive = r.read("2i")
        alpha = r.read("i")[0] if version >= 0x5007 else 0
        result["materials"].append(dict(id=mat, sub=sub, diffuse=diffuse, opacity=opacity,
                                          colors=colors, two_sided=two_sided, additive=additive, alpha=alpha))
    for _ in range(nodes):
        name, parent = r.text(40), r.text(40)
        matrix = r.floats(16)
        scale = r.floats(3)
        r.floats(24)  # axis rotations/scales + auxiliary matrix
        points = [r.floats(3) for _ in range(r.count(100_000))]
        faces = []
        count = r.count(100_000)
        for _ in range(count):
            indices = r.read("3i")
            if any(i < 0 or i >= len(points) for i in indices):
                raise ValueError("ELU vertex index")
            uv = r.floats(9)
            material, smoothing = r.read("2i")
            faces.append((indices, uv, material))
        normals = [r.floats(12) for _ in range(count)]
        r.take(r.count(100_000) * 12)  # optional vertex colors
        material = r.read("i")[0]
        weights = []
        for _ in range(r.count(100_000)):
            names = [r.text(40) for _ in range(4)]
            amounts = r.floats(4)
            ids = r.read("4i")
            count = r.count(4)
            offsets = [r.floats(3) for _ in range(4)]
            weights.append([(names[i], amounts[i], offsets[i]) for i in range(count)])
        if weights and len(weights) != len(points):
            raise ValueError("ELU weights/vertices mismatch")
        result["nodes"].append(dict(name=name, parent=parent, matrix=matrix, scale=scale,
                                    points=points, faces=faces, normals=normals, material=material, weights=weights))
    r.end()
    return result


def collision(data):
    r = Reader(data)
    if r.read("2I") != (0x5050178F, 0):
        raise ValueError("Unsupported COL format")
    node_limit, polygon_limit = r.count(100000), r.count(500000)
    triangles = []
    nodes = 0

    def node(depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > node_limit or depth > 200:
            raise ValueError("COL node/depth budget")
        r.take(16)
        if r.take(1)[0] > 1:
            raise ValueError("COL solid flag")
        for _ in range(2):
            flag = r.take(1)[0]
            if flag > 1:
                raise ValueError("COL child flag")
            if flag:
                node(depth+1)
        for _ in range(r.count(polygon_limit)):
            triangles.append([r.floats(3) for _ in range(3)])
            r.take(12)
            if len(triangles) > polygon_limit:
                raise ValueError("COL triangle budget")
    node()
    r.end()
    if nodes != node_limit or len(triangles) != polygon_limit:
        raise ValueError("COL declared counts")
    return triangles


def ani(data):
    r = Reader(data)
    sig, version, frames, nodes, kind = r.read("5I")
    if sig != 0x0107F060 or version not in (0x1001, 0x1002, 0x1003) or kind != 2 or nodes > 512 or frames > 10000:
        raise ValueError("Unsupported ANI header")
    result = {"frames": frames, "nodes": {}}
    for _ in range(nodes):
        name, matrix = r.text(40), r.floats(16)
        positions = [r.read("3fi") for _ in range(r.count(10000))]
        rotations = [r.read("4fi") for _ in range(r.count(10000))]
        if version < 0x1003:
            converted = []
            for x, y, z, angle, frame in rotations:
                norm = math.sqrt(x*x+y*y+z*z)
                scale = math.sin(angle*.5)/norm if norm > 1e-8 else 0
                converted.append((x*scale, y*scale, z*scale, math.cos(angle*.5), frame))
            rotations = converted
        visibility = [r.read("fi") for _ in range(r.count(10000))]
        result["nodes"][name] = dict(matrix=matrix, positions=positions, rotations=rotations)
    r.end()
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2] / "native/assets"
    files = unpack_mrs((root / "raw/Maps/mansion.mrs").read_bytes())
    for name, content in files.items():
        output = root / "extracted/mansion" / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        print(name, len(content))
    for name in ("man_lo01.elu", "man-parts_assassin.elu"):
        model = elu((root / "raw/Model/man" / name).read_bytes())
        print(name, "materials", model["materials"])
        print("nodes", [(n["name"], n["parent"], len(n["points"]), len(n["faces"])) for n in model["nodes"]])
    animation = ani((root / "raw/Model/man/man_sword_idle.elu.ani").read_bytes())
    print("ANI frames", animation["frames"], "bones", len(animation["nodes"]))