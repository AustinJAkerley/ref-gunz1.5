# Level-99 loadout, Duel Elo and hit damage

These are explicit patches to the real OpenGunZ build, not the native prototype.
The pinned source and downloaded data stay untouched; [patch_source.py](patch_source.py)
patches generated source copies and [data.py](data.py) prepares matching runtime XML.

## What players receive

- Level **99**, including existing non-deleted characters. XP has a level-99 floor.
- Rusty Sword, **Breaker 8** and **Breaker 9P** equipped. The pinned pack has no
  plain Breaker 9; 9P is its available higher-tier variant. Weapon stats are unchanged.
- **Zaurus B x2** and **Dynax 800C x2** revolvers in inventory.
- Gender-matched **Valkyrie** equipped and **Battle Brood** alternate outfit in
  inventory: five armor pieces each. These are normal high-stat sets, not admin gear.
- **Two permanent Basic Rings**, each **+10 HP / +10 AP**: +20 HP/AP together.
  Same item type, separate inventory instances; never reuse rented gear.
- Medical Kit and Repair Kit in the two custom slots: **20 HP** and **20 AP** per
  pickup, five charges per kit. Restoration clamps to the relevant maximum and
  does not spill into the other stat. Original item-use controls remain unchanged.

Existing characters get the starter equipment once, without removing other owned
items. A transactional version-1 marker prevents duplicates or resetting chosen
equipment at each login. This is the first competitive migration; no earlier
competitive revision was deployed. Future changed grants require a new migration.
New characters receive the grant within original character creation's transaction.
Offline practice uses the same equipped female set and level, but has no persistent
inventory or rated opponent; its ELO column shows `--`.

## Duel rating

- Scoreboard order is **Name → ELO → Clan**, with existing score columns afterward.
- Start **1000 Elo**, K=32. Equal-rated players exchange 16 points; an upset awards
  more. Scores cannot go below zero; each result transfers the same amount.
- **Iron:** below 1000; **Bronze:** 1000–1199; **Silver:** 1200–1499;
  **Gold:** 1500+. **Top 10** overrides the tier at positions 2–10; **Rank 1** is
  first place. Ties sort by character ID. At least one rated result is required
  for a ladder position, so new unplayed characters cannot occupy the top spots.
- Each active **Duel round** counts once, including private rooms. An active
  duellist's death, suicide/environmental death, or departure awards the other
  active player. Draws/timeouts, waiting-queue departures, and countdown departures
  do not count. Bots, same-character and same-account matches are not rated.
- The server resolves character IDs; clients cannot submit Elo values. Snapshots
  refresh every two seconds. Server messages are rejected inside peer tunnels.
- A unique round event prevents kill/disconnect duplicates. Elo and both counters
  commit atomically. An independent SQLite outbox preserves result order across
  game-database locks and process restarts; retries do not depend on connected
  player objects. No five-second SQLite lock wait runs on the game thread.

### Trust and operational limits

This local baseline is **not an anti-cheat-complete public ranked service**.
Original P2P deaths and world-item spawn/pickup messages still trust clients.
Separate accounts can collude; server-based rooms also retain upstream death-report
paths. The displayed ladder is server-persisted, not proof of authoritative combat.
Deploying publicly requires additional death, movement, item and ammunition validation.
The launcher still has no external networking or published ports.

The pending journal is stored alongside the game database. Back up/restore them
as a consistent pair after migration. If the journal itself cannot be written
(for example a full disk), results remain in memory and the server logs the error;
power loss in that failure state can lose unjournaled results. Normal game-DB lock
contention is durable and retried in FIFO order.

## Damage on the hit marker

The shooter sees a short-lived number below the crosshair. Shotgun pellets are
summed into one shot total, rather than separate pellet popups. Replays/spectating
do not show the local shooter's number, and misses/guarded/invulnerable targets
do not generate new local numbers.

- **P2P:** the local hit calculation, explicitly labeled `(P2P)`. It is predicted
  weapon damage, not a promise about the remote player's actual HP/AP loss.
- **Server-based:** actual HP+AP removed by the server, excluding overkill and
  self-damage; nearby receipts are combined within 50 ms. That time window is an
  approximation, not a network shot identifier. Original server/client invulnerability
  differences remain part of the upstream combat implementation.

## Applying or rolling back

Close and reopen using the existing desktop launcher. No session is restarted by
the build. On next launch the matching binaries/XML are copied, a pre-competitive
SQLite backup is saved under the runtime backups directory, and the server migrates
existing characters transactionally. The backup must succeed before the server starts.
Later launches preserve inventory choices and do not repeat grants.

To roll back, stop the session first, retain a copy of both current databases,
restore the pre-competitive backup, and use the previous matching client/server and
runtime data. Do not combine an old database with a newer pending-results journal.
Merely restoring the DB while leaving this build enabled will migrate it again.

## Verification (without opening the game)

- Python suite: launcher behavior, temporary SQLite backup, XML overlays, command
  ID uniqueness, exact patch anchors, and compiled **actual inserted Duel hooks**.
- Native C++: actual SQLite grant/rating/outbox implementation; rollback, duplicate
  results, rental exclusion, distinct rings, FIFO recovery, locked DB, restart,
  commit-before-ack replay, ranking, and damage-event lifetime.
- Windows console integration target: actual patched SQLiteDatabase create/reopen;
  full shared command table, wire serialization, actual client rating text and
  peer-tunnel rejection; actual client/server item and world-item XML loading.
  Fresh temporary DB and compiler Wine prefix only.
- [../tests/smoke_server.py](../tests/smoke_server.py): generates temporary overlays,
  runs the real XML loaders, then starts the full MatchServer with a fresh scratch
  database and checks its ready marker and TCP listener. Disposable network-isolated
  container, compiler Wine prefix and no desktop access; never uses the live DB.
- [../verify.py](../verify.py): unchanged controller/physics/camera/animation hashes
  and exact expected feature patches, plus the current executable hashes.

The updated HUD and a complete two-player Duel have **not** been visually/live
tested. These checks do not launch, focus, capture or change the current game session.

### XML compatibility regression

The engine's XML wrapper matches literal `xml` and `ITEM` names, not namespace-aware
names. ElementTree's default `ns0:` serialization produced valid XML that both
original loaders rejected, preventing MatchServer from starting. The overlay now
preserves the original **default namespace** and uses it for the new ring too.
Tests cover the literal serialized names and the actual Windows engine loaders;
reparsing with ElementTree alone is not sufficient. The launcher waits for the real
server-ready marker and TCP listener before opening the client, and surfaces startup
failures rather than leaving players at an unusable login screen.