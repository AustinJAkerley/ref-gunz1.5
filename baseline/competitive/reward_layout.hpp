#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>
#include "reward.hpp"
#include "competitive_reward_art.hpp"

namespace competitive {
static_assert(reward_art::durationMS == gbucksRewardLifetime, "Queue and original animation lifetime must agree");
struct RewardQuad { int glyph; float left, top, right, bottom; };
inline float rewardOpacity(std::uint64_t elapsed) {
    if (elapsed >= gbucksRewardLifetime) return 0;
    const float frame = float(elapsed) * reward_art::ticksPerMS;
    const auto& keys = reward_art::opacityKeys;
    for (std::size_t i = 1; i < sizeof(keys) / sizeof(keys[0]); ++i) {
        if (frame < keys[i].frame) {
            const auto& a = keys[i - 1]; const auto& b = keys[i];
            return a.value + (b.value - a.value) * (frame - a.frame) / (b.frame - a.frame);
        }
    }
    return 0;
}
inline float rewardScale(std::uint64_t elapsed) {
    // RAnimationNode::GetTMValue uses stepped keys, not interpolated matrices.
    const float frame = float((std::min)(elapsed, gbucksRewardLifetime)) * reward_art::ticksPerMS;
    float scale = 1;
    for (const auto& key : reward_art::scaleKeys) {
        if (key.frame > frame) break;
        scale = key.value;
    }
    return scale;
}
inline std::vector<RewardQuad> rewardLayout(int amount, bool completion, std::uint64_t elapsed) {
    if (!GBucksRewardQueue::valid(amount, completion) || elapsed >= gbucksRewardLifetime) return {};
    std::vector<int> digits;
    do { digits.push_back(amount % 10); amount /= 10; } while (amount);
    std::reverse(digits.begin(), digits.end());
    std::vector<RewardQuad> result;
    float x = reward_art::left;
    auto append = [&](int id, float scale) {
        const auto& g = reward_art::glyphs[id];
        const float center = x - g.left;
        result.push_back({id, center + g.left * scale, reward_art::baseline + g.top * scale,
                         center + g.right * scale, reward_art::baseline + g.bottom * scale});
        x += g.right - g.left;
    };
    // Same top-left reward region and original glyph sizes; the longer label
    // precedes the plus rather than leaving the old EXP suffix in the texture.
    append(reward_art::labelGlyph, 1); x += 8;
    append(reward_art::plusGlyph, 1);
    const float scale = rewardScale(elapsed);
    // Preserve original fixed 30-world-unit numeric advance and per-digit pop.
    const float firstCenter = x + reward_art::numberGap;
    for (std::size_t i = 0; i < digits.size(); ++i) {
        x = firstCenter + float(i) * 30 + reward_art::glyphs[digits[i]].left;
        append(digits[i], scale);
    }
    return result;
}
}