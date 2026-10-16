#!/usr/bin/env python3
"""Run official ClamAV offline against a read-only source mount, not game code.

On a normal host, use Python directly. In Flatpak VS Code, run this script
through flatpak-spawn --host. Docker must already be accessible to the user.
The optional signature updater has network access but no source mount.
"""

import argparse
import os
from pathlib import Path
import subprocess


IMAGE = (
    "clamav/clamav@sha256:"
    "638d90201ee7ee6a82d249a2fc23b132e578673b5f1f2766852b127676ca1ef6"
)
DATABASE = "gunz-audit-clamav-db"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Refresh signatures first")
    parser.add_argument("--log-name", default="clamav-rescan.log")
    args = parser.parse_args()
    if args.log_name != Path(args.log_name).name or args.log_name in (".", ".."):
        parser.error("--log-name must be a filename without directories")
    reports = ROOT / "security" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    log = reports / args.log_name
    if log.exists():
        parser.error("Log already exists; choose a new --log-name to preserve evidence")

    if args.update:
        subprocess.run([
            "docker", "run", "--rm", "--user", "clamav", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "128",
            "--memory", "2g", "--mount",
            f"type=volume,source={DATABASE},target=/var/lib/clamav",
            "--entrypoint", "freshclam", IMAGE,
            "--stdout", "--log=/tmp/freshclam.log", "--datadir=/var/lib/clamav",
        ], check=True)

    base = [
        "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "128",
        "--memory", "3g", "--cpus", "2",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
        "--mount", f"type=volume,source={DATABASE},target=/var/lib/clamav,readonly",
    ]
    subprocess.run(base + ["--entrypoint", "clamscan", IMAGE, "--version"], check=True)
    command = base + [
        "--mount", f"type=bind,source={ROOT},target=/scan,readonly",
        "--mount", f"type=bind,source={reports},target=/reports",
        "--entrypoint", "clamscan", IMAGE,
        "--recursive", "--infected", "--allmatch", "--scan-archive=yes",
        "--alert-encrypted=yes", "--alert-exceeds-max=yes",
        "--max-filesize=128M", "--max-scansize=1024M", "--max-recursion=40",
        "--max-files=50000", "--max-scantime=120000",
        r"--exclude-dir=^/scan/(\.git|security)(/|$)",
        f"--log=/reports/{args.log_name}", "/scan",
    ]
    result = subprocess.run(command)
    print(f"ClamAV exit code: {result.returncode}; report: {log}")
    print("0 = no alerts, 1 = detections/heuristic alerts, 2 = scan error")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())