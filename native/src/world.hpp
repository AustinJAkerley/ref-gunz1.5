#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>

namespace gz {
constexpr float tick = 1.0f / 60.0f;
constexpr float radius = .35f, height = 1.8f, runSpeed = 6.3f;
constexpr std::uint32_t maxPlayers = 8;
constexpr std::uint16_t defaultPort = 27650;
struct Vec {
    float x = 0, y = 0, z = 0;
    Vec operator+(Vec b) const { return {x+b.x,y+b.y,z+b.z}; }
    Vec operator-(Vec b) const { return {x-b.x,y-b.y,z-b.z}; }
    Vec operator*(float s) const { return {x*s,y*s,z*s}; }
    Vec& operator+=(Vec b) { *this = *this+b; return *this; }
};
inline float dot(Vec a, Vec b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
inline float length(Vec v) { return std::sqrt(dot(v,v)); }
inline Vec unit(Vec v) { const auto n=length(v); return n>.0001f?v*(1/n):Vec{}; }
inline Vec direction(float yaw,float pitch=0) {
    return {std::sin(yaw)*std::cos(pitch),std::sin(pitch),std::cos(yaw)*std::cos(pitch)};
}
struct Box { Vec lo,hi; };
const std::vector<Box>& arena();
enum Button : std::uint32_t {
    Forward=1, Back=2, Left=4, Right=8, Jump=16, Dash=32, Primary=64, Secondary=128, Reset=256, Guard=512
};
constexpr std::uint32_t validButtons=1023;
enum class Action : std::uint32_t {
    Idle, Attack1, Attack2, Attack3, Attack4, AirSlash, Uppercut, Guard,
    DashForward, DashBack, DashRight, DashLeft
};
inline bool isDash(Action a) {return a>=Action::DashForward&&a<=Action::DashLeft;}
inline bool isAttack(Action a) {return a>=Action::Attack1&&a<=Action::Uppercut;}
// Source: ZMyCharacter::OnTumble (1000 cm/s); katana ANI 1600 ticks / 4800 ticks/s.
constexpr float dashSpeed=10.f,dashDuration=1600.f/4800.f;
// Original zitem.xml item 2: katana01, damage=15, range=220 cm, delay=359 ms.
constexpr int katanaDamage=15;
constexpr float katanaRange=2.2f;
inline float actionDuration(Action a) {
    switch(a) {
        // Original GetSelectWeaponDelay: item delay minus 299 ms, added to clip length.
        case Action::Attack1:return .3f+.06f;
        case Action::Attack2:return 1760.f/4800.f+.06f;
        case Action::Attack3:return .5f+.06f;
        case Action::Attack4:return 1.f+.06f;
        case Action::AirSlash:return .5f+.06f;
        case Action::Uppercut:return 2720.f/4800.f;
        case Action::Guard:return 2.f;
        default:return isDash(a)?dashDuration:0.f;
    }
}
inline float hitTime(Action a) {return a==Action::Attack1?.1f:a==Action::Uppercut?.18f:0.f;}
struct Input { std::uint32_t sequence=0, buttons=0; float yaw=0,pitch=0; };
struct Player {
    std::uint32_t id=0, ack=0, swings=0, hits=0, score=0;
    Vec position{}, velocity{};
    float yaw=0,pitch=0,dashCooldown=0,jumpBuffer=0;
    Action action=Action::Idle;
    float actionTime=0,comboWindow=0,stun=0;
    std::uint32_t combo=0;
    Vec dashDirection{};
    bool hitApplied=false,guardExhausted=false;
    int hp=100;
    bool grounded=true;
};
struct Target { Vec position; int hp=100; float respawn=0; };
struct Snapshot { std::uint32_t tick=0; std::vector<Player> players; std::array<Target,4> targets{}; };
Player spawn(std::uint32_t id);
void move(Player& player,const Input& input,float dt=tick);
float rayBox(Vec origin,Vec ray,const Box& box,float limit);
class World {
public:
    Snapshot state;
    World();
    Player* find(std::uint32_t id);
    void step(const std::vector<std::pair<std::uint32_t,Input>>& inputs);
private:
    std::vector<std::uint32_t> respawned;
    void attack(Player& player);
};
} // namespace gz