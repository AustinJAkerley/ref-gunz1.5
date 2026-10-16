#include "protocol.hpp"
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
    auto p=gz::spawn(1);gz::Input in;in.buttons=gz::Forward;
    for(int i=0;i<60;++i) gz::move(p,in);
    check(p.position.z>-5&&p.position.z<-3,"run speed approaches original 6.3 metres/sec");
    check(p.grounded&&std::abs(p.position.y)<.001,"floor collision");
    in.buttons=gz::Jump;gz::move(p,in);check(p.velocity.y>8&&p.position.y>0,"jump impulse");
    in.buttons=0;float apex=0;for(int i=0;i<120;++i) {gz::move(p,in);apex=std::max(apex,p.position.y);}
    check(apex>1.4&&apex<1.7,"original jump/gravity scaling");check(p.grounded,"landing");
    p=gz::spawn(1);in.buttons=gz::Dash|gz::Forward;gz::move(p,in);
    check(p.velocity.z>17&&p.dashCooldown>.6,"dash");
    for(int i=0;i<500;++i) gz::move(p,in);
    check(p.position.z<=22-gz::radius+.001,"solid boundary cannot be crossed");
    p=gz::spawn(1);p.position={17.65f,2,0};p.grounded=false;in.buttons=gz::Jump;gz::move(p,in);
    check(p.velocity.y>13&&p.velocity.x<0,"wall rebound");
    gz::Box box{{-1,0,3},{1,2,4}};
    check(gz::rayBox({0,1,0},{0,0,1},box,10)==3,"ray hit");
    check(gz::rayBox({2,1,0},{0,0,1},box,10)==10,"parallel ray miss");
    gz::World world;world.state.players.push_back(gz::spawn(1));in={1,gz::Fire,0,0};
    for(int i=0;i<50;++i) world.step({{1,in}});
    check(world.find(1)->hits==4&&world.find(1)->score==1,"server target damage and score");
    check(world.state.targets[0].hp==0,"target destroyed");
    for(int i=0;i<190;++i) world.step({});
    check(world.state.targets[0].hp==100,"target respawn");
    // A solid pillar must prevent damage through cover.
    gz::World cover;auto shooter=gz::spawn(1);shooter.position={-9,0,-10};cover.state.players.push_back(shooter);
    cover.state.targets[0].position={-9,0,8};
    for(int i=0;i<60;++i) cover.step({{1,in}});
    check(cover.state.targets[0].hp==100,"server occlusion");
    gz::World duel;auto a=gz::spawn(1),b=gz::spawn(2);
    a.position={3,0,-12};b.position={3,0,-9};b.hp=25;
    duel.state.players={a,b};
    duel.step({{1,{1,gz::Fire,0,0}},{2,{1,gz::Fire,3.14159f,0}}});
    check(duel.find(1)->score==1&&duel.find(2)->hp==100,"player kill and respawn");
    check(duel.find(2)->shots==0,"no attack from stale input during death tick");
    check(gz::newer(0,0xffffffffu)&&!gz::newer(0xffffffffu,0)&&!gz::newer(7,7),"sequence wrap ordering");
    gz::Message out{};auto bytes=gz::encodeSnapshot(world.state);
    check(gz::decode(bytes.data(),bytes.size(),out),"snapshot roundtrip");
    check(out.snapshot.players.size()==1&&out.snapshot.players[0].hits==4,"snapshot fields");
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