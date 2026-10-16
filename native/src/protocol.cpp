#include "protocol.hpp"
#include "MCRC32.h"
#include <cstring>
#include <stdexcept>

namespace gz {
namespace {
constexpr std::uint32_t magic=0x475A4E31,version=1;
struct Writer {
    Bytes b;
    void u(std::uint32_t n) { for(int i=0;i<4;++i) b.push_back(std::uint8_t(n>>(8*i))); }
    void f(float n) { std::uint32_t bits;static_assert(sizeof(n)==sizeof(bits));std::memcpy(&bits,&n,4);u(bits); }
    void v(Vec n) {f(n.x);f(n.y);f(n.z);}
    explicit Writer(Kind k) {u(magic);u(version);u(std::uint32_t(k));}
    Bytes finish() {u(MCRC32::BuildCRC32(b.data(),std::uint32_t(b.size())));return b;}
};
struct Reader {
    const std::uint8_t* data;std::size_t size,pos=0;
    std::uint32_t u() {
        if(pos+4>size) throw std::runtime_error("truncated");
        std::uint32_t n=0;for(int i=0;i<4;++i) n|=std::uint32_t(data[pos++])<<(8*i);return n;
    }
    float f() {
        auto bits=u();float n;std::memcpy(&n,&bits,4);
        if(!std::isfinite(n)||std::abs(n)>100000) throw std::runtime_error("invalid float");
        return n;
    }
    Vec v() {return {f(),f(),f()};}
};
}
Bytes encodeWelcome(std::uint32_t id) {Writer w(Kind::Welcome);w.u(id);return w.finish();}
Bytes encodeInput(const Input& in) {
    Writer w(Kind::Input);w.u(in.sequence);w.u(in.buttons);w.f(in.yaw);w.f(in.pitch);return w.finish();
}
Bytes encodeSnapshot(const Snapshot& s) {
    Writer w(Kind::Snapshot);w.u(s.tick);w.u(std::uint32_t(s.players.size()));
    for(const auto& p:s.players) {
        w.u(p.id);w.u(p.ack);w.v(p.position);w.v(p.velocity);w.f(p.yaw);w.f(p.pitch);
        w.u(std::uint32_t(p.hp));w.u(p.grounded?1:0);w.f(p.dashCooldown);
        w.u(p.shots);w.u(p.hits);w.u(p.score);w.v(p.shotEnd);
    }
    for(const auto& t:s.targets) {w.v(t.position);w.u(std::uint32_t(t.hp));w.f(t.respawn);}
    return w.finish();
}
bool decode(const void* ptr,std::size_t size,Message& out) {
    if(!ptr||size<16||size>4096) return false;
    auto data=static_cast<const std::uint8_t*>(ptr);
    try {
        Reader r{data,size-4},checksum{data+size-4,4};
        if(checksum.u()!=MCRC32::BuildCRC32(data,std::uint32_t(size-4))) return false;
        if(r.u()!=magic||r.u()!=version) return false;
        Message m{};m.kind=Kind(r.u());
        if(m.kind==Kind::Welcome) {m.id=r.u();if(m.id==0) return false;}
        else if(m.kind==Kind::Input) {
            auto& in=m.input;in.sequence=r.u();in.buttons=r.u();in.yaw=r.f();in.pitch=r.f();
            if(in.buttons&~validButtons || std::abs(in.yaw)>3.142f || std::abs(in.pitch)>1.45f) return false;
        } else if(m.kind==Kind::Snapshot) {
            auto& s=m.snapshot;s.tick=r.u();auto count=r.u();if(count>maxPlayers) return false;
            for(std::uint32_t i=0;i<count;++i) {
                Player p;p.id=r.u();p.ack=r.u();p.position=r.v();p.velocity=r.v();p.yaw=r.f();p.pitch=r.f();
                auto hp=r.u(),ground=r.u();if(hp>100||ground>1||p.id==0) return false;
                for(const auto& old:s.players) if(old.id==p.id) return false;
                p.hp=int(hp);p.grounded=ground!=0;p.dashCooldown=r.f();
                p.shots=r.u();p.hits=r.u();p.score=r.u();p.shotEnd=r.v();s.players.push_back(p);
            }
            for(auto& t:s.targets) {t.position=r.v();auto hp=r.u();if(hp>100) return false;t.hp=int(hp);t.respawn=r.f();}
        } else return false;
        if(r.pos!=r.size) return false;
        out=std::move(m);return true;
    } catch(const std::runtime_error&) {return false;}
}
} // namespace gz