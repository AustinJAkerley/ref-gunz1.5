#pragma once
#include "world.hpp"
#include <raylib.h>
#include <string>
#include <vector>
#include <array>

namespace gz {
class SceneModel {
    struct Part { Mesh mesh{};Material material{};Texture2D texture{};std::vector<float> poses; };
    std::vector<Part> parts;
    unsigned frames=1,fps=1;
public:
    SceneModel()=default;
    ~SceneModel();
    SceneModel(const SceneModel&)=delete;
    SceneModel& operator=(const SceneModel&)=delete;
    void load(const std::string& path);
    void clear();
    void draw(Vec position,float yaw,float time,bool loop=true,float duration=0);
};
class Scene {
    SceneModel mansion,idle,run,runBack,jump,jumpDown;
    std::array<SceneModel,11> actions;
public:
    bool active=false;
    void load(const std::string& directory);
    void drawMap();
    void drawCharacter(const Player& p,float time,float snapshotAge=0);
    void clear();
};
}