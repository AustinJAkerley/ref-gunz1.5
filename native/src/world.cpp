#include "world.hpp"
#include "../../Gunz/ZGameConst.h"
#include <algorithm>
#include <limits>

namespace gz {
const std::vector<Box>& arena() {
    static const std::vector<Box> boxes={
        {{-18,-1,-22},{18,0,22}},
        {{-19,0,-23},{-18,6,23}},{{18,0,-23},{19,6,23}},
        {{-18,0,-23},{18,6,-22}},{{-18,0,22},{18,6,23}},
        {{-11,0,-3},{-8,3,3}},{{8,0,-3},{11,3,3}},
        {{-3,0,4},{3,1,7}},{{-2,0,7},{2,2,9}},
        {{-15,0,10},{-12,2,14}},{{12,0,10},{15,2,14}},
        {{-7,0,-15},{-5,4,-13}},{{5,0,-15},{7,4,-13}}
    };
    return boxes;
}
Player spawn(std::uint32_t id) {
    Player p; p.id=id; p.position={static_cast<float>((id-1)%4)*2,0,-10}; return p;
}
static bool overlaps(Vec p,const Box& b) {
    return p.x+radius>b.lo.x && p.x-radius<b.hi.x &&
        p.y+height>b.lo.y+.0001f && p.y<b.hi.y-.0001f &&
        p.z+radius>b.lo.z && p.z-radius<b.hi.z;
}
void move(Player& p,const Input& in,float dt) {
    if(!std::isfinite(dt)||dt<=0||dt>.05f) return;
    p.yaw=in.yaw; p.pitch=in.pitch; p.ack=in.sequence;
    p.dashCooldown=std::max(0.f,p.dashCooldown-dt);
    p.fireCooldown=std::max(0.f,p.fireCooldown-dt);
    p.slashCooldown=std::max(0.f,p.slashCooldown-dt);
    p.jumpBuffer=std::max(0.f,p.jumpBuffer-dt);
    Vec wish=direction(in.yaw)*float(bool(in.buttons&Forward)-bool(in.buttons&Back));
    wish+=direction(in.yaw+1.570796327f)*float(bool(in.buttons&Right)-bool(in.buttons&Left));
    wish=unit(wish);
    if(in.buttons&Jump) p.jumpBuffer=.3f; // Original jump-buffer duration.
    if(p.grounded) {
        const float blend=std::min(1.f,18.f*dt);
        p.velocity.x+=(wish.x*runSpeed-p.velocity.x)*blend;
        p.velocity.z+=(wish.z*runSpeed-p.velocity.z)*blend;
    } else if(std::hypot(p.velocity.x,p.velocity.z)<runSpeed) {
        // Original AIR_MOVE=0.05 and acceleration=7000, scaled to metres.
        p.velocity.x+=wish.x*70.f*.05f*dt;
        p.velocity.z+=wish.z*70.f*.05f*dt;
    }
    if(p.jumpBuffer>0 && p.grounded) {
        p.velocity.y=9.f; p.grounded=false; p.jumpBuffer=0;
    } else if(p.jumpBuffer>0) {
        Vec normal{};
        for(const auto& b:arena()) {
            if(p.position.y+height<=b.lo.y || p.position.y>=b.hi.y) continue;
            if(p.position.z>b.lo.z-radius && p.position.z<b.hi.z+radius) {
                if(std::abs(p.position.x-(b.lo.x-radius))<.12f) normal={-1,0,0};
                if(std::abs(p.position.x-(b.hi.x+radius))<.12f) normal={1,0,0};
            }
            if(p.position.x>b.lo.x-radius && p.position.x<b.hi.x+radius) {
                if(std::abs(p.position.z-(b.lo.z-radius))<.12f) normal={0,0,-1};
                if(std::abs(p.position.z-(b.hi.z+radius))<.12f) normal={0,0,1};
            }
        }
        if(length(normal)>0) {
            p.velocity=(p.velocity-normal*dot(p.velocity,normal))*1.1f+normal*3.f;
            p.velocity.y=14.f; p.jumpBuffer=0;
        }
    }
    if((in.buttons&Dash) && p.dashCooldown<=0) {
        if(length(wish)<.1f) wish=direction(in.yaw);
        p.velocity.x=wish.x*18.f; p.velocity.z=wish.z*18.f;
        p.dashCooldown=.65f;
    }
    // Directly reuse the original gravity/fall-limit definitions (cm -> m).
    p.velocity.y=std::max(p.velocity.y-GRAVITY_CONSTANT*.01f*dt,-MAX_FALL_SPEED*.01f);
    p.grounded=false;
    for(int axis=0;axis<3;++axis) {
        float* coordinate=axis==0?&p.position.x:axis==1?&p.position.z:&p.position.y;
        float* speed=axis==0?&p.velocity.x:axis==1?&p.velocity.z:&p.velocity.y;
        const float delta=*speed*dt; *coordinate+=delta;
        for(const auto& b:arena()) if(overlaps(p.position,b)) {
            if(axis==0) *coordinate=delta>0?b.lo.x-radius:b.hi.x+radius;
            else if(axis==1) *coordinate=delta>0?b.lo.z-radius:b.hi.z+radius;
            else {
                *coordinate=delta>0?b.lo.y-height:b.hi.y;
                if(delta<=0) p.grounded=true;
            }
            *speed=0;
        }
    }
    if(p.position.y<-15 || (in.buttons&Reset)) {
        auto original=spawn(p.id); p.position=original.position;p.velocity={};p.hp=100;
    }
}
float rayBox(Vec origin,Vec ray,const Box& b,float limit) {
    float lo=0,hi=limit;
    const float o[]={origin.x,origin.y,origin.z},d[]={ray.x,ray.y,ray.z};
    const float mn[]={b.lo.x,b.lo.y,b.lo.z},mx[]={b.hi.x,b.hi.y,b.hi.z};
    for(int i=0;i<3;++i) {
        if(std::abs(d[i])<1e-6f) { if(o[i]<mn[i]||o[i]>mx[i]) return limit; }
        else {
            float a=(mn[i]-o[i])/d[i],c=(mx[i]-o[i])/d[i];
            if(a>c) std::swap(a,c);
            lo=std::max(lo,a);hi=std::min(hi,c);
            if(lo>hi) return limit;
        }
    }
    return lo;
}
World::World() {
    state.targets={Target{{0,0,-2}},Target{{-12,0,6}},Target{{12,0,6}},Target{{0,0,17}}};
}
Player* World::find(std::uint32_t id) {
    for(auto& p:state.players) if(p.id==id) return &p;
    return nullptr;
}
void World::attack(Player& p,bool melee) {
    const auto eye=p.position+Vec{0,1.45f,0},dir=direction(p.yaw,p.pitch);
    float closest=melee?2.8f:80.f;
    for(const auto& box:arena()) closest=rayBox(eye,dir,box,closest);
    int target=-1; Player* enemy=nullptr;
    for(std::size_t i=0;i<state.targets.size();++i) {
        const auto& t=state.targets[i]; if(t.hp<=0) continue;
        float hit=rayBox(eye,dir,{t.position+Vec{-.45f,0,-.45f},t.position+Vec{.45f,2,.45f}},closest);
        if(hit<closest) {closest=hit;target=int(i);}
    }
    for(auto& other:state.players) if(other.id!=p.id) {
        float hit=rayBox(eye,dir,{other.position+Vec{-radius,0,-radius},other.position+Vec{radius,height,radius}},closest);
        if(hit<closest) {closest=hit;enemy=&other;target=-1;}
    }
    ++p.shots;p.shotEnd=eye+dir*closest;
    const int damage=melee?50:25;
    if(target>=0) {
        auto& t=state.targets[std::size_t(target)]; t.hp=std::max(0,t.hp-damage);++p.hits;
        if(t.hp==0) {t.respawn=3; ++p.score;}
    }
    if(enemy) {
        enemy->hp-=damage;++p.hits;
        if(enemy->hp<=0) {
            ++p.score;enemy->position=spawn(enemy->id).position;enemy->velocity={};enemy->hp=100;
            enemy->fireCooldown=.3f;enemy->slashCooldown=.3f;respawned.push_back(enemy->id);
        }
    }
}
void World::step(const std::vector<std::pair<std::uint32_t,Input>>& inputs) {
    ++state.tick;
    respawned.clear();
    for(auto& t:state.targets) if(t.hp==0) {
        t.respawn-=tick;if(t.respawn<=0) {t.hp=100;t.respawn=0;}
    }
    for(auto& p:state.players) {
        if(std::find(respawned.begin(),respawned.end(),p.id)!=respawned.end()) continue;
        Input in;in.yaw=p.yaw;in.pitch=p.pitch;
        for(const auto& pair:inputs) if(pair.first==p.id) {in=pair.second;break;}
        move(p,in);
        if((in.buttons&Fire) && p.fireCooldown<=0) {attack(p,false);p.fireCooldown=.18f;}
        if((in.buttons&Slash) && p.slashCooldown<=0) {attack(p,true);p.slashCooldown=.45f;}
    }
}
} // namespace gz