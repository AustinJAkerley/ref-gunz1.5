# GBucks reward integration contract

These files only own presentation. The main integration owns the command,
cache accessor, source-patch composition and build target. No reward is inferred
from local damage/deaths, XP, levels, or a balance delta.

## Client

Include `reward.hpp` in `client.hpp`. Define this cache accessor there (not in
another translation unit's private/static namespace):

```cpp
inline competitive::GBucksRewardQueue& CompetitiveGBucksPopup() {
    static competitive::GBucksRewardQueue value;
    return value;
}
```

For `MC_MATCH_GBUCKS_REWARD` (49003), `OnCommand` must verify the sender equals
`GetServerUID()` **before** decoding. Decode exactly two `MPT_INT` parameters,
`amount` then `completion`; reject completion values other than 0 or 1. Then
call `AddCompetitiveGBucksReward(amount, completion == 1, GetGlobalTimeMS())`.
The queue validates kill rewards 10–20 inclusive, completion rewards positive.
Amounts come from the server's committed reward, never client Elo calculation.
Keep the command server-only (not a peer/tunnel command). The queue is not a
transport deduplicator; the command has no event ID. Server sends each award once.

Call `ClearCompetitiveGBucksRewards()` from `CompetitiveClear()` and when a new
`ZGame::Create` begins (alongside the existing damage clear). Screen-effect
destruction also clears and releases its texture. Don't clear at round start:
a notice arriving between rounds still deserves its animation. Replays and
observer targets never draw rewards. Hidden/paused frames cannot extend expiry.

The queue holds at most 16 notices, one second each, FIFO, with immutable
scheduled timestamps. Overflow drops only the extra popup, not currency.
`CurrentCompetitiveGBucksReward(now)` returns a pointer valid until the queue is
modified; consume it immediately. Both completion and kill HUD say GBucks +N.

## Source composition

Add `reward_patch.FILES` to the union of stage patch files and compose each file
in this order: existing `patch_source` → `economy_patch` → `progression_patch` →
`presentation_patch` → `reward_patch`. Apply only a module that owns the path.
Use the same composition for source verification. The reward patch fails closed
without the exact suppressed `AddExpEffect` body and existing HIT anchors.
It never repurposes `AddExpEffect` or touches its XP parameter.

## CMake (main-owned)

Next to existing HIT atlas generation:

```cmake
execute_process(COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/competitive/reward_art.py
    --data /work/reference-data --header ${CMAKE_BINARY_DIR}/competitive_reward_art.hpp
    COMMAND_ERROR_IS_FATAL ANY)
add_executable(RewardHudIntegration competitive/reward_hud_test.cpp)
target_compile_options(RewardHudIntegration PRIVATE /EHsc /FI/baseline/compat/platform_headers.h)
target_link_libraries(RewardHudIntegration PRIVATE RealSpace2 d3d9 gdiplus ole32)
```

Existing global include paths already cover `competitive` and `${CMAKE_BINARY_DIR}`.
Pillow and Liberation Serif Bold Italic are the same build-only dependencies as
HIT art. No extra runtime files are installed: the generated PNG is embedded.

The test also compiles as a native C++14 program with `competitive` plus the
temporary generated-header directory in the include path. On Windows it adds
actual GDI+/D3D9 rendering/readback at 800×600, 1280×800 and 1920×1080, both
InterfaceFix modes, kill and completion amounts, fade/expiry, and hostile prior
render-state restoration. Run that only on isolated Xvfb/compiler Wine, never a
game/runtime Wine prefix. No real-target build/configure is needed for native
queue/layout tests or Python art/patch tests.

The original number/plus pixels and ELU dimensions are preserved. The original
one-second animation keys drive opacity and stepped digit growth. The longer
generated silver/blue GBucks label goes before the plus in the same upper-left
reward region, rather than squeezing six letters into the old EXP suffix.