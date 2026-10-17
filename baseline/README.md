# Actual GunZ Windows/Wine reference baseline

**Use this baseline to judge the feel. The raylib native experiment is preserved,
but is no longer the gameplay reference.** This build compiles OpenGunZ's actual
`Gunz` and `MatchServer` targets using Microsoft C++ under Wine. It is not a new
controller or renderer imitating GunZ.

## Run on this computer

Use **GunZ (Local)** in your desktop application menu, or double-click the
**GunZ** desktop shortcut. No VS Code window or task is involved.
The window title is **Open GunZ**, not “Native Lab”.

The standalone entry points are [play.sh](../play.sh) and [launch.py](../launch.py)
in the repository root. Both work from any current directory. Default is the
login/signup screen; `--practice` enters the original offline Mansion test mode.

```sh
./play.sh
./play.sh --practice
./play.sh --check
python3 launch.py --install-shortcut
```

`--check` verifies prerequisites without starting a container/game/server.
`--install-shortcut` installs desktop/menu launchers and does not open the game.
If the desktop asks, select **Allow Launching** or **Trust** for the shortcut.

### What the launcher does

1. Checks Python/Docker, the already-built game files, local Wine image and display.
2. Refuses duplicate sessions without restarting or focusing the existing game.
3. Starts an isolated Docker container with Wine and the persistent project cache.
4. Prepares runtime data/configuration and starts MatchServer, then the login client.
5. When the client closes, stops its Wine processes/server and removes the container.
  Accounts, characters, settings and logs remain in the project build cache.

It does **not** build the project, download anything, publish network ports or
depend on VS Code. Docker, the prepared Wine image and game data are still required;
this is a launcher for this local installation, not yet a general distributable.

- `--practice` enters **Mansion directly using the upstream standalone test
  mode**. The test character is named Dogs, with the Rusty Sword, **Breaker 7**
  (primary, item 6002) and **Breaker 8** (secondary, item 6004).
  This mode bypasses the lobby through the original built-in test harness; it is
  not a multiplayer match connected to MatchServer.
- The matching original MatchServer runs alongside it in the same isolated
  container. Default launch opens the genuine login/registration/character UI
  against that server.
- Only one reference session runs at once. Exit the game before switching modes.
- Original controls: WASD, directional double-tap dash/tumble, Space jump,
  Shift block, mouse attacks, number keys/scroll for equipment. In the test loadout,
  **1 selects the sword; 2 and 3 select the two shotguns**. Input bindings can be
  changed in the original options UI. Weapon damage, ammo and delays are unchanged.
- The baseline is **silent**. No proprietary FMOD or third-party voice-chat DLL is
  loaded. Original gameplay, physics, camera and animation source is unchanged.
- Original OpenGunZ is a community-modified 1.0-lineage game, not a promise of
  untouched retail or 1.5 behavior. The purpose is to establish a real engine
  reference that the user can assess before further porting.

## Verified so far

- Microsoft x86 Release compilation of the real game and matching server succeeds.
- Used D3D shaders are rebuilt from the original HLSL using the Microsoft SDK.
- Real Direct3D9 client runs under Wine and logs **ZGame Created** for Mansion.
- Window capture shows the original HUD, weapon icons, character and map rendering.
  Weapon switching to Rusty Sword, jumping and camera input were exercised.
- Real account registration succeeded through the original UI/protocol. SQLite
  contains the account and a hashed password verifier. Login reached the real
  character-selection screen. No authentication bypass or plaintext DB password.
- **Online character creation, room creation and a two-client multiplayer match
  have not yet been completed.** Direct Mansion play is the verified gameplay path.
- [verify.py](verify.py) compares key compiled controller/combat/camera/animation
  sources with the pinned original checkout and records hashes and runtime evidence.

This is a functioning reference for controls and movement, not a declaration that
every feature, quest or online flow is complete. User confirmation of dash/block,
butterfly and other technique feel is still required.

## Source and dependency provenance

Revisions are recorded in [sources.json](sources.json):

- OpenGunZ: `b46e3e119e9be671c4a78edd34c15f951f49c528`.
- Client data: `open-gunz/ogz-client` at `6b370b78e39ae7a2a8c266aceb9086a867e3181b`.
- Server data: `open-gunz/ogz-server` at `babf92e67c307d1f7b0103c65c88e883ef20afb6`.
- msvc-wine downloader/wrappers: `514f8ea34842cd6d831804d0e9658d3a32870ae1`.

No downloaded game EXE/DLL/LIB/OBJ is linked, copied into the runtime, or executed.
The data fetcher accepts an explicit set of data extensions, verifies Git blob
hashes/sizes, rejects executable magic, skips the bundled FMOD/GDI+ DLLs, and
downloads Mansion only from the maps directory. Runtime images/models/XML remain
community snapshot data, not verified pristine retail assets. No downloaded game
art is committed to Git.

Common dependencies are compiled from source: vendored libsodium/SQLite/ImGui/INI,
pinned zlib 1.3.1 and Bullet 2.85.1. System Wine provides Windows APIs/Direct3D/GDI+.
Microsoft compiler/SDK libraries are standard build dependencies downloaded from
Microsoft; these nonredistributable toolchain files remain in the local cache.
The game imports only common Windows system DLLs, not FMOD.

## Build-only adaptations (not replacement gameplay)

- A separate CMake graph preserves upstream's unity-build arrangement.
- Standard headers and Windows macro hygiene are supplied for the modern SDK.
- GDI+ text backend selected, as in the upstream build configuration.
- Voice chat disabled through the existing feature flag.
- A small source-built **null-audio FMOD ABI** adapter replaces the proprietary
  audio runtime. It produces no sound and does not simulate gameplay.
- Obsolete `dxerr` diagnostic strings provided by source, not a binary helper.
- Existing `_LOCATOR` branch disabled to use the original direct `SERVER0` list.
  Authentication and game networking remain the original implementations.
- Shader bytecode headers regenerated from original HLSL, not reused as blobs.
- The standalone test harness changes only two ranged item IDs for the requested
  dual-shotgun loadout. This does not alter online inventory or weapon mechanics.
- No native prototype code is part of this target.

The original source clone is untouched. Build-stage copies change the voice
feature flag, binary-library pragma directives, and those two practice-loadout IDs.
Gameplay file comparisons normalize line endings; their content must otherwise
match. Verification checks the entire practice harness against the original with
exactly those two substitutions—no broad exemption from source checking.

## Isolation and operational limits

The runtime container has **no external networking**, no published host ports, no
Linux capabilities and no-new-privileges. Client/server communicate through its
private loopback. The only persistent writable data is the project build cache.
No host home directory or Docker socket is mounted inside it.

The host X11 socket is shared so the game window can appear. This is **not a strong
malware sandbox**: X11 access grants desktop interaction. Downloaded data was not
executed; game executables were built locally. Source provenance is not a safety
proof. Do not put real credentials or production data in this test environment.

Rendering is currently forced through Mesa software OpenGL for a predictable
Wine path on this machine. FPS varies, and this is not representative of native
GPU performance. Hardware acceleration/Proton/DXVK tuning is subsequent work.

## Reproduce from scratch

The one-time developer setup currently uses host Docker and `flatpak-spawn`.
The installed desktop launcher itself needs only host Python 3 and Docker, not
Flatpak or VS Code. No host package
installation or administrator password is required. Build tools are installed in
the [container](Toolchain.Dockerfile). A fresh Microsoft SDK install requires
accepting [Microsoft's license](https://go.microsoft.com/fwlink/?LinkId=2086102).

```sh
python3 baseline/setup.py --accept-msvc-license
./play.sh
```

Incremental build and login mode:

```sh
python3 baseline/build.py --configure
python3 baseline/build.py
./play.sh
python3 baseline/verify.py
```

The public launcher uses the current user's UID/GID and desktop `DISPLAY`, with
optional read-only Xauthority forwarding. Wayland desktops need Xwayland available.
The build/setup helpers still target this machine's UID 1000. [run.py](run.py)
remains a compatibility wrapper for developer scripts and keeps its old practice
default. The generated 32-bit Windows EXEs
can also run with their matching runtime data on Windows, but a physical Windows
machine has not been tested here.

## Local outputs (ignored by Git)

- Real source checkout and Microsoft SDK: under the repository's build cache.
- Compiled binaries: reference-win32 output directory.
- Matched data and runtime: reference-data and reference-runtime directories.
- Separate Wine prefixes: reference-home/compiler-wine and reference-home/game-wine.
- Original client logs: Wine user's Documents/Open GunZ/Logs.
- Server console/logs and SQLite DB: reference-runtime/server.
- Screenshot and verification JSON: reference-runtime.
- Disposable test account: protected local JSON in reference-runtime; password
  never printed or committed. The UI test helper is for that account only.

Known data warnings include absent optional great-sword clips/effect descriptor,
unused map banners/navigation and quest-drop entries. The tested Mansion + Rusty
Sword path runs; these warnings prevent claiming a complete all-content release.

## Next step

Validate the real controller's feel with the user first. Preserve this build as the
reference, then port platform boundaries one at a time with input/replay comparisons.
Do not return to replacing the controller with approximated motion constants.