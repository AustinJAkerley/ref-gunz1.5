# GunZ loadout, Duel ranking, GBucks and hit damage

These are explicit patches to the real OpenGunZ build, not the native prototype.
The pinned source and downloaded data stay untouched; [patch_source.py](patch_source.py)
patches generated source copies and [data.py](data.py) prepares matching runtime XML.

## What players receive

- **No player level or EXP progression.** Names, player lists, HUD, results,
  equipment descriptions and rooms do not show/use progression requirements.
  Legacy database/protocol fields remain at the existing internal compatibility
  floor; they are not a gameplay system and are never converted into currency.
- Rusty Sword, **Breaker 8** and **Breaker 9P** equipped. The pinned pack has no
  plain Breaker 9; 9P is its available higher-tier variant. Weapon stats are unchanged.
- **Zaurus B x2** and **Dynax 800C x2** revolvers in inventory.
- Gender-matched **Valkyrie** equipped and **Battle Brood** alternate outfit in
  inventory: five armor pieces each. These are normal high-stat sets, not admin gear.
- **Two permanent Basic Rings**, each **+10 HP / +10 AP**: +20 HP/AP together.
  Same item type, separate inventory instances; never reuse rented gear.
- Medical Kit and Repair Kit in the two custom slots: **20 HP** and **20 AP** per
  pickup, five charges per kit. Restoration clamps to the relevant maximum and
  does not spill into the other stat. **4/5 select the packs** with default bindings;
  use the normal attack action to deploy them. Mouse wheel/next/previous cycle only
  **melee → primary → secondary**, skipping empty slots and returning to that list
  from either pack. Custom user keybindings remain unchanged.

Existing characters get the starter equipment once, without removing other owned
items. A transactional version-1 marker prevents duplicates or resetting chosen
equipment at each login. This update does not reset inventory choices or regrant
previously awarded equipment. Future changed grants require a new migration.
New characters receive the grant within original character creation's transaction.
Offline practice uses the same equipped female set, but has no persistent
inventory or rated opponent; its ELO column shows `--`.

## Duel rating

- Scoreboard order is **Name → ELO → Rank → Clan**, followed by kills/deaths/ping.
  ELO is numeric, Rank is the separate tier. The old EXP column is removed, not
  relabeled GBucks. Quest HP/AP remains available in its previous space.
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

The Elo and GBucks pending journals are stored alongside the game database.
Back up/restore all three together after migration. If a journal cannot be written
(for example a full disk), results remain in memory and the server logs the error;
power loss in that failure state can lose unjournaled results. Normal game-DB lock
contention is durable and retried in FIFO order.

## GBucks (the former Bounty wallet)

**Bounty is renamed GBucks; EXP is removed, not renamed or exchanged.** Existing
BP balances are preserved. The original BP wallet and purchase transactions remain
the storage/payment mechanism; no separate spending balance is introduced.

- Eligible human PvP kills award **10–20 GBucks**, using stored Duel Elo:
  `round(10 + 10 / (1 + 10^((attackerElo - victimElo)/400)))`.
  Equal Elo gives **15**; an opponent 400 higher gives **19**, 400 lower gives **11**.
  Missing ratings default to 1000. Elo is read inside the first successful settlement
  transaction; under contention it is settlement-time Elo, not a death-time snapshot.
- Stay until the **entire match** completes to receive an additional
  `floor(that match's kill earnings / 2)`. A 100-GBucks match becomes 150 total;
  existing savings are never multiplied. It is not awarded every Duel round.
- Leaving/disconnecting/switching to spectator forfeits that match's completion
  bonus; reconnecting cannot restore eligibility. Already earned kill money stays.
  Zero kills means zero bonus. Abort/server shutdown is not completion.
- No rewards for suicides, same-account kills, teamkills, bots, spectators,
  waiting Duel players, practice/training/skillmap, or quest/NPC outcomes.
- The familiar large blue reward presentation now reads **GBucks +15**, for
  example. It preserves the original blue number/plus artwork and animation;
  the label is generated to match. It receives **server-only committed reward
  notices**, not local death guesses or XP notifications. Completion bonuses use
  the same popup. Queue overflow or a disconnected client may lose a popup, never
  the credited wallet value.
- Transactions, unique event IDs and a durable FIFO outbox prevent duplicate
  currency on retry/restart. A monotonic reward watermark loads with BP in one
  SQL snapshot and updates the live wallet without re-crediting the old BP cache.

### Cosmetic shop

The server catalogue contains **Magician, Halem, Crusader and Ninja**, complete
male/female outfits: **100 GBucks per piece, 500 for five pieces**. All apparel
uses the free Valkyrie piece stats (+4 HP/+20 AP, zero weight), so the purchased
look does not confer extra power. Weapons and rings are not purchasable there.
Selling equipment and quest items is disabled on both server and client, preventing
free starter gear from becoming a currency source. The server checks its catalogue
and funds even if a modified client sends a purchase request directly.

## Damage on the hit marker

The shooter sees **HIT 43** (with the appropriate damage amount) at the original
upper-right HIT position; the old below-crosshair number is removed. Original HIT
pixels are preserved. Digits are generated from Liberation Serif Bold Italic with
the HIT image's sampled orange gradient and matching visible height. They are a
style match, not recovered original digit artwork. The generated atlas is embedded
in the client; no font or digit assets need to be supplied at runtime.
Shotgun pellets are summed into one shot total. **Sword swings/stabs/slashes and
massives now report HIT damage too**, combining eligible targets for one attack.
Guarded, dead, invisible, invincible and self targets do not contribute. Massive
presentation does not add another damage application. Replays/spectating
do not show the local shooter's number, and misses/guarded/invulnerable targets
do not generate new local numbers.

- **P2P:** the local hit calculation. The compact HIT artwork no longer includes
  the old `(P2P)` suffix; changing presentation does not enable server authority. It is predicted
  weapon damage, not a promise about the remote player's actual HP/AP loss.
- **Server-based:** actual HP+AP removed by the server, excluding overkill and
  self-damage; nearby receipts are combined within 50 ms. That time window is an
  approximation, not a network shot identifier. Original server/client invulnerability
  differences remain part of the upstream combat implementation.
  This upstream server has no melee resolver, so local melee numbers remain
  disabled in server-based rooms rather than pretending they are authoritative.
  The current local configuration still defaults/falls back to P2P antilead.

## Applying or rolling back

Close and reopen using the existing desktop launcher. No session is restarted by
the build. On next launch the matching binaries/XML are copied, a pre-GBucks
SQLite backup (pre-competitive for an untouched DB) is saved under the runtime backups directory, and the server migrates
existing characters transactionally. The backup must succeed before the server starts.
Later launches preserve inventory choices and do not repeat grants.

To roll back, stop the session first, retain the game DB and both pending journals,
restore the appropriate pre-update backup, and use the previous matching client/server and
runtime data. Do not combine an old database with a newer pending-results journal.
Merely restoring the DB while leaving this build enabled will migrate it again.

## Verification (without opening the game)

- Python suite: launcher behavior, temporary SQLite backup, XML overlays, command
  ID uniqueness, exact patch anchors, and compiled **actual inserted Duel hooks**.
- Native C++: actual SQLite grant/rating/outbox implementation; rollback, duplicate
  results, rental exclusion, distinct rings, FIFO recovery, locked DB, restart,
  commit-before-ack replay, ranking, and damage-event lifetime.
- GBucks C++ tests exercise 10,001 Elo pairs, eligibility, settlement/popup
  idempotence, cash preservation, completion/leave behavior, locked journals/DB,
  failed commit/ack, delayed deleted-victim replay, and wallet watermark syncing.
- Windows console integration target: actual patched SQLiteDatabase create/reopen;
  full shared command table, wire serialization, actual client rating text and
  peer-tunnel rejection; actual client/server item/world-item/catalogue loading;
  earning, finishing, loading the BP/watermark snapshot and purchasing a cosmetic
  through the real Windows SQLiteDatabase API.
  Fresh temporary DB and compiler Wine prefix only.
- [../tests/smoke_server.py](../tests/smoke_server.py): generates temporary overlays,
  runs the real XML loaders, then starts the full MatchServer with a fresh scratch
  database and checks its ready marker and TCP listener. Disposable network-isolated
  container, compiler Wine prefix and no desktop access; never uses the live DB.
- [../verify.py](../verify.py): unchanged controller/physics/camera/animation hashes
  and exact expected feature patches, plus the current executable hashes.

The standalone `HitHudIntegration` target exercises the actual D3D9 renderer on
an isolated Xvfb display: digit order, equal glyph height, upper-right bounds at
800x600/1280x800/1920x1080, both interface scaling modes, and render-state restoration.
`RewardHudIntegration` checks the blue GBucks queue/animation, rendering bounds,
fade and D3D state restoration at the same resolutions without opening GunZ.
The updated HUD has **not** been checked in a live match, nor has a complete
two-player Duel been validated. Tests do not launch, focus, capture or change the
current game session. Close the original client and relaunch normally to install
the new executable before opening extra clients.

### XML compatibility regression

The engine's XML wrapper matches literal `xml` and `ITEM` names, not namespace-aware
names. ElementTree's default `ns0:` serialization produced valid XML that both
original loaders rejected, preventing MatchServer from starting. The overlay now
preserves the original **default namespace** and uses it for the new ring too.
Tests cover the literal serialized names and the actual Windows engine loaders;
reparsing with ElementTree alone is not sufficient. The launcher waits for the real
server-ready marker and TCP listener before opening the client, and surfaces startup
failures rather than leaving players at an unusable login screen.