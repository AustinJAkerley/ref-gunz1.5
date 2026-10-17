#!/usr/bin/env python3
"""Launch only the freshly built native server/client; terminate our server on exit."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=root / "build/native")
    parser.add_argument("--port", type=int, default=27650)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--synthetic", action="store_true", help="Use the old generated regression arena")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    build = args.build.resolve()
    suffix = ".exe" if os.name == "nt" else ""
    server = build / f"gunz-server{suffix}"
    client = build / f"gunz-client{suffix}"
    if not server.is_file() or not client.is_file():
        parser.error("Native executables missing: build the CMake native targets first")
    artifacts = root / "native/artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    # Refuse to use another service accidentally. ENet binding remains authoritative.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", args.port))
    command = [str(client), "--port", str(args.port)]
    assets = root / "native/assets/converted"
    asset_args = []
    if not args.synthetic:
        if not (assets / "mansion.gza").is_file():
            parser.error("Mansion assets missing: run native/tools/fetch_assets.py and convert_assets.py first")
        asset_args = ["--assets", str(assets)]
        command += asset_args
    if args.smoke:
        command += ["--smoke", "--seconds", "6", "--screenshot", str(artifacts / "arena.png"),
                    "--report", str(artifacts / "client-smoke.json")]
    process = None
    with (artifacts / "server.log").open("w") as server_log, (artifacts / "client.log").open("w") as client_log:
        try:
            process = subprocess.Popen([str(server), "--port", str(args.port), *asset_args], stdout=server_log, stderr=subprocess.STDOUT)
            print(f"Native loopback server PID {process.pid}; launching client. Logs: {artifacts}", flush=True)
            result = subprocess.run(command, stdout=client_log, stderr=subprocess.STDOUT,
                                    timeout=30 if args.smoke else None)
            if result.returncode:
                print((artifacts / "client.log").read_text(errors="replace"))
                return result.returncode
            if args.smoke:
                report = json.loads((artifacts / "client-smoke.json").read_text())
                print(json.dumps(report, indent=2))
                assert report["ok"], report
                assert (artifacts / "arena.png").is_file(), "Missing rendered screenshot"
                print("PASS: real window, server-timed katana attacks, hits, jump, dash, guard and uppercut.")
            return 0
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    sys.exit(main())