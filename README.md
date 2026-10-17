# GunZ source + original-engine Wine baseline

**Current gameplay reference: [actual OpenGunZ Windows client under Wine](baseline/README.md).**
Open **GunZ (Local)** from your desktop/application menu, or run [play.sh](play.sh)
for login/signup. Use `--practice` for direct Mansion testing with the
original controller, combat, camera and renderer. No VS Code task is required.
The Python entry point is [launch.py](launch.py). This is source-built, not the
native prototype. Audio is currently silent. Original login/registration is verified;
full online room/multiplayer flow remains to be validated.

The next-launch update adds [level-99 starter gear, Duel Elo and hit damage](baseline/competitive/README.md):
Breaker 8/9P, revolvers, two outfits, two +10 HP/+10 AP rings, 20-point HP/AP packs,
and ELO before Clan on the scoreboard. Existing characters migrate once after an
automatic database backup. Offline practice shares the equipped loadout; ratings
require a real Duel. Build/isolated tests are verified; live multiplayer/HUD validation
and public-service anti-cheat hardening remain outstanding.

## Preserved native experiment

The original reference source remains in its historical directories. A new,
source-built native testing slice is available in [native](native/README.md).

**Current status:** Linux client/server running locally in Mansion with textured
characters, katana animations and source-informed sword controls;
Windows client/server cross-build verified. This is **not yet the full GunZ 1.5
port** and uses a new loopback test protocol rather than the original protocol.

The **GunZ: Play native locally** task still exists for the earlier experiment,
but it is not the reference for GunZ gameplay feel. No bundled legacy executables,
DLLs, libraries or object files are used by that target either.

- [Build, play, controls and limitations](native/README.md)
- [Validation record](native/validation/RESULTS.md)
- [Katana behavior and remaining parity gaps](native/GAMEPLAY_PARITY.md)
- [Imported-source security review](security/REVIEW.md)
