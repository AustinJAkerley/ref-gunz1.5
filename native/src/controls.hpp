#pragma once
#include "world.hpp"
#include <algorithm>

namespace gz {
// raylib's Y-up, right-handed camera uses cross(forward, up) for screen-right.
// With forward=(sin(yaw), 0, cos(yaw)), positive yaw turns screen-left.
inline Vec screenRight(float yaw) {
    return {-std::cos(yaw),0,std::sin(yaw)};
}
inline void mouseLook(float& yaw,float& pitch,float dx,float dy) {
    constexpr float sensitivity=.0025f,turn=6.283185307f;
    yaw=std::remainder(yaw-dx*sensitivity,turn);
    // Mouse coordinates increase downwards; positive pitch looks upwards.
    pitch=std::clamp(pitch-dy*sensitivity,-1.4f,1.4f);
}
class DashTaps {
    std::array<double,4> last{{-10,-10,-10,-10}};
    std::uint32_t held=0;
public:
    std::uint32_t update(std::uint32_t buttons,double seconds) {
        constexpr std::array<std::uint32_t,4> keys{{Forward,Back,Right,Left}};
        std::uint32_t dash=0;
        for(std::size_t i=0;i<keys.size();++i)if((buttons&keys[i])&&!(held&keys[i])) {
            if(seconds-last[i]<=.2){dash=keys[i];last[i]=-10;}
            else last[i]=seconds;
        }
        held=buttons;return dash;
    }
    void reset(){last.fill(-10);held=0;}
};
}