#pragma once
#include <cstdint>
constexpr int MC_MATCH_DUEL_RATING=49001;
constexpr int MC_MATCH_DAMAGE_CONFIRMATION=49002;
constexpr int MC_MATCH_GBUCKS_REWARD=49003;
struct CompetitiveRatingWire {
    std::uint32_t uidHigh,uidLow;
    std::int32_t elo,rank,position,wins,losses;
};
static_assert(sizeof(CompetitiveRatingWire)==28,"Rating wire size");