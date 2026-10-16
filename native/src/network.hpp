#pragma once
#include "protocol.hpp"
#include <chrono>
#include <stdexcept>

struct _ENetHost;
struct _ENetPeer;
using ENetHost = _ENetHost;
using ENetPeer = _ENetPeer;

namespace gz {
using Clock=std::chrono::steady_clock;
struct NetworkRuntime {
    NetworkRuntime();
    ~NetworkRuntime();
    NetworkRuntime(const NetworkRuntime&)=delete;
    NetworkRuntime& operator=(const NetworkRuntime&)=delete;
};
void send(ENetPeer* peer,const Bytes& data,bool reliable=false);
class Connection {
    ENetHost* host=nullptr;
    ENetPeer* peer=nullptr;
public:
    std::uint32_t id=0;
    Snapshot snapshot;
    bool connected=false,updated=false;
    Clock::time_point lastSnapshot=Clock::now();
    explicit Connection(std::uint16_t port);
    ~Connection();
    Connection(const Connection&)=delete;
    Connection& operator=(const Connection&)=delete;
    void poll();
    void input(const Input& input);
    unsigned ping() const;
};
struct Options {
    std::uint16_t port=defaultPort;
    double seconds=0;
    bool smoke=false;
    std::string screenshot,report;
};
Options options(int argc,char** argv);
} // namespace gz