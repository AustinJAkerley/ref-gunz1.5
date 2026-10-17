#!/usr/bin/env python3
"""Fetch an explicit data-only selection from a pinned public client snapshot.

No launchers, installers, DLLs, scripts, custom maps or whole client packages.
Git blob hashes are verified against the pinned tree before anything is written.
"""
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
from katana_clips import CLIPS

ROOT = Path(__file__).resolve().parents[2]
REVISION = "6b370b78e39ae7a2a8c266aceb9086a867e3181b"
REPOSITORY = "open-gunz/ogz-client"
FILES = [
    "Maps/mansion.mrs", "Model/man/man_lo01.elu",
    "Model/man/man-parts_assassin.elu", "Model/man/man01.xml",
    "Model/man/Assassin_male_chest.TGA.dds", "Model/man/Assassin_male_legs.tga.dds",
    "Model/man/Assassin_male_head.TGA.dds", "Model/man/Assassin_male_hands.TGA.dds",
    "Model/man/Assassin_male_feet.TGA.dds",
    "Model/man/man_sword_idle.elu.ani", "Model/man/man_sword_run.elu.ani",
    "Model/man/man_sword_jump_up.elu.ani", "Model/man/man_sword_attack_jump.elu.ani",
    "Model/weapon/katana/katana01.bmp.dds",
]
FILES += ["Model/man/" + name for name in CLIPS.values()]


def get(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "GunZ-native-data-import"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Download exceeds size limit")
        return data


def main():
    tree = json.loads(get(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1", 10_000_000))
    assert not tree["truncated"]
    entries = {entry["path"]: entry for entry in tree["tree"] if entry["type"] == "blob"}
    destination = ROOT / "native/assets/raw"
    records = []
    for name in FILES:
        entry = entries[name]
        assert entry["mode"] == "100644" and entry["size"] < 20_000_000
        url = f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/{urllib.parse.quote(name)}"
        path = destination / name
        data = path.read_bytes() if path.exists() else get(url, 20_000_000)
        digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if digest != entry["sha"] or len(data) != entry["size"]:
            raise ValueError(f"Snapshot hash/size mismatch: {name}")
        if data.startswith((b"MZ", b"\x7fELF")):
            raise ValueError(f"Executable rejected: {name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        records.append({"path": name, "url": url, "bytes": len(data), "git_blob": digest,
                        "sha256": hashlib.sha256(data).hexdigest()})
        print(f"Verified data: {name} ({len(data):,} bytes)")
    manifest = {"repository": REPOSITORY, "revision": REVISION,
                "provenance": "Community client snapshot; canonical-named assets, not verified retail originals. No declared repository license. No custom-map or launcher downloads.",
                "files": records}
    (destination.parent / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()