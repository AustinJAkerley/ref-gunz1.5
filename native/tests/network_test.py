"""Exercise two real loopback peers; no legacy binaries or external services."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = str(sock.getsockname()[1])
    with tempfile.TemporaryDirectory(prefix="gunz-native-test-") as directory:
        root = Path(directory)
        with (root / "server.log").open("w+") as log:
            server = subprocess.Popen(
                [sys.argv[1], "--port", port, "--seconds", "7", "--report", str(root / "server.json")],
                stdout=log, stderr=subprocess.STDOUT,
            )
            probes = []
            try:
                # ENet handles connection retries; no fixed startup sleep required.
                for n in range(2):
                    probes.append(subprocess.Popen(
                        [sys.argv[2], "--port", port, "--seconds", "5", "--report", str(root / f"peer{n}.json")],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    ))
                for probe in probes:
                    output, _ = probe.communicate(timeout=12)
                    print(output)
                    assert probe.returncode == 0, output
                assert server.wait(timeout=10) == 0
                reports = [json.loads((root / f"peer{n}.json").read_text()) for n in range(2)]
                assert all(r["ok"] and r["peak_players"] == 2 for r in reports), reports
                assert len({r["id"] for r in reports}) == 2
                assert sum(r["hits"] for r in reports) >= 4, reports
                status = json.loads((root / "server.json").read_text())
                assert status["joined"] == 2 and status["peak_players"] == 2, status
                print("PASS: two clients, movement, jumping, shooting, server damage and snapshots", status)
            finally:
                for process in [*probes, server]:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()


if __name__ == "__main__":
    main()