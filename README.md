# GunZ 1.5 reference + native Linux/Windows lab

The original reference source remains in its historical directories. A new,
source-built native testing slice is available in [native](native/README.md).

**Current status:** Linux client/server running locally in Mansion with textured
characters, katana animations and source-informed sword controls;
Windows client/server cross-build verified. This is **not yet the full GunZ 1.5
port** and uses a new loopback test protocol rather than the original protocol.

In the Projects VS Code workspace, run **GunZ: Play native locally** to build and
launch both. No bundled legacy executables, DLLs, libraries or object files are used.

- [Build, play, controls and limitations](native/README.md)
- [Validation record](native/validation/RESULTS.md)
- [Katana behavior and remaining parity gaps](native/GAMEPLAY_PARITY.md)
- [Imported-source security review](security/REVIEW.md)
