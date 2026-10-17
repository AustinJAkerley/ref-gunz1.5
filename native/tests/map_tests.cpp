#include "map.hpp"
#include <iostream>
#include <stdexcept>

void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main(int argc,char** argv)try{
    require(argc==2,"collision fixture path required");gz::map().load(argv[1]);
    auto p=gz::spawn(1);gz::Input in;
    require(gz::map().active(),"map active");
    const float floor=gz::map().ray(p.position+gz::Vec{0,2,0},{0,-1,0},5);
    require(floor>1.8f&&floor<2.3f,"central-hall floor matches map geometry");
    for(int i=0;i<120;++i)gz::move(p,in);
    require(p.grounded&&std::abs(p.position.y)<.1f,"stable original-map floor");
    in.buttons=gz::Jump;gz::move(p,in);in.buttons=0;float apex=0;
    for(int i=0;i<120;++i){gz::move(p,in);apex=std::max(apex,p.position.y);}
    require(apex>1.3f&&apex<1.8f,"map jump clearance");
    require(p.grounded&&std::abs(p.position.y)<.1f,"map landing");
    auto start=p.position;in.buttons=gz::Right;
    for(int i=0;i<40;++i)gz::move(p,in);
    require(gz::length(p.position-start)>1,"map horizontal movement");
    require(p.position.y>-1,"movement stays above floor");
    in.buttons=gz::Reset;gz::move(p,in);
    require(gz::length(p.position-gz::spawn(1).position)<.01f,"map reset");
    gz::World world;world.state.players.push_back(gz::spawn(1));
    in={1,gz::Primary,0,0};for(int i=0;i<240;++i)world.step({{1,in}});
    require(world.find(1)->hits>=7&&world.find(1)->score>=1,"map katana arc and targets");
    std::cout<<"PASS: Mansion floor, jump, landing, movement, reset, katana damage\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}