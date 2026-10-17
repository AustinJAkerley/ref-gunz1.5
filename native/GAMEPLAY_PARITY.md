# Katana behavior reference and limits

This is a source-informed native katana practice mode, **not a claim of full GunZ
1.5 behavior parity**. The native server remains authoritative and uses its own
protocol; the original game's animation state machine, peer networking, collision
solver, equipment system and complete cancel chains are not running here.

## Corrected mismatches

- Removed the placeholder firearm path. A visible katana no longer performs an
  80-metre hitscan shot, draws a tracer or displays a muzzle flash.
- LMB starts ground combo stages 1–4, or an air slash when airborne. Holding LMB
  continues the combo after each stage finishes; exact historical input queues,
  charge/massive behavior and recovery-return clips remain unported.
- RMB requests a grounded uppercut; Shift guards. Holding both attack buttons
  also guards. Guard expires after two seconds until released; front-facing guard
  blocks the implemented melee attack. Uppercut launches players, not static dummies.
- Double-tap W/A/S/D within 200 ms to dash in that direction. Holding a key does
  not repeatedly dash. Shift is **not** dash anymore.
- Katana animations now come from male `motion_type=1` (`man_knife_*`), not the
  great-sword `motion_type=12` clips used by the first visual prototype.
- The server replicates action and elapsed action time. The renderer selects the
  matching attack/dash/guard/uppercut clip, clamps one-shots, and keeps the blade
  attached to the same animated hand transform. It no longer uses a client-only
  right-click flash or loops a jump attack as the ground attack.

## Source-derived values

- [Original dash input](../Gunz/ZGameInput.cpp): directional press/release/press,
  0.2-second sequence timeout.
- [Original tumble and melee handlers](../Gunz/ZMyCharacter.cpp): melee dash
  velocity 1000 original units/s; airborne tumble allowed; first slash damage
  event delayed 0.1 s; uppercut delayed 0.18 s. Slash/guard intentionally interrupt
  tumble as in the source, rather than forcing a non-cancellable dash.
- [Original velocity and animation speed](../Gunz/ZCharacter.cpp): skip normal
  horizontal braking while tumbling; base animation speed 4.8 ticks/ms. Ordinary
  acceleration, stopping and over-speed correction use 7000, 3000 and 7100 original
  units/s² respectively.
- The four pinned katana dash ANI files each end at **1600 animation ticks**.
  At 4800 ticks/s this is **1/3 s**. At this port's 100 units/metre scale, velocity
  is **10 m/s**, giving **3.333 m during an uninterrupted, unobstructed dash**.
  Subsequent braking adds travel; collision, slash/guard cancellation and airborne
  momentum can change the total travel. This is not a hard teleport distance.
- [Original katana item 2](../Gunz/XML/zitem.xml): mesh `katana01`, damage **15**,
  range **220 units / 2.2 m**, delay **359 ms**. Original attack timing subtracts
  299 ms from item delay and adds the result to the chosen clip length; this preset
  therefore adds 60 ms. The loaded ground clips last 0.3, 0.3667, 0.5 and 1 s before
  that adjustment. Other original weapons/items can have different timing.
- [Original melee range logic](../Gunz/ZGame.cpp): sword-origin one metre forward
  at half character height, distance to the victim's vertical segment, 60-degree
  forward half-cone and wall occlusion. This is not a tiny crosshair ray. One swing
  can hit several nearby opponents, once per victim.

## Remaining differences

Original attack-return blends, precise guard transitions, massive charging,
stun/knockback tuning, wall-running/hanging, complete K-style cancellation,
weapon switching, guns, sound and camera/animation blending are still missing or
simplified. Uppercut launch velocity is currently native tuning, not validated
against the original skill implementation. Ground lock and air-steering rules are
not claimed to reproduce every original state. Character collision approximates
a capsule against original collision triangles, not the original cylinder/BSP
solver. No latency compensation or prediction is implemented.

## Regression coverage

Core tests verify the dash duration/displacement at 60 and 120 Hz in all four
directions, no braking during dash, braking afterward, 200 ms double taps, mouse
handedness, delayed first slash, one hit per swing, no distant sword damage,
off-crosshair melee arc, rear exclusion, wall occlusion, guard, uppercut, combo
damage, action cancellation/reset and serialized action phase. Asset tests parse
the old axis-angle ANI variants and verify all four dash files end at 1600 ticks.
The real-window smoke observes server-confirmed slash hits, dash, guard, uppercut
and jump while rendering the corresponding katana clips in Mansion.