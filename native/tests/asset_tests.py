"""Data parser regressions. No graphics, network, or original executable required."""
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from asset_formats import Reader, ani, bsp, collision, elu, unpack_mrs


def zip_fixture(name="test.txt", content=b"GunZ"):
    name = name.encode()
    crc = zlib.crc32(content)
    local = struct.pack("<I5H3I2H", 0x04034B50, 20, 0, 0, 0, 0, crc, len(content), len(content), len(name), 0) + name + content
    directory = struct.pack("<I6H3I5H2I", 0x02014B50, 20, 20, 0, 0, 0, 0, crc, len(content), len(content), len(name), 0, 0, 0, 0, 0, 0) + name
    return local + directory + struct.pack("<I4H2IH", 0x06054B50, 0, 0, 1, 1, len(directory), len(local), 0)


def bsp_fixture():
    header = struct.pack("<6I", 0x35849298, 2, 1, 1, 3, 3)
    node = b"\0" * 42 + struct.pack("<I", 1)
    polygon = struct.pack("<iiII", 0, 0, 0, 3)
    for point in ((0, 0, 0), (100, 0, 0), (0, 100, 0)):
        polygon += struct.pack("<10f", *point, 0, 0, 1, 0, 0, float("nan"), float("nan"))
    return header + node + polygon + struct.pack("<3f", 0, 0, 1)


class Formats(unittest.TestCase):
    def test_reader_bounds(self):
        with self.assertRaises(ValueError): Reader(b"123").u32()
        with self.assertRaises(ValueError): Reader(b"123").take(-1)
        with self.assertRaises(ValueError): Reader(struct.pack("<i", -1)).count()
        with self.assertRaises(ValueError): Reader(struct.pack("<f", float("nan"))).floats(1)

    def test_zip_crc_paths_and_executables(self):
        self.assertEqual(unpack_mrs(zip_fixture()), {"test.txt": b"GunZ"})
        for name in ("../bad", "/absolute", "C:/escape", "a/../../escape"):
            with self.assertRaises(ValueError): unpack_mrs(zip_fixture(name))
        with self.assertRaises(ValueError): unpack_mrs(zip_fixture(content=b"MZpayload"))
        bad = bytearray(zip_fixture()); bad[38] ^= 1
        with self.assertRaises(ValueError): unpack_mrs(bytes(bad))

    def test_bsp_counts_and_truncation(self):
        fixture = bsp_fixture()
        self.assertEqual(len(bsp(fixture)), 1)
        for n in range(len(fixture)):
            with self.assertRaises((ValueError, struct.error)): bsp(fixture[:n])
        bad = bytearray(fixture); struct.pack_into("<I", bad, 20, 6)
        with self.assertRaises(ValueError): bsp(bytes(bad))
        bad = bytearray(fixture); struct.pack_into("<f", bad, 86, float("nan"))
        with self.assertRaises(ValueError): bsp(bytes(bad))

    def test_unknown_formats(self):
        for parser in (bsp, collision, elu, ani):
            with self.assertRaises(ValueError): parser(b"\0" * 200)

    def test_legacy_axis_angle(self):
        import math
        matrix=struct.pack("<16f", *([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]))
        data=struct.pack("<5I",0x0107F060,0x1001,10,1,2)
        data+=b"Bip01"+b"\0"*35+matrix+struct.pack("<2I",0,1)
        data+=struct.pack("<4fiI",0,1,0,math.pi,1600,0)
        key=ani(data)["nodes"]["Bip01"]["rotations"][0]
        self.assertAlmostEqual(key[1],1,places=5)
        self.assertAlmostEqual(key[3],0,places=5)

    def test_downloaded_data_if_present(self):
        root = Path(__file__).resolve().parents[1] / "assets/raw"
        path = root / "Maps/mansion.mrs"
        if not path.exists(): self.skipTest("Optional downloaded asset fixture absent")
        files = unpack_mrs(path.read_bytes())
        self.assertEqual(len(bsp(files["mansion.rs.bsp"])), 34350)
        self.assertEqual(len(collision(files["mansion.rs.col"])), 31432)
        model = elu((root / "Model/man/man-parts_assassin.elu").read_bytes())
        self.assertEqual(len(model["materials"]), 5)
        self.assertEqual(len(model["nodes"]), 36)
        clip = ani((root / "Model/man/man_sword_idle.elu.ani").read_bytes())
        self.assertEqual(len(clip["nodes"]), 37)
        dash=root/"Model/man/man_knife_dash.elu.ani"
        if dash.exists():
            for name in ("man_knife_dash", "man_knife_dash_back", "man_knife_dash_Rside", "man_knife_dash_Lside"):
                clip=ani((root/f"Model/man/{name}.elu.ani").read_bytes())
                ticks=max(key[-1] for node in clip["nodes"].values() for kind in ("positions","rotations") for key in node[kind])
                self.assertEqual(ticks,1600)


if __name__ == "__main__":
    unittest.main()