#include "map.hpp"
#include "asset_reader.hpp"
#include <algorithm>
#include <set>

namespace gz {
namespace {
Vec cross(Vec a,Vec b) {return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
std::int64_t key(int x,int z) {return std::int64_t(std::uint64_t(std::uint32_t(x))<<32|std::uint32_t(z));}
int cell(float x) {return int(std::floor(x/3.f));}
Vec closest(Vec p,const Triangle& t) {
    Vec ab=t.b-t.a,ac=t.c-t.a,ap=p-t.a;float d1=dot(ab,ap),d2=dot(ac,ap);
    if(d1<=0&&d2<=0) return t.a;
    Vec bp=p-t.b;float d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return t.b;
    float vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return t.a+ab*(d1/(d1-d3));
    Vec cp=p-t.c;float d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6)return t.c;
    float vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return t.a+ac*(d2/(d2-d6));
    float va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return t.b+(t.c-t.b)*((d4-d3)/((d4-d3)+(d5-d6)));
    float denom=va+vb+vc;if(std::abs(denom)<1e-10f)return t.a;
    return t.a+ab*(vb/denom)+ac*(vc/denom);
}
float hit(Vec o,Vec d,const Triangle& t,float limit) {
    auto edge1=t.b-t.a,edge2=t.c-t.a,h=cross(d,edge2);float det=dot(edge1,h);
    if(std::abs(det)<1e-7f)return limit;
    float inv=1/det;auto s=o-t.a;float u=inv*dot(s,h);if(u<0||u>1)return limit;
    auto q=cross(s,edge1);float v=inv*dot(d,q);if(v<0||u+v>1)return limit;
    float distance=inv*dot(edge2,q);return distance>=0&&distance<limit?distance:limit;
}
}
CollisionMap& map() {static CollisionMap instance;return instance;}
void CollisionMap::load(const std::string& path) {
    AssetReader r(path);if(r.u()!=0x31435a47)throw std::runtime_error("Collision cache version");
    auto count=r.count(200000),spawnCount=r.count(128);if(!count||!spawnCount)throw std::runtime_error("Empty collision");
    triangles.clear();grid.clear();spawns.clear();
    for(unsigned i=0;i<spawnCount;++i){Player p;p.position={r.f(),r.f(),r.f()};p.yaw=r.f();spawns.push_back(p);}
    std::size_t references=0;
    for(unsigned i=0;i<count;++i){
        Triangle t;t.a={r.f(),r.f(),r.f()};t.b={r.f(),r.f(),r.f()};t.c={r.f(),r.f(),r.f()};
        t.normal=unit(cross(t.b-t.a,t.c-t.a));if(length(t.normal)<.5f)continue;
        t.bounds={{std::min({t.a.x,t.b.x,t.c.x}),std::min({t.a.y,t.b.y,t.c.y}),std::min({t.a.z,t.b.z,t.c.z})},
                  {std::max({t.a.x,t.b.x,t.c.x}),std::max({t.a.y,t.b.y,t.c.y}),std::max({t.a.z,t.b.z,t.c.z})}};
        const auto index=triangles.size();triangles.push_back(t);
        for(int x=cell(t.bounds.lo.x);x<=cell(t.bounds.hi.x);++x)for(int z=cell(t.bounds.lo.z);z<=cell(t.bounds.hi.z);++z){
            if(++references>3000000)throw std::runtime_error("Collision spatial budget");
            grid[key(x,z)].push_back(index);
        }
    }
    r.end();
}
std::vector<std::size_t> CollisionMap::nearby(Vec p,float extent) const {
    std::vector<std::size_t> out;
    for(int x=cell(p.x-extent);x<=cell(p.x+extent);++x)for(int z=cell(p.z-extent);z<=cell(p.z+extent);++z){
        auto it=grid.find(key(x,z));if(it!=grid.end())out.insert(out.end(),it->second.begin(),it->second.end());
    }
    std::sort(out.begin(),out.end());out.erase(std::unique(out.begin(),out.end()),out.end());return out;
}
Player CollisionMap::spawn(std::uint32_t id) const {
    auto p=spawns[(id-1)%spawns.size()];p.id=id;p.position.y+=.1f;
    if(id==1){p.yaw=0;p.position={0,.1f,-4};} // Verified ground-floor central hall, camera clear of walls.
    return p;
}
float CollisionMap::ray(Vec o,Vec d,float limit) const {
    // The map is small (~31k triangles); reject triangle AABBs before exact tests.
    for(const auto& t:triangles)if(rayBox(o,d,t.bounds,limit)<limit)limit=hit(o,d,t,limit);
    return limit;
}
Vec CollisionMap::wall(Vec p) const {
    auto center=p+Vec{0,.9f,0};
    for(auto i:nearby(p,.6f)) {
        const auto& t=triangles[i];if(std::abs(t.normal.y)>.3f)continue;
        auto delta=center-closest(center,t);float distance=length(delta);
        if(distance>.001f&&distance<radius+.15f)return delta*(1/distance);
    }
    return {};
}
void CollisionMap::move(Player& p,float dt) const {
    p.grounded=false;
    // Substeps and a three-sphere capsule approximation. Not original BSP cylinder physics.
    for(int step=0;step<4;++step){
        p.position+=p.velocity*(dt/4);
        const auto candidates=nearby(p.position,.9f);
        for(int iteration=0;iteration<3;++iteration)for(float y:{radius,.9f,height-radius})for(auto index:candidates){
            const auto& t=triangles[index];Vec center=p.position+Vec{0,y,0};
            if(center.y+radius<t.bounds.lo.y||center.y-radius>t.bounds.hi.y)continue;
            Vec delta=center-closest(center,t);float distance=length(delta);
            if(distance>=radius||distance<.00001f)continue;
            Vec normal=delta*(1/distance);p.position+=normal*(radius-distance+.0001f);
            float inward=dot(p.velocity,normal);if(inward<0)p.velocity=p.velocity-normal*inward;
            if(normal.y>.55f)p.grounded=true;
        }
    }
    if(p.velocity.y<=0){
        Vec origin=p.position+Vec{0,.16f,0};float floor=.22f;
        for(auto index:nearby(p.position,.4f))floor=hit(origin,{0,-1,0},triangles[index],floor);
        if(floor<.22f){p.position.y=origin.y-floor+.001f;p.velocity.y=0;p.grounded=true;}
    }
}
}