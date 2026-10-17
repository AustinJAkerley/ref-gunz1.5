#include "network.hpp"
#include "map.hpp"
#include <enet/enet.h>
#include <cmath>
#include <string>

namespace gz {
NetworkRuntime::NetworkRuntime() {if(enet_initialize()!=0) throw std::runtime_error("ENet initialization failed");}
NetworkRuntime::~NetworkRuntime() {enet_deinitialize();}
unsigned Connection::ping() const {return peer?peer->roundTripTime:0;}
void send(ENetPeer* peer,const Bytes& data,bool reliable) {
    auto* packet=enet_packet_create(data.data(),data.size(),reliable?ENET_PACKET_FLAG_RELIABLE:0);
    if(!packet) throw std::runtime_error("packet allocation failed");
    if(enet_peer_send(peer,reliable?0:1,packet)!=0) enet_packet_destroy(packet);
}
Connection::Connection(std::uint16_t port) {
    host=enet_host_create(nullptr,1,2,0,0);
    if(!host) throw std::runtime_error("client socket allocation failed");
    host->maximumPacketSize=4096;host->maximumWaitingData=65536;
    ENetAddress address{};address.port=port;enet_address_set_host_ip(&address,"127.0.0.1");
    peer=enet_host_connect(host,&address,2,protocolVersion*10+(map().active()?2:1));
    if(!peer) {enet_host_destroy(host);host=nullptr;throw std::runtime_error("connect failed");}
    enet_peer_timeout(peer,8,2000,5000);
}
Connection::~Connection() {
    if(peer) {enet_peer_disconnect_now(peer,0);enet_host_flush(host);}
    if(host) enet_host_destroy(host);
}
void Connection::poll() {
    updated=false;ENetEvent event{};
    for(int budget=0;budget<128&&enet_host_service(host,&event,0)>0;++budget) {
        if(event.type==ENET_EVENT_TYPE_CONNECT) connected=true;
        else if(event.type==ENET_EVENT_TYPE_DISCONNECT) {connected=false;id=0;}
        else if(event.type==ENET_EVENT_TYPE_RECEIVE) {
            Message message{};
            if(decode(event.packet->data,event.packet->dataLength,message)) {
                if(message.kind==Kind::Welcome) id=message.id;
                if(message.kind==Kind::Snapshot && (message.snapshot.tick==snapshot.tick||newer(message.snapshot.tick,snapshot.tick))) {
                    snapshot=std::move(message.snapshot);updated=true;lastSnapshot=Clock::now();
                }
            }
            enet_packet_destroy(event.packet);
        }
    }
    if(id && Clock::now()-lastSnapshot>std::chrono::seconds(5)) {connected=false;id=0;}
}
void Connection::input(const Input& in) {
    if(connected && id) {send(peer,encodeInput(in));enet_host_flush(host);}
}
Options options(int argc,char** argv) {
    Options result;
    for(int i=1;i<argc;++i) {
        const std::string arg=argv[i];
        if(arg=="--smoke") result.smoke=true;
        else {
            if(i+1>=argc) throw std::runtime_error("missing argument value: "+arg);
            const std::string value=argv[++i];std::size_t used=0;
            if(arg=="--port") {
                auto port=std::stoul(value,&used);if(used!=value.size()||port<1024||port>65535) throw std::runtime_error("invalid port");
                result.port=static_cast<std::uint16_t>(port);
            } else if(arg=="--seconds") {
                result.seconds=std::stod(value,&used);
                if(used!=value.size()||!std::isfinite(result.seconds)||result.seconds<=0||result.seconds>86400) throw std::runtime_error("invalid duration");
            } else if(arg=="--screenshot") result.screenshot=value;
            else if(arg=="--report") result.report=value;
            else if(arg=="--assets") result.assets=value;
            else throw std::runtime_error("unknown option: "+arg);
        }
    }
    return result;
}
} // namespace gz