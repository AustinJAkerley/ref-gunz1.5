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
    Forward=1, Back=2, Left=4, Right=8, Jump=16, Dash=32, Fire=64, Slash=128, Reset=256
};
constexpr std::uint32_t validButtons=511;
struct Input { std::uint32_t sequence=0, buttons=0; float yaw=0,pitch=0; };
struct Player {
    std::uint32_t id=0, ack=0, shots=0, hits=0, score=0;
    Vec position{}, velocity{};
    float yaw=0,pitch=0,dashCooldown=0,fireCooldown=0,slashCooldown=0,jumpBuffer=0;
    int hp=100;
    bool grounded=true;
    Vec shotEnd{};
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
    void attack(Player& player,bool melee);
};
} // namespace gz