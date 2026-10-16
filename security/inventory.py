#!/usr/bin/env python3
"""Inventory an upstream snapshot without executing any of its contents."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


SNAPSHOT = "d3dae1b7c108c276a715d291d357341af96bafc7"
ROOT = Path(__file__).resolve().parents[1]


def inventory():
    entries = subprocess.check_output(
        ["git", "ls-tree", "-r", "-z", SNAPSHOT], cwd=ROOT
    ).split(b"\0")
    extensions = Counter()
    binaries = defaultdict(list)
    archives = []
    empty = []
    mismatches = []
    total_size = 0
    count = 0
    manifest = hashlib.sha256()

    for entry in entries:
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode, kind, expected_oid = metadata.split()
        path = encoded_path.decode("utf-8")
        relative = Path(path)
        if (
            mode not in (b"100644", b"100755")
            or kind != b"blob"
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError(f"Unsupported or unsafe tree entry: {path!r}")
        file = ROOT / relative
        if any(parent.is_symlink() for parent in (file, *file.parents)):
            raise ValueError(f"Refusing symlink traversal: {path!r}")
        data = file.read_bytes()
        oid = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if oid != expected_oid.decode("ascii"):
            mismatches.append(path)
        digest = hashlib.sha256(data).hexdigest()
        manifest.update(encoded_path + b"\0" + digest.encode("ascii") + b"\n")
        count += 1
        total_size += len(data)
        extensions[relative.suffix.lower() or "(none)"] += 1
        if not data:
            empty.append(path)
        if data[:2] == b"MZ" and len(data) >= 64:
            offset = int.from_bytes(data[60:64], "little")
            if data[offset:offset + 4] == b"PE\0\0":
                binaries[digest].append({"path": path, "bytes": len(data)})
        if relative.suffix.lower() == ".zip":
            with zipfile.ZipFile(file) as archive:
                members = archive.infolist()
                unsafe = []
                for member in members:
                    name = member.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/") or ":" in name:
                        unsafe.append(member.filename)
                archives.append({
                    "path": path,
                    "sha256": digest,
                    "members": len(members),
                    "expanded_bytes": sum(member.file_size for member in members),
                    "encrypted_members": [
                        member.filename for member in members if member.flag_bits & 1
                    ],
                    "unsafe_member_names": unsafe,
                })

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "upstream": "https://github.com/open-gunz/ref-gunz1.5",
        "snapshot": SNAPSHOT,
        "tracked_files": count,
        "nonempty_files": count - len(empty),
        "total_bytes": total_size,
        "empty_files": empty,
        "snapshot_blob_mismatches": mismatches,
        "sha256_manifest_digest": manifest.hexdigest(),
        "manifest_format": "git tree order: UTF-8 path + NUL + hex SHA-256 + LF",
        "extensions": dict(extensions.most_common()),
        "pe_files": sum(len(paths) for paths in binaries.values()),
        "unique_pe_hashes": len(binaries),
        "pe_sha256": dict(sorted(binaries.items())),
        "zip_metadata": archives,
        "limitations": [
            "Inventory and hashing are not malware detection.",
            "PE binaries were identified by headers, not executed or decompiled.",
            "ZIP metadata was read; members were not extracted by this script.",
            "Only files in the pinned upstream snapshot are inventoried.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory()
    content = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(json.dumps({key: result[key] for key in (
            "snapshot", "tracked_files", "nonempty_files", "total_bytes",
            "snapshot_blob_mismatches", "pe_files", "unique_pe_hashes",
        )}, indent=2))
    else:
        print(content, end="")
    return 1 if result["snapshot_blob_mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())