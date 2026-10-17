#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>
#include "competitive_hit_art.hpp"

namespace competitive {
struct HitQuad {int glyph;float left,top,right,bottom;};
inline std::vector<HitQuad> hitLayout(int amount){
    if(amount<=0||amount>10000)return {};
    std::vector<int> digits;
    do{digits.push_back(amount%10);amount/=10;}while(amount);
    std::reverse(digits.begin(),digits.end());
    std::vector<HitQuad> result;
    float x=hit_art::left;
    auto append=[&](int id){
        const auto& g=hit_art::glyphs[id];float w=g.width*hit_art::pixelX;
        result.push_back({id,x,hit_art::top,x+w,hit_art::top-g.height*hit_art::pixelY});x+=w;
    };
    append(0);x+=8*hit_art::pixelX;
    for(int digit:digits){append(digit+1);x+=3*hit_art::pixelX;}
    return result;
}
inline float hitOpacity(std::uint64_t elapsed){
    if(elapsed>=650)return 0;
    return std::min(1.f,std::min(float(elapsed)/33.f,float(650-elapsed)/100.f));
}
}