#pragma once
#include <algorithm>
namespace competitive {
// Abstract indices 0=melee, 1=primary, 2=secondary. Custom slots never enter.
inline int cycleMainWeapon(int selected,bool previous,const bool (&owned)[3]) {
    int start=selected>=0&&selected<3?selected:(previous?0:2);
    for(int step=1;step<=3;++step){int next=(start+(previous?-step:step)+6)%3;if(owned[next])return next;}
    return -1;
}
struct MeleeFeedback {
    int total=0;
    void add(float damage,bool local,bool replay,bool serverBased,bool alive,bool visible,bool invincible) {
        if(!local||replay||serverBased||!alive||!visible||invincible||!(damage>0))return;
        total=std::min(10000,total+int(std::min(10000.f,damage)));
    }
};
}