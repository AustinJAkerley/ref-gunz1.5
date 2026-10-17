# GunZ source + original-engine Wine baseline

**Current gameplay reference: [actual OpenGunZ Windows client under Wine](baseline/README.md).**
Run **GunZ: Play original reference (Wine)** for direct Mansion testing with the
original controller, combat, camera and renderer. This is source-built, not the
native prototype. Audio is currently silent. Original login/registration is verified;
full online room/multiplayer flow remains to be validated.

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
