#include "network.hpp"
#include "map.hpp"
#include <filesystem>
#include <enet/enet.h>
#include <algorithm>
#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <map>
#include <thread>

namespace { volatile std::sig_atomic_t stopping=0; void stop(int) {stopping=1;} }
int main(int argc,char** argv) try {
    const auto opts=gz::options(argc,argv);gz::NetworkRuntime runtime;
    if(!opts.assets.empty())gz::map().load((std::filesystem::path(opts.assets)/"mansion.collision").string());
    ENetAddress address{};enet_address_set_host_ip(&address,"127.0.0.1");address.port=opts.port;
    auto* host=enet_host_create(&address,gz::maxPlayers,2,0,0);
    if(!host) throw std::runtime_error("cannot bind loopback UDP port (already in use?)");
    host->maximumPacketSize=4096;host->maximumWaitingData=65536;
    struct Session {std::uint32_t id;gz::Input in{};gz::Clock::time_point last=gz::Clock::now();unsigned packets=0;};
    std::map<ENetPeer*,Session> peers;gz::World world;std::uint32_t nextID=1;
    unsigned joined=0,invalid=0,peak=0;auto start=gz::Clock::now(),next=start,rateWindow=start;
    std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
    std::cout<<"READY 127.0.0.1:"<<opts.port<<" native protocol v"<<gz::protocolVersion<<"; 60 Hz; katana combat"<<std::endl;
    while(!stopping) {
        const auto now=gz::Clock::now();
        if(opts.seconds>0&&std::chrono::duration<double>(now-start).count()>=opts.seconds) break;
        if(now-rateWindow>=std::chrono::seconds(1)) {for(auto& [peer,s]:peers) { (void)peer;s.packets=0;}rateWindow=now;}
        ENetEvent event{};
        for(int budget=0;budget<512&&enet_host_service(host,&event,0)>0;++budget) {
            if(event.type==ENET_EVENT_TYPE_CONNECT) {
                if(event.data!=gz::protocolVersion*10+(gz::map().active()?2u:1u)||peers.size()>=gz::maxPlayers) {enet_peer_disconnect_now(event.peer,1);continue;}
                auto id=nextID++;peers.emplace(event.peer,Session{id});world.state.players.push_back(gz::spawn(id));
                enet_peer_timeout(event.peer,8,2000,5000);gz::send(event.peer,gz::encodeWelcome(id),true);
                ++joined;peak=std::max(peak,unsigned(peers.size()));std::cout<<"JOIN "<<id<<std::endl;
            } else if(event.type==ENET_EVENT_TYPE_DISCONNECT) {
                auto it=peers.find(event.peer);if(it!=peers.end()) {
                    auto id=it->second.id;auto& p=world.state.players;
                    p.erase(std::remove_if(p.begin(),p.end(),[id](const auto& x){return x.id==id;}),p.end());peers.erase(it);
                }
            } else if(event.type==ENET_EVENT_TYPE_RECEIVE) {
                auto it=peers.find(event.peer);gz::Message m{};
                if(it!=peers.end() && ++it->second.packets<=240 && gz::decode(event.packet->data,event.packet->dataLength,m) && m.kind==gz::Kind::Input) {
                    auto& s=it->second;
                    if(gz::newer(m.input.sequence,s.in.sequence)) {
                        auto edges=s.in.buttons&(gz::Jump|gz::Dash|gz::Reset);
                        s.in=m.input;s.in.buttons|=edges;s.last=now;
                    }
                } else ++invalid;
                enet_packet_destroy(event.packet);
            }
        }
        int catchup=0;
        while(now>=next && catchup++<4) {
            std::vector<std::pair<std::uint32_t,gz::Input>> inputs;
            for(auto& [peer,s]:peers) {
                (void)peer;
                if(now-s.last>std::chrono::milliseconds(250)) s.in.buttons=0;
                inputs.emplace_back(s.id,s.in);s.in.buttons&=~(gz::Jump|gz::Dash|gz::Reset);
            }
            world.step(inputs);
            if(world.state.tick%2==0) {
                const auto bytes=gz::encodeSnapshot(world.state);
                for(auto& [peer,s]:peers) {(void)s;gz::send(peer,bytes);}
                enet_host_flush(host);
            }
            next+=std::chrono::microseconds(16667);
        }
        if(now-next>std::chrono::milliseconds(100)) next=now;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    enet_host_destroy(host);
    if(!opts.report.empty()) {
        std::ofstream f(opts.report);if(!f) throw std::runtime_error("cannot write server report");
        f<<"{\"ticks\":"<<world.state.tick<<",\"joined\":"<<joined<<",\"peak_players\":"<<peak<<",\"invalid_packets\":"<<invalid<<"}\n";
    }
    return 0;
} catch(const std::exception& e) {std::cerr<<"server: "<<e.what()<<'\n';return 1;}