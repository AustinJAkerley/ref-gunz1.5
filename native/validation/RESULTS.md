# Native slice validation — 2026-10-16

This record describes the first native testing slice, not a completed GunZ port.

## Verified

- Linux x86-64 Debug: GCC 15.2, CMake 4.3.3, SDL2 2.32.70, raylib 5.5, ENet 1.3.18.
- Original CRC helper compiles natively; its standard CRC-32 vector passes.
- Core suite: **10,207 checks** including malformed packets, movement/collision,
  target/player damage, no death-tick attack, respawning and sequence wraparound.
- Two real loopback peers connected simultaneously; snapshots included both IDs;
  movement, jumping, shooting and server-confirmed target hits passed.
- Both CTest suites passed in ordinary Debug and in an ASan/UBSan headless build.
- Real Wayland/OpenGL client opened, connected, rendered and exercised scripted
  combat/movement. Its final smoke before documentation reported **668 frames,
  180 snapshots, eight hits, 33 shots and 1.54583 m maximum jump height** over six
  seconds. Repeats may vary with desktop scheduling.
- Windows x86-64 Release: MinGW GCC 12 cross-build of client/server/probe succeeds
  using the same project sources plus source-built raylib/GLFW and ENet.
- Windows import inspection showed only common system DLLs: GDI32, KERNEL32,
  msvcrt, SHELL32, USER32, WINMM and WS2_32. No historical game/vendor DLLs.
- Linux link inspection showed system SDL2, standard C/C++ runtime/math libraries,
  and newly source-built project/raylib/ENet archives. OpenGL is loaded by the
  platform backend. No legacy binary input was linked.

## Environment notes

Linux validation runs inside the existing VS Code Flatpak SDK on this computer.
Its Wayland socket is available; the sandbox does not expose the host X11 socket.
SDL successfully renders through Wayland despite Mesa/NVIDIA EGL probe warnings.
The specific GPU acceleration path was not established; observed FPS is not a
benchmark or guarantee of hardware acceleration. Built Linux binaries currently
depend on the SDK runtime and are not yet portable distribution packages.

The Windows compiler/container is only a build tool. **Windows runtime behavior
and MSVC builds have not been tested.** No Windows game binary was run under Wine.

Initial screenshot verification caught raylib's screenshot helper discarding path
components; explicit screen-image export fixed this and the smoke was repeated.
Initial Windows configuration caught ENet's plain/keyword CMake linkage mismatch;
the build graph was corrected and the cross-build passed. The unused raylib audio
module is disabled, avoiding obsolete unused decoder code and compiler warnings.

## Evidence and reproducibility

The [native guide](../README.md) describes build/run/test steps. Tests remain in
source control. Generated executables, fetched dependency source, test logs and
screenshots are intentionally ignored rather than committed. The local smoke
outputs are available in the native artifacts directory; CTest logs reside in each
build directory. Re-running the smoke overwrites its previous local evidence.

No original binaries/scripts, external game services or historical database
migrations were executed. No external game assets were needed for this slice.