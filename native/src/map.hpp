#pragma once
#include "world.hpp"
#include <string>
#include <unordered_map>

namespace gz {
struct Triangle { Vec a,b,c,normal; Box bounds; };
class CollisionMap {
    std::vector<Triangle> triangles;
    std::vector<Player> spawns;
    std::unordered_map<std::int64_t,std::vector<std::size_t>> grid;
    std::vector<std::size_t> nearby(Vec point,float extent) const;
public:
    bool active() const {return !triangles.empty();}
    void load(const std::string& path);
    Player spawn(std::uint32_t id) const;
    float ray(Vec origin,Vec direction,float limit) const;
    void move(Player& player,float dt) const;
    Vec wall(Vec point) const;
};
CollisionMap& map();
}