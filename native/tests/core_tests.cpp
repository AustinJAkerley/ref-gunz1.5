#include "protocol.hpp"
#include "controls.hpp"
#include "MCRC32.h"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <random>

namespace {int checks=0;void check(bool ok,const char* text) {++checks;if(!ok){std::cerr<<"FAIL "<<text<<'\n';std::exit(1);}}}
int main() {
    check(sizeof(MCRC32::crc_t)==4,"CRC fixed-width on Linux and Windows");
    const char* text="123456789";
    check(MCRC32::BuildCRC32(reinterpret_cast<const BYTE*>(text),9)==0xcbf43926u,"original CRC standard vector");
    check(MCRC32::BuildCRC32(nullptr,0)==0,"empty CRC");
    for(float heading:{0.f,1.570796327f,-1.570796327f,3.141592654f}) {
        const auto forward=gz::direction(heading);
        // Independently derive the renderer's right vector: cross(forward, Y-up).
        const gz::Vec right{-forward.z,0,forward.x};
        check(gz::dot(gz::screenRight(heading),right)>.999f,"strafe matches camera handedness");
        for(auto button:{gz::Left,gz::Right}) {
            auto player=gz::spawn(1);const auto start=player.position;
            gz::move(player,{1,std::uint32_t(button),heading,0});
            const auto displacement=gz::dot(player.position-start,right);
            check(button==gz::Right?displacement>0:displacement<0,"A/D move screen-left/right at every heading");
        }
        float yaw=heading,pitch=0;
        gz::mouseLook(yaw,pitch,10,0);
        check(gz::dot(gz::direction(yaw)-forward,right)>0,"mouse right looks right");
        yaw=heading;gz::mouseLook(yaw,pitch,-10,0);
        check(gz::dot(gz::direction(yaw)-forward,right)<0,"mouse left looks left");
        yaw=heading;pitch=0;gz::mouseLook(yaw,pitch,0,-10);
        check(gz::direction(yaw,pitch).y>0,"mouse up looks up");
        pitch=0;gz::mouseLook(yaw,pitch,0,10);
        check(gz::direction(yaw,pitch).y<0,"mouse down looks down");
    }
    auto p=gz::spawn(1);gz::Input in;in.buttons=gz::Forward;
    for(int i=0;i<60;++i) gz::move(p,in);
    check(p.position.z>-5&&p.position.z<-3,"run speed approaches original 6.3 metres/sec");
    check(p.grounded&&std::abs(p.position.y)<.001,"floor collision");
    in.buttons=gz::Jump;gz::move(p,in);check(p.velocity.y>8&&p.position.y>0,"jump impulse");
    in.buttons=0;float apex=0;for(int i=0;i<120;++i) {gz::move(p,in);apex=std::max(apex,p.position.y);}
    check(apex>1.4&&apex<1.7,"original jump/gravity scaling");check(p.grounded,"landing");
    p=gz::spawn(1);in.buttons=gz::Dash|gz::Forward;gz::move(p,in);
    check(std::abs(p.velocity.z-gz::dashSpeed)<.001f&&p.action==gz::Action::DashForward,"original katana dash impulse");
    for(int i=0;i<500;++i) gz::move(p,in);
    check(p.position.z<=22-gz::radius+.001,"solid boundary cannot be crossed");
    p=gz::spawn(1);p.position={17.65f,2,0};p.grounded=false;in.buttons=gz::Jump;gz::move(p,in);
    check(p.velocity.y>13&&p.velocity.x<0,"wall rebound");
    gz::Box box{{-1,0,3},{1,2,4}};
    check(gz::rayBox({0,1,0},{0,0,1},box,10)==3,"ray hit");
    check(gz::rayBox({2,1,0},{0,0,1},box,10)==10,"parallel ray miss");
    for(auto button:{gz::Forward,gz::Back,gz::Right,gz::Left})for(float dt:{gz::tick,1.f/120}) {
        auto dasher=gz::spawn(1);const auto start=dasher.position;
        gz::Input dash{1,std::uint32_t(gz::Dash|button),0,0};
        int ticks=int(std::round(gz::dashDuration/dt));
        for(int i=0;i<ticks;++i){gz::move(dasher,dash,dt);dash.buttons=0;}
        check(std::abs(std::hypot(dasher.position.x-start.x,dasher.position.z-start.z)-10.f/3.f)<.002f,
              "dash covers 3.333 m before animation ends at either tick rate");
        check(std::abs(std::hypot(dasher.velocity.x,dasher.velocity.z)-10.f)<.001f,"no ground braking during dash");
        gz::move(dasher,dash,dt);check(dasher.action==gz::Action::Idle,"dash exits at clip end");
        check(std::hypot(dasher.velocity.x,dasher.velocity.z)<10.f,"braking resumes after dash");
    }
    gz::DashTaps taps;
    check(taps.update(gz::Forward,0)==0,"first press is not a dash");
    check(taps.update(gz::Forward,.03)==0,"holding key is not double tap");
    taps.update(0,.05);check(taps.update(gz::Forward,.19)==gz::Forward,"200ms double tap");
    taps.reset();taps.update(gz::Right,0);taps.update(0,.1);
    check(taps.update(gz::Right,.21)==0,"late double tap rejected");
    gz::World world;world.state.players.push_back(gz::spawn(1));in={1,gz::Primary,0,0};
    world.step({{1,in}});check(world.state.targets[0].hp==100,"first slash has wind-up");
    for(int i=0;i<6;++i)world.step({{1,in}});
    check(world.state.targets[0].hp==85&&world.find(1)->swings==1,"first hit at 100ms with original 15 damage");
    for(int i=0;i<10;++i)world.step({{1,in}});
    check(world.state.targets[0].hp==85,"one hit per swing, not continuous hitscan");
    for(int i=0;i<600&&world.find(1)->score==0;++i) world.step({{1,in}});
    check(world.find(1)->hits==7&&world.find(1)->score==1,"katana target damage and score");
    check(world.state.targets[0].hp==0,"target destroyed");
    for(int i=0;i<190;++i) world.step({});
    check(world.state.targets[0].hp==100,"target respawn");
    gz::World distant;distant.state.players.push_back(gz::spawn(1));distant.state.targets[0].position={0,0,-2};
    for(int i=0;i<120;++i)distant.step({{1,in}});
    check(distant.find(1)->swings>0&&distant.find(1)->hits==0,"katana cannot shoot distant targets");
    gz::World cone;cone.state.players.push_back(gz::spawn(1));
    cone.state.targets[0].position={1,0,-8};cone.state.targets[1].position={0,0,-12};
    for(int i=0;i<7;++i)cone.step({{1,in}});
    check(cone.state.targets[0].hp==85&&cone.state.targets[1].hp==100,"sword arc hits off-axis in front but not behind");
    // A solid pillar must prevent damage through cover.
    gz::World cover;auto shooter=gz::spawn(1);shooter.position={-9,0,-10};cover.state.players.push_back(shooter);
    cover.state.players[0].position={-9,0,-4};cover.state.targets[0].position={-9,0,-1.5f};
    for(int i=0;i<60;++i) cover.step({{1,in}});
    check(cover.state.targets[0].hp==100,"server occlusion");
    gz::World duel;auto a=gz::spawn(1),b=gz::spawn(2);
    a.position={3,0,-12};b.position={3,0,-9.5f};b.hp=15;
    duel.state.players={a,b};
    for(int i=0;i<6;++i)duel.step({{1,{1,gz::Primary,0,0}}});
    duel.step({{1,{1,gz::Primary,0,0}},{2,{1,gz::Primary,3.14159f,0}}});
    check(duel.find(1)->score==1&&duel.find(2)->hp==100,"player kill and respawn");
    check(duel.find(2)->swings==0,"no attack from stale input during death tick");
    gz::World guarded;a=gz::spawn(1);b=gz::spawn(2);b.position={0,0,-7.5f};b.yaw=3.1415926f;
    guarded.state.players={a,b};
    for(int i=0;i<12;++i)guarded.step({{1,in},{2,{1,gz::Guard,3.1415926f,0}}});
    check(guarded.find(2)->hp==100,"front-facing guard blocks katana");
    gz::World cancel;cancel.state.players.push_back(gz::spawn(1));
    cancel.step({{1,{1,gz::Dash|gz::Forward,0,0}}});
    check(gz::isDash(cancel.find(1)->action),"dash action starts");
    cancel.step({{1,{2,gz::Primary,0,0}}});
    check(cancel.find(1)->action==gz::Action::Attack1,"slash intentionally cancels tumble like original OnShotMelee");
    cancel.step({{1,{3,gz::Guard,0,0}}});
    check(cancel.find(1)->action==gz::Action::Guard,"guard cancels attack");
    for(int i=0;i<130;++i)cancel.step({{1,{4,gz::Guard,0,0}}});
    check(cancel.find(1)->guardExhausted&&cancel.find(1)->action==gz::Action::Idle,"guard expires after two seconds");
    cancel.step({{1,{5,gz::Reset|gz::Guard,0,0}}});
    check(cancel.find(1)->action==gz::Action::Guard&&!cancel.find(1)->guardExhausted,"reset clears stale action flags");
    gz::World upper;upper.state.players={a,b};
    for(int i=0;i<11;++i)upper.step({{1,{1,gz::Secondary,0,0}}});
    check(upper.find(2)->hp==100,"uppercut wind-up before 180ms");
    upper.step({{1,{1,gz::Secondary,0,0}}});
    check(upper.find(2)->hp==85&&upper.find(2)->velocity.y>10,"uppercut damage and launch after wind-up");
    check(gz::newer(0,0xffffffffu)&&!gz::newer(0xffffffffu,0)&&!gz::newer(7,7),"sequence wrap ordering");
    gz::Message out{};auto bytes=gz::encodeSnapshot(world.state);
    check(gz::decode(bytes.data(),bytes.size(),out),"snapshot roundtrip");
        check(out.snapshot.players.size()==1&&out.snapshot.players[0].hits==7,"snapshot fields");
        auto actionBytes=gz::encodeSnapshot(upper.state);
        check(gz::decode(actionBytes.data(),actionBytes.size(),out)&&out.snapshot.players[0].action==gz::Action::Uppercut
            &&out.snapshot.players[0].actionTime>.18f,"authoritative animation phase roundtrip");
    for(std::size_t n=0;n<bytes.size();++n) check(!gz::decode(bytes.data(),n,out),"reject every truncated snapshot");
    auto corrupt=bytes;corrupt[20]^=1;check(!gz::decode(corrupt.data(),corrupt.size(),out),"CRC corruption");
    auto input=gz::encodeInput({3,gz::Forward,.25f,-.1f});check(gz::decode(input.data(),input.size(),out),"input roundtrip");
    input=gz::encodeInput({3,1024,0,0});check(!gz::decode(input.data(),input.size(),out),"reject unknown buttons");
    input=gz::encodeInput({3,0,std::numeric_limits<float>::quiet_NaN(),0});check(!gz::decode(input.data(),input.size(),out),"reject NaN");
    input=gz::encodeInput({3,0,0,3});check(!gz::decode(input.data(),input.size(),out),"reject pitch bounds");
    std::mt19937 random(7);
    for(int i=0;i<10000;++i) {
        gz::Bytes noise(random()%200);for(auto& b:noise) b=std::uint8_t(random());
        check(!gz::decode(noise.data(),noise.size(),out),"random malformed packet");
    }
    std::cout<<checks<<" checks passed\n";
}