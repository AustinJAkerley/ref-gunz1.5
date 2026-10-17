#include "world.hpp"
#include "map.hpp"
#include "controls.hpp"
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
    if(map().active())return map().spawn(id);
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
    p.jumpBuffer=std::max(0.f,p.jumpBuffer-dt);
    p.comboWindow=std::max(0.f,p.comboWindow-dt);
    p.stun=std::max(0.f,p.stun-dt);
    if(p.action!=Action::Idle) {
        p.actionTime+=dt;
        if(p.actionTime+1e-6f>=actionDuration(p.action)) {
            if(p.action==Action::Guard)p.guardExhausted=true;
            p.action=Action::Idle;p.actionTime=0;
        }
    }
    Vec wish=direction(in.yaw)*float(bool(in.buttons&Forward)-bool(in.buttons&Back));
    wish+=screenRight(in.yaw)*float(bool(in.buttons&Right)-bool(in.buttons&Left));
    wish=unit(wish);
    const bool locked=isAttack(p.action)||p.action==Action::Guard||p.stun>0;
    if((in.buttons&Jump)&&!locked) p.jumpBuffer=.3f;
    if(isDash(p.action)) {
        // Preserve the original dash impulse without ordinary acceleration/braking.
    } else if(locked&&p.grounded) {
        p.velocity.x=0;p.velocity.z=0;
    } else if(p.grounded) {
        p.velocity.x+=wish.x*70.f*dt;p.velocity.z+=wish.z*70.f*dt;
        const float speed=std::hypot(p.velocity.x,p.velocity.z);
        float reduced=speed;
        if(speed>runSpeed)reduced=std::max(runSpeed,speed-71.f*dt);
        if(length(wish)<.1f)reduced=std::max(0.f,reduced-30.f*dt);
        if(speed>0){p.velocity.x*=reduced/speed;p.velocity.z*=reduced/speed;}
    } else if(std::hypot(p.velocity.x,p.velocity.z)<runSpeed) {
        // Original AIR_MOVE=0.05 and acceleration=7000, scaled to metres.
        p.velocity.x+=wish.x*70.f*.05f*dt;
        p.velocity.z+=wish.z*70.f*.05f*dt;
    }
    if(p.jumpBuffer>0 && p.grounded && !locked && !isDash(p.action)) {
        p.velocity.y=9.f; p.grounded=false; p.jumpBuffer=0;
    } else if(p.jumpBuffer>0 && !locked && !isDash(p.action)) {
        Vec normal=map().active()?map().wall(p.position):Vec{};
        if(!map().active())for(const auto& b:arena()) {
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
    if((in.buttons&Dash) && !locked && p.action==Action::Idle && p.dashCooldown<=0) {
        p.action=Action::DashForward;p.dashDirection=direction(in.yaw);
        if(in.buttons&Back){p.action=Action::DashBack;p.dashDirection=direction(in.yaw)*-1.f;}
        else if(in.buttons&Right){p.action=Action::DashRight;p.dashDirection=screenRight(in.yaw);}
        else if(in.buttons&Left){p.action=Action::DashLeft;p.dashDirection=screenRight(in.yaw)*-1.f;}
        p.velocity=p.dashDirection*dashSpeed; // Original SetVelocity also replaces vertical velocity.
        p.actionTime=0;p.dashCooldown=dashDuration;
    }
    // Directly reuse the original gravity/fall-limit definitions (cm -> m).
    p.velocity.y=std::max(p.velocity.y-GRAVITY_CONSTANT*.01f*dt,-MAX_FALL_SPEED*.01f);
    p.grounded=false;
    if(map().active())map().move(p,dt);
    else for(int axis=0;axis<3;++axis) {
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
        auto original=spawn(p.id);
        original.yaw=p.yaw;original.pitch=p.pitch;original.ack=p.ack;
        original.swings=p.swings;original.hits=p.hits;original.score=p.score;
        p=original;
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
    state.targets={Target{{0,0,-7.5f}},Target{{-12,0,6}},Target{{12,0,6}},Target{{0,0,17}}};
    if(map().active()) {
        auto p=spawn(1);
        for(std::size_t i=0;i<state.targets.size();++i){
            auto pos=p.position+direction(p.yaw)*(2.5f+float(i)*3.f);
            state.targets[i].position=pos;state.targets[i].position.y=p.position.y;
        }
    }
}
Player* World::find(std::uint32_t id) {
    for(auto& p:state.players) if(p.id==id) return &p;
    return nullptr;
}
void World::attack(Player& p) {
    const auto forward=direction(p.yaw);
    const auto sword=p.position+forward+Vec{0,height*.5f,0};
    auto inReach=[&](Vec target) {
        // Original player melee test: forward-offset sword vs vertical body segment,
        // 60-degree half cone, then world occlusion. Not an 80-metre firearm ray.
        Vec nearest{target.x,std::clamp(sword.y,target.y,target.y+height),target.z};
        if(length(sword-nearest)>katanaRange)return false;
        if(dot(forward,unit(target-(p.position-forward*.5f)))<.5f)return false;
        const auto origin=p.position+Vec{0,height*.5f,0};
        const auto delta=target+Vec{0,height*.5f,0}-origin;
        float distance=length(delta),clear=distance;
        if(map().active())clear=map().ray(origin,unit(delta),distance);
        else for(const auto& box:arena())clear=rayBox(origin,unit(delta),box,clear);
        return clear>=distance-.02f;
    };
    for(auto& t:state.targets)if(t.hp>0&&inReach(t.position)) {
        t.hp=std::max(0,t.hp-katanaDamage);++p.hits;
        if(t.hp==0){t.respawn=3;++p.score;}
    }
    for(auto& enemy:state.players)if(enemy.id!=p.id&&inReach(enemy.position)) {
        if(enemy.action==Action::Guard&&dot(direction(enemy.yaw),forward)<0)continue;
        enemy.hp-=katanaDamage;++p.hits;
        if(p.action==Action::Uppercut){enemy.velocity.y=12.f;enemy.grounded=false;enemy.stun=.5f;enemy.action=Action::Idle;}
        if(enemy.hp<=0){
            ++p.score;auto fresh=spawn(enemy.id);
            fresh.yaw=enemy.yaw;fresh.pitch=enemy.pitch;fresh.ack=enemy.ack;
            fresh.swings=enemy.swings;fresh.hits=enemy.hits;fresh.score=enemy.score;
            fresh.stun=.3f;enemy=fresh;respawned.push_back(enemy.id);
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
        const bool guard=(in.buttons&Guard)||((in.buttons&Primary)&&(in.buttons&Secondary));
        if(!guard)p.guardExhausted=false;
        if(p.stun>0)continue;
        if(guard&&!p.guardExhausted){
            if(p.action!=Action::Guard){p.action=Action::Guard;p.actionTime=0;p.combo=0;p.velocity.x=0;p.velocity.z=0;}
        } else {
            if(p.action==Action::Guard){p.action=Action::Idle;p.actionTime=0;}
            if(!guard&&(p.action==Action::Idle||isDash(p.action))){
                Action next=Action::Idle;
                if((in.buttons&Secondary)&&p.grounded)next=Action::Uppercut;
                else if(in.buttons&Primary){
                    if(!p.grounded)next=Action::AirSlash;
                    else {p.combo=p.comboWindow>0?p.combo%4+1:1;next=Action(std::uint32_t(Action::Attack1)+p.combo-1);}
                }
                if(next!=Action::Idle){
                    p.action=next;p.actionTime=0;p.hitApplied=false;++p.swings;
                    p.comboWindow=actionDuration(next)+.25f;p.dashCooldown=0;
                    if(p.grounded){p.velocity.x=0;p.velocity.z=0;}
                }
            }
        }
        if(isAttack(p.action)&&!p.hitApplied&&p.actionTime+1e-6f>=hitTime(p.action)){
            p.hitApplied=true;attack(p);
        }
    }
}
} // namespace gz