# GunZ 1.5 acquisition and security review

Review date: 2026-10-16 (UTC).

## Result

**No confirmed malware was identified, but this is not a malware-free or safe-to-run certification.**
Two ClamAV alerts identify duplicate encrypted Excel workbooks whose contents could
not be fully inspected. Static review found serious legacy security weaknesses and
expected but dangerous updater/administration functionality. Do not launch the
bundled executables, deployment tools, web administration, or anti-cheat components
on a trusted host just because no named malware signature was detected.

No game binaries, repository scripts, build events, installers, or SQL migrations
were executed. Only newly authored inventory/scanner helpers and external inspection
tools were run. No repository files or hashes were submitted to public malware
analysis services. No upstream files were modified or removed.

## Provenance and repository arrangement

- Upstream: <https://github.com/open-gunz/ref-gunz1.5>
- Requested GitHub fork: <https://github.com/AustinJAkerley/ref-gunz1.5>
- Reviewed upstream commit: `d3dae1b7c108c276a715d291d357341af96bafc7`.
- GitHub API confirmed the fork's parent is `open-gunz/ref-gunz1.5`.
- Existing local `origin` remains `git@github.com:AustinJAkerley/GunZ.git`.
- Added `upstream` and `fork` remotes; local `main` tracks `fork/main`.
- Imported source at the local repository root; client and server projects remain
  in their original directory structure, including the duplicated historical tree.
- Acquisition disabled Git hooks, LFS filters and recursive submodule operations.
  The upstream tree contained no symlinks, submodules, Git attributes, GitHub
  workflows, or VS Code workspace automation directories.
- `git fsck --full` passed. Hashing all 10,797 upstream files against their Git
  blob IDs found zero mismatches. This establishes consistency with the public
  snapshot, **not authenticity as an untouched publisher release**.
- The fork operation created the requested remote fork. Review artifacts were
  committed locally only; no subsequent push was performed.

## Antivirus methodology and evidence

- Official image: `clamav/clamav`, pinned to
  `sha256:638d90201ee7ee6a82d249a2fc23b132e578673b5f1f2766852b127676ca1ef6`.
- ClamAV engine: **1.5.4**.
- Updated daily signatures: **28155**, dated **2026-10-16 06:24:17**.
- Loaded signatures: **3,628,169**.
- Signature updates ran separately with network access and **no source mount**.
- Scanning ran with **no network**, a read-only source mount/root filesystem, no
  Linux capabilities, `no-new-privileges`, and PID/memory/CPU limits. Only the
  dedicated report directory and temporary scan space were writable.
- All **10,779 nonempty upstream files** were scanned. The other **18 files are
  empty**, reconciling the total of **10,797**. Total source size: **559,083,577 bytes**.
- Git object storage/history and newly added audit material were excluded. This
  review is of the checked-out snapshot, not every historical commit.
- Archive inspection, all-match reporting, encrypted-content alerts, and scan-limit
  alerts were enabled. No scan-limit, file-access, or parser-error warning was
  reported in the completed scans.
- Limits: 128 MiB/file, 1 GiB expanded scan size, 40 nested levels, 50,000 contained
  files, 120 seconds per file. No upstream individual file exceeded 25 MiB.
- Both the initial completed scan and the repeat using the saved runner produced
  the same two alerts. Scanner exit code **1** represents these alerts, not an
  execution failure. An earlier attempt could not create its log due to container
  UID permissions; this was corrected before the two complete scans.

Evidence: [first scan](reports/clamav.log), [verification scan](reports/clamav-verification.log),
[inventory and binary SHA-256 hashes](reports/inventory.json).

The signature updater also warned that no `clamd` daemon was available for reload.
That is expected: the review uses standalone `clamscan`, which loaded the updated
database successfully. The downloaded image and `gunz-audit-clamav-db` Docker volume
remain available locally for repeat scans; no scanner container is left running.

### The two alerts

- [Original workbook](../DOC/계정%20정리.xls)
- [Duplicate workbook](../Mint2/DOC/계정%20정리.xls)

Both are 33,280-byte legacy Excel compound documents with SHA-256
`8dee544574cbd75d3efdce768d1748991acf50c6408ecb6d3cd3ac91653f339b`.
Both report **`Heuristics.Encrypted.OLE2`**. The scanner summary labels them
“Infected files,” but the actual rule is an encryption/visibility warning, **not a
positive identification of a named virus or Trojan**. Their encrypted contents
remain unresolved. They have not been decrypted, opened in Office, deleted, or
quarantined; keep them unopened until separately assessed.

### Binary and archive coverage

Header inspection identified **108 PE executables/DLLs across 47 unique SHA-256
hashes**, including executable payloads with nonstandard extensions used by the
launcher and GameGuard. Counting only normal executable extensions would miss ten
of these files. All were within the antivirus scan scope.

One duplicated launcher updater is UPX-packed. Packing is not evidence of malware,
but these binaries were not decompiled or proven to match their source. Historical
anti-cheat and publisher-authentication binaries remain opaque trust dependencies.

The two ZIP files are copies of a sample mesh archive, each with 1,217 members and
4,075,080 expanded bytes. Metadata inspection found no encrypted entries or unsafe
member names. They were also included in ClamAV's archive inspection.

## Static-review findings

Severity below concerns potential harm **if the affected component is deployed**;
it does not imply confirmed malicious intent or verified external exploitability.
Secrets encountered during review are not reproduced here.

### High priority: legacy web administration

- [Configuration rewriting](../GunZ%20Web%20Components/GunzAdmin/config.html#L5-L29)
  uses a fixed password, lacks the normal session check, and writes posted values
  into PHP configuration source. Do not deploy this endpoint.
- [Login queries](../GunZ%20Web%20Components/GunzAdmin/login_action.php#L6-L25)
  interpolate request values into SQL without parameterization.
- [Session checking](../GunZ%20Web%20Components/GunzAdmin/lib/helper_api.php#L25-L35)
  does not enforce operator roles; account-management handlers accept privileged
  changes after only this check. These are access-control weaknesses, not evidence
  of a concealed malware payload.
- Runtime/admin configurations contain plaintext service/database credentials.
  Treat committed credentials as compromised; never reuse them. This review did
  not test whether any historical credential is still valid.

### High priority: management and patch execution

- [ServerKeeper manager connection](../ServerKeeper/MServerKeeper_Command.cpp#L329-L355)
  records the sender as manager without authentication in that handler. Later
  control commands trust the recorded UID. Lower-layer protections and network
  reachability were not fully traced, so this is a serious trust-boundary concern,
  not a demonstrated network exploit.
- [FTP update transport](../ServerKeeper/Updater.cpp#L15-L44) and
  [patch execution](../ServerKeeper/MServerKeeper.cpp#L291-L337) form an intended
  deployment mechanism capable of running downloaded scripts/executables. No
  modern signed-update trust chain was established in the inspected path.
- [Torrent completion](../Utils/DownLoader/src/torrent.cpp#L1888-L1906) can execute
  downloaded content automatically when Auto Execute is selected, or with user
  confirmation. This is visible product behavior, not covert execution.
- Historical build/publish scripts delete build outputs and deployment targets,
  invoke bundled helpers, and access network shares/version-control systems.
  Do not run them unchanged on a modern workstation.

### Medium priority: outbound reporting and anti-cheat

- [Abuse reporting](../Gunz/ZReportAbuse.cpp#L32-L90) collects report text and recent
  chat and invokes FTP upload using embedded credentials.
- [Crash handling](../MatchServer/ExceptionAttacher.cpp#L151-L189) can upload dumps
  and logs by FTP when its compile-time option is enabled. Dumps may include
  sensitive process memory. These are identifiable reporting functions, not proven
  covert exfiltration.
- [Debug server polling](../MatchServer/MatchServer.cpp#L207-L222) makes periodic
  requests to a historical internal HTTP endpoint. The inspected response path
  did not execute downloaded content.
- [HackShield startup](../Gunz/main.cpp#L1412-L1435) and related GameGuard/XTrap
  integrations invoke intrusive third-party anti-cheat functionality. Source
  integration alone cannot establish the safety of their bundled binaries.

## Limits and recommended next step

Targeted static review searched scripts/build events, process launch, persistence,
injection, encoded execution, updater/reporting flows, authentication, and operator
commands. It did not identify a confirmed credential stealer, concealed command
channel, or unconditional hidden game-login password. This was **not** exhaustive
line-by-line verification, binary reverse engineering, dynamic sandboxing,
cryptographic publisher-signature validation, or a multi-engine malware scan.

Do not interpret negative signature results as proof of safety. Before a runnable
local build: replace historical credentials/endpoints, isolate or remove legacy
management/web/deployment utilities, review anti-cheat dependencies, and use a
disposable VM with no personal files or credentials and restricted networking.
Those hardening changes have **not** been applied in this acquisition/review task.

## Reproducing the review

- [inventory.py](inventory.py) inventories the pinned upstream snapshot, verifies
  working-file Git blob hashes, and records PE SHA-256 hashes and archive metadata.
  Its `--output` option writes a JSON report.
- [scan.py](scan.py) uses the pinned ClamAV image and offline source mount.
  `--update` refreshes signatures separately; `--log-name` selects a new report
  filename. Existing logs are deliberately not overwritten. Docker access is
  required; in Flatpak VS Code run it on the host through `flatpak-spawn --host`.
- Scanner exit codes are preserved: `0` = no alerts, `1` = detections/heuristics,
  `2` = scanner error. The current snapshot is expected to return `1` because the
  encrypted workbooks remain present.