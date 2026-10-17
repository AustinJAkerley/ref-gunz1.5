#include "network.hpp"
#include "map.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>

int main(int argc,char** argv) try {
    auto opts=gz::options(argc,argv);
    if(!opts.assets.empty())gz::map().load((std::filesystem::path(opts.assets)/"mansion.collision").string());
    gz::NetworkRuntime runtime;gz::Connection connection(opts.port);
    auto start=gz::Clock::now(),next=start;gz::Input input;
    unsigned snapshots=0,peak=0,swings=0,hits=0;float displacement=0,maxY=0;
    bool spawned=false;gz::Vec initial;
    while(std::chrono::duration<double>(gz::Clock::now()-start).count()<(opts.seconds>0?opts.seconds:4)) {
        connection.poll();const auto now=gz::Clock::now();
        if(connection.updated) {
            ++snapshots;peak=std::max(peak,unsigned(connection.snapshot.players.size()));
            for(const auto& p:connection.snapshot.players) if(p.id==connection.id) {
                if(!spawned) {initial=p.position;spawned=true;}
                displacement=std::max(displacement,gz::length(p.position-initial));maxY=std::max(maxY,p.position.y-initial.y);
                swings=p.swings;hits=p.hits;
            }
        }
        if(connection.id && now>=next) {
            ++input.sequence;input.buttons=input.sequence<60?gz::Primary:0;
            if(input.sequence>100 && input.sequence<145) input.buttons|=gz::Right;
            if(input.sequence==110) input.buttons|=gz::Jump;
            if(input.sequence==170) input.buttons|=gz::Dash|gz::Left;
            if(input.sequence>220)input.buttons|=gz::Primary;
            connection.input(input);next=now+std::chrono::microseconds(16667);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    const bool ok=spawned&&snapshots>20&&displacement>1&&maxY>.5f&&swings>2;
    std::string json="{\"ok\":"+std::string(ok?"true":"false")+",\"id\":"+std::to_string(connection.id)+
        ",\"snapshots\":"+std::to_string(snapshots)+",\"peak_players\":"+std::to_string(peak)+
        ",\"displacement\":"+std::to_string(displacement)+",\"max_y\":"+std::to_string(maxY)+
        ",\"swings\":"+std::to_string(swings)+",\"hits\":"+std::to_string(hits)+"}";
    std::cout<<json<<'\n';
    if(!opts.report.empty()) {std::ofstream f(opts.report);if(!f) throw std::runtime_error("cannot write probe report");f<<json<<'\n';}
    return ok?0:1;
} catch(const std::exception& e) {std::cerr<<"probe: "<<e.what()<<'\n';return 1;}