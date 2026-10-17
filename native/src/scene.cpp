#include "scene.hpp"
#include "asset_reader.hpp"
#include <raymath.h>
#include <rlgl.h>
#include <algorithm>
#include <filesystem>
#include <cstring>
#include <iostream>

namespace gz {
SceneModel::~SceneModel(){
    clear();
}
void SceneModel::clear(){
    for(auto& p:parts){UnloadMesh(p.mesh);UnloadMaterial(p.material);}
    parts.clear();
}
void SceneModel::load(const std::string& path){
    AssetReader r(path);if(r.u()!=0x31415a47)throw std::runtime_error("Model cache version");
    auto count=r.count(256);frames=r.count(120);fps=r.count(120);
    if(!count||!frames||!fps)throw std::runtime_error("Empty model");
    std::size_t budget=0;parts.reserve(count);
    for(unsigned i=0;i<count;++i){
        const auto name=r.text();auto vertices=r.count(1000000);
        budget+=std::size_t(vertices)*frames*3;
        if(!vertices||vertices%3||budget>32000000)throw std::runtime_error("Model vertex budget");
        parts.emplace_back();auto& p=parts.back();p.mesh.vertexCount=int(vertices);p.mesh.triangleCount=int(vertices/3);
        p.mesh.vertices=static_cast<float*>(MemAlloc(vertices*3*sizeof(float)));
        p.mesh.texcoords=static_cast<float*>(MemAlloc(vertices*2*sizeof(float)));
        if(!p.mesh.vertices||!p.mesh.texcoords)throw std::runtime_error("Model allocation");
        for(unsigned j=0;j<vertices*2;++j)p.mesh.texcoords[j]=r.f();
        p.poses.resize(std::size_t(vertices)*3*frames);for(auto& value:p.poses)value=r.f();
        std::copy_n(p.poses.data(),vertices*3,p.mesh.vertices);UploadMesh(&p.mesh,frames>1);
        auto texturePath=std::filesystem::path(path).parent_path()/name;
        p.texture=LoadTexture(texturePath.string().c_str());if(!p.texture.id)throw std::runtime_error("Texture load: "+name);
        SetTextureFilter(p.texture,TEXTURE_FILTER_BILINEAR);SetTextureWrap(p.texture,TEXTURE_WRAP_REPEAT);
        p.material=LoadMaterialDefault();p.material.maps[MATERIAL_MAP_DIFFUSE].texture=p.texture;
    }
    r.end();std::cout<<"ASSET "<<path<<" materials="<<count<<" frames="<<frames<<std::endl;
}
void SceneModel::draw(Vec position,float yaw,float time,bool loop,float duration){
    Matrix transform=MatrixMultiply(MatrixRotateY(yaw),MatrixTranslate(position.x,position.y,position.z));
    const float frameTime=duration>0?std::max(0.f,time)/duration*float(frames-1):std::max(0.f,time)*fps;
    const unsigned frame=loop?unsigned(frameTime)%frames:unsigned(std::min(frameTime,float(frames-1)));
    rlDisableBackfaceCulling();
    for(auto& p:parts){
        if(frames>1){
            const auto size=std::size_t(p.mesh.vertexCount)*3;
            std::copy_n(p.poses.data()+frame*size,size,p.mesh.vertices);
            UpdateMeshBuffer(p.mesh,0,p.mesh.vertices,int(size*sizeof(float)),0);
        }
        DrawMesh(p.mesh,p.material,transform);
    }
    rlEnableBackfaceCulling();
}
void Scene::load(const std::string& directory){
    auto path=std::filesystem::path(directory);
    mansion.load((path/"mansion.gza").string());idle.load((path/"character_idle.gza").string());
    run.load((path/"character_run.gza").string());runBack.load((path/"character_run_back.gza").string());
    jump.load((path/"character_jump.gza").string());jumpDown.load((path/"character_jump_down.gza").string());
    constexpr std::array<const char*,11> names{{"attack1","attack2","attack3","attack4","air_slash","uppercut","guard",
        "dash_forward","dash_back","dash_right","dash_left"}};
    for(std::size_t i=0;i<names.size();++i)actions[i].load((path/(std::string("character_")+names[i]+".gza")).string());
    active=true;
}
void Scene::drawMap(){mansion.draw({},0,0);}
void Scene::clear(){
    mansion.clear();idle.clear();run.clear();runBack.clear();jump.clear();jumpDown.clear();
    for(auto& model:actions)model.clear();
    active=false;
}
void Scene::drawCharacter(const Player& p,float time,float snapshotAge){
    if(p.action!=Action::Idle){
        auto index=std::uint32_t(p.action)-1;
        actions.at(index).draw(p.position,p.yaw+PI,p.actionTime+std::min(snapshotAge,.05f),false,actionDuration(p.action));
        return;
    }
    auto& model=!p.grounded?(p.velocity.y>0?jump:jumpDown):
        std::hypot(p.velocity.x,p.velocity.z)>.5f?(dot(p.velocity,direction(p.yaw))<-.1f?runBack:run):idle;
    // Exported character faces -Z; native movement faces +Z at yaw zero.
    // Jump clips are one-shots, not wall-clock loops or a frozen first frame.
    const float airTime=p.velocity.y>0?std::max(0.f,(9.f-p.velocity.y)/25.f):std::max(0.f,-p.velocity.y/25.f);
    model.draw(p.position,p.yaw+PI,p.grounded?time:airTime,p.grounded);
}
}