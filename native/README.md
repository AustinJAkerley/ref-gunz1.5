# GunZ native testing slice

**A running foundation, not a completed port of GunZ 1.5.** The native server and
client use a new test protocol and generated geometry. They do not interoperate
with historical GunZ clients/servers. The original gameplay, animation, item,
resource, lobby, database and network subsystems have not been ported wholesale.

## What runs today

- Native 64-bit Linux headless server and OpenGL third-person client.
- Windows 64-bit executables cross-compiled from the same C++ sources; Windows
  runtime testing is still outstanding.
- A generated arena with walls, cover, steps, a character proxy, targets and HUD.
- Movement, collision, jump buffering, wall rebound, dash, hitscan fire and melee.
- Server-owned movement, hit detection, health, scoring and respawning, at 60 Hz.
- Two or more local clients, up to eight; 30 Hz snapshots. No external account,
  database, publisher, patch, billing or anti-cheat service.
- Original CRC implementation compiled with a small fixed-width portability
  guard; original gravity/fall constants directly included. Other movement values
  are drawn from the original character code, scaled from centimetres to metres.
  Movement is a new approximation, **not verified K-style/animation parity**.

This initial slice is silent. It uses box collisions and generated capsule/box
graphics, not the original BSP/ELU engine. Networking has no prediction, rewind,
lag compensation, account persistence, reconnection, encryption or authentication.
The server is deliberately bound to **127.0.0.1 only**. CRC detects corruption; it
is not a security/authentication mechanism. Do not expose this test protocol.

## Play on this computer

In the Projects workspace, run **Tasks: Run Task → GunZ: Play native locally**.
It builds the current code, starts a loopback server, opens the native client and
stops its own server when the client closes. This machine builds/runs inside the
VS Code Flatpak Linux SDK, which already provides SDL2 and Wayland graphics support.
The resulting ELF binaries may require that SDK's newer C/C++ runtimes; do not
assume they are standalone host-distribution packages yet.

Click inside the game window to capture the mouse.

- **W/A/S/D** — move; **mouse** — aim.
- **Space** — jump; near a wall in the air, rebound.
- **Left Shift** — dash (short cooldown).
- **Left mouse** — fire; **right mouse** — melee.
- **R** — return to spawn; **F11** — fullscreen.
- **Esc** — release mouse; press again to exit.

The native server has no interactive console. The launcher writes logs into the
ignored artifacts directory. For a second player, leave that session running and
run **GunZ: Open second native client**. The first launcher owns the server lifetime.
Two overlapping desktop windows compete for mouse focus; each releases capture
when focus is lost.

## Build from source

Required: C++17 compiler, CMake 3.24+, Ninja (or another CMake generator). The first
configure downloads **source archives only**, verified against pinned SHA-256
hashes in the [root build graph](../CMakeLists.txt).

Linux additionally needs SDL2 development headers, OpenGL/Mesa and a working
Wayland or X11 session. Debian/Ubuntu package names include `build-essential`,
`cmake`, `ninja-build`, `libsdl2-dev`, and `libgl1-mesa-dev`.

From the repository root:

```sh
cmake -S . -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Debug -DPLATFORM=SDL
cmake --build build/native --parallel 4
ctest --test-dir build/native --output-on-failure
python3 native/run_local.py
```

For X11 use `SDL_VIDEODRIVER=x11`; Wayland uses `SDL_VIDEODRIVER=wayland` if automatic
selection needs help. The workspace task selects Wayland for this computer.

For **Windows**, use a Visual Studio C++ developer shell or MinGW with CMake and
Python 3. Windows uses raylib's source-built GLFW backend rather than requiring SDL:

```powershell
cmake -S . -B build/windows-native -DPLATFORM=Desktop
cmake --build build/windows-native --config Release --parallel 4
ctest --test-dir build/windows-native -C Release --output-on-failure
python native/run_local.py --build build/windows-native/Release
```

For single-configuration Ninja/MinGW omit `/Release` in the launcher's build path.
MSVC configuration is supported by the build graph but **only MinGW cross-building
has been verified so far**. The local Windows outputs are under the ignored Windows
cross-build directory. They are newly built from these sources, not reused binaries.

The optional [MinGW toolchain](cmake/mingw64.cmake) and
[compiler container](validation/Windows.Dockerfile) document the Linux-to-Windows
build setup. Container build uses a read-only source mount and a writable output
mount. No game binary is installed or run in that compiler container.

Headless server-only builds use `-DGUNZ_BUILD_CLIENT=OFF`; no graphics development
packages or display are needed. `-DGUNZ_SANITIZE=ON` enables ASan/UBSan for native
project code on GCC/Clang. ENet itself is not instrumented by this option.

## Reproduce validation

```sh
ctest --test-dir build/native --output-on-failure
python3 native/run_local.py --smoke --port 27651
```

The graphical smoke opens a **real window**, connects to the server, fires, jumps,
captures a screenshot and verifies server-confirmed hits and jump height. It
requires an active desktop and writes ignored logs, JSON and an image. It is not
a headless renderer test. The client can briefly take desktop focus.

The CTest network test starts two actual ENet clients on an ephemeral loopback UDP
port, verifies both are present, checks movement/jumping/firing and target damage,
then terminates its child processes. Core tests cover CRC vectors, physics,
wall collision/rebound, target/player damage, respawning, occlusion, sequence
wraparound, packet truncation, bounds checks, NaNs and malformed packets.

## Dependency and asset policy

- **raylib 5.5** — zlib license; compiled locally from source; bundled GLFW also
  source-built for Windows. Linux uses the common system SDL2/OpenGL libraries.
- **ENet 1.3.18** — MIT license; compiled locally from source.
- Standard compiler/runtime/OS graphics libraries are allowed common dependencies.
- No historical EXE, DLL, LIB or OBJ is used as a native build input. Those files
  remain in the archival source tree but are not loaded, invoked, copied or linked.
- No external models, textures, sounds, maps, binaries or installers were fetched.
  Arena geometry and character/target proxies are generated by the new code.
- External dependencies retain their upstream license files in fetched source
  directories. The existing GunZ source is not being relicensed by this work.

## Source layout

- [src/world.cpp](src/world.cpp) — new deterministic fixed-step simulation and
  generated arena; original tuning references documented above.
- [src/protocol.cpp](src/protocol.cpp) — explicitly serialized, little-endian,
  versioned, bounded messages; no host-struct memcpy across the wire.
- [src/server.cpp](src/server.cpp) — loopback authority, peer mapping, input timeout
  and receive-rate cap; no historical MatchServer executable dependencies.
- [src/client.cpp](src/client.cpp) — native window, rendering, controls and HUD.
- [src/network.cpp](src/network.cpp) — small cross-platform ENet adapter.
- [run_local.py](run_local.py) — local session lifecycle and graphical smoke.
- [tests/core_tests.cpp](tests/core_tests.cpp) — simulation/protocol regression tests.
- [tests/network_test.py](tests/network_test.py) — real two-client integration test.

## Next milestones

1. Original-format bounded BSP/ELU/animation loaders with sample fixtures and tests.
2. Asset inventory and verified source/data provenance; no arbitrary game installers.
3. Port more original movement/combat rules; add animation and timing parity tests.
4. Client prediction/reconciliation and interpolation, followed by real latency tests.
5. Local equipment, lobby and persistence; then additional modes and maps.
6. Windows runtime validation and portable Linux packaging outside the Flatpak SDK.

The earlier [security review](../security/REVIEW.md) applies to the imported snapshot,
not to a finished game or a security certification of this new native code.