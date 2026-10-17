#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>

namespace competitive {
// Presentation only. Never computes Elo rewards, changes a balance, or observes
// local kills. The caller must authenticate the server notice before adding it.
constexpr std::uint64_t gbucksRewardLifetime = 1000;
struct GBucksReward {
    int amount;
    bool completion;
    std::uint64_t at;
};
class GBucksRewardQueue {
    std::deque<GBucksReward> notices;
public:
    static constexpr std::size_t capacity = 16;
    static bool valid(int amount, bool completion) {
        return completion ? amount > 0 : amount >= 10 && amount <= 20;
    }
    void clear() { notices.clear(); }
    const GBucksReward* current(std::uint64_t now) {
        while (!notices.empty() && now >= notices.front().at &&
               now - notices.front().at >= gbucksRewardLifetime)
            notices.pop_front();
        return notices.empty() || now < notices.front().at ? nullptr : &notices.front();
    }
    bool visible(std::uint64_t now) { return current(now) != nullptr; }
    bool add(int amount, bool completion, std::uint64_t now) {
        if (!valid(amount, completion)) return false;
        current(now);
        // Overflow drops presentation only, never merges distinct server awards.
        if (notices.size() >= capacity) return false;
        const auto at = notices.empty() ? now : notices.back().at + gbucksRewardLifetime;
        if (at < now || at > UINT64_MAX - gbucksRewardLifetime) return false;
        notices.push_back({amount, completion, at});
        return true;
    }
};
}

// client.hpp owns this one cache accessor, just like CompetitiveDamage().
// Its definition must return a function-local static GBucksRewardQueue.
competitive::GBucksRewardQueue& CompetitiveGBucksPopup();
inline bool AddCompetitiveGBucksReward(int amount, bool completion, std::uint64_t now) {
    return CompetitiveGBucksPopup().add(amount, completion, now);
}
inline const competitive::GBucksReward* CurrentCompetitiveGBucksReward(std::uint64_t now) {
    return CompetitiveGBucksPopup().current(now);
}
inline void ClearCompetitiveGBucksRewards() { CompetitiveGBucksPopup().clear(); }