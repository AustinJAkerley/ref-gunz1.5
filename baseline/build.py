#!/usr/bin/env python3
"""Run the real Windows source build in its isolated toolchain container."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--target", nargs="+", default=["Gunz", "MatchServer"])
    args = parser.parse_args()
    base = ["flatpak-spawn", "--host", "docker", "run", "--rm", "--user", "1000:1000",
            "--env", "HOME=/work/reference-home", "--env", "WINEPREFIX=/work/reference-home/compiler-wine",
            "--env", "WINEDEBUG=-all", "--mount", f"type=bind,source={ROOT}/build,target=/work",
            "--mount", f"type=bind,source={ROOT}/baseline,target=/baseline,readonly",
            "gunz-baseline-toolchain:local"]
    if args.configure:
        command = ["cmake", "-S", "/baseline", "-B", "/work/reference-win32", "-G", "Ninja",
                   "-DCMAKE_TOOLCHAIN_FILE=/baseline/msvc-toolchain.cmake", "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_CXX_FLAGS=/DWIN32_LEAN_AND_MEAN /FI/baseline/compat/build_headers.h", "-DCMAKE_C_FLAGS=/DWIN32_LEAN_AND_MEAN"]
    else:
        result = subprocess.run(base + ["python3", "/baseline/compile_shaders.py"])
        if result.returncode:
            return result.returncode
        command = ["cmake", "--build", "/work/reference-win32", "--target", *args.target, "--parallel", "6"]
    log = ROOT / "build/reference-win32" / ("configure.log" if args.configure else "build.log")
    with log.open("w") as output:
        result = subprocess.run(base + command, stdout=output, stderr=subprocess.STDOUT)
    text = log.read_text(errors="replace")
    lines = text.splitlines()
    if result.returncode:
        print("\n".join(line for line in lines if any(term in line for term in ("error ", "FAILED:", "CMake Error", "fatal error", "Error:", "LNK")))[:16000])
    else:
        print("\n".join(lines[-12:]))
    print(f"Build exit {result.returncode}; full log: {log}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())