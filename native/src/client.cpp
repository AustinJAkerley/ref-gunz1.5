#include "network.hpp"
#include <raylib.h>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <string>

namespace {
constexpr Color background{10,16,25,255},panel{14,24,36,235},cyan{81,224,210,255};
constexpr Color muted{133,159,178,255},orange{255,173,91,255};
Vector3 v(gz::Vec a) {return {a.x,a.y,a.z};}
void label(const char* text,int x,int y,int size,Color color=RAYWHITE) {DrawText(text,x,y,size,color);}
void box(const gz::Box& b,Color color) {
    DrawCubeV(v((b.lo+b.hi)*.5f),v(b.hi-b.lo),color);
    DrawCubeWiresV(v((b.lo+b.hi)*.5f),v(b.hi-b.lo),Fade(cyan,.16f));
}
void character(const gz::Player& p,Color color) {
    const auto base=p.position;
    DrawCapsule(v(base+gz::Vec{0,.4f,0}),v(base+gz::Vec{0,1.35f,0}),.3f,6,10,color);
    DrawSphere(v(base+gz::Vec{0,1.62f,0}),.22f,Fade(RAYWHITE,.9f));
    auto hand=base+gz::Vec{0,1.15f,0}+gz::direction(p.yaw+1.5708f)*.35f;
    DrawCylinderEx(v(hand),v(hand+gz::direction(p.yaw,p.pitch)*.8f),.07f,.05f,6,orange);
}
}

int main(int argc,char** argv) try {
    const auto opts=gz::options(argc,argv);
    gz::NetworkRuntime network;gz::Connection connection(opts.port);
    SetTraceLogLevel(LOG_WARNING);
    SetConfigFlags(FLAG_WINDOW_RESIZABLE|FLAG_MSAA_4X_HINT);
    InitWindow(1280,800,"GunZ | Native Lab - Linux / Windows source build");
    if(!IsWindowReady()) throw std::runtime_error("graphics window could not be initialized");
    SetWindowMinSize(960,600);SetExitKey(KEY_NULL);SetTargetFPS(120);
    Camera3D camera{};camera.up={0,1,0};camera.fovy=65;camera.projection=CAMERA_PERSPECTIVE;
    gz::Input input;gz::Player local=gz::spawn(1);gz::World preview;
    bool captured=false,havePlayer=false,finished=false;
    unsigned frames=0,snapshots=0,seenHits=0,seenShots=0;
    float yaw=0,pitch=0,hitFlash=0,shotFlash=0,elapsed=0,netTime=0,maxY=0;
    const auto started=gz::Clock::now();
    const std::string renderer="OpenGL 3.3";
    while(!WindowShouldClose()&&!finished) {
        const float dt=std::min(GetFrameTime(),.05f);elapsed=float(std::chrono::duration<double>(gz::Clock::now()-started).count());
        connection.poll();
        if(connection.updated) {
            ++snapshots;
            for(const auto& p:connection.snapshot.players) if(p.id==connection.id) {
                if(p.hits>seenHits) hitFlash=.16f;
                if(p.shots>seenShots) shotFlash=.08f;
                seenHits=p.hits;seenShots=p.shots;
                local=p;havePlayer=true;maxY=std::max(maxY,p.position.y);
            }
        }
        if(!IsWindowFocused()&&captured) {EnableCursor();captured=false;}
        if(IsKeyPressed(KEY_ESCAPE)) {
            if(captured) {EnableCursor();captured=false;} else if(!opts.smoke) finished=true;
        }
        if(IsMouseButtonPressed(MOUSE_BUTTON_LEFT)&&!captured&&!opts.smoke) {DisableCursor();captured=true;}
        if(IsKeyPressed(KEY_F11)) ToggleFullscreen();
        input.buttons=0;
        if(captured) {
            const auto delta=GetMouseDelta();yaw+=delta.x*.0025f;pitch-=delta.y*.0025f;
            yaw=std::remainder(yaw,2*PI);pitch=std::clamp(pitch,-1.4f,1.4f);
            if(IsKeyDown(KEY_W)) input.buttons|=gz::Forward;
            if(IsKeyDown(KEY_S)) input.buttons|=gz::Back;
            if(IsKeyDown(KEY_A)) input.buttons|=gz::Left;
            if(IsKeyDown(KEY_D)) input.buttons|=gz::Right;
            if(IsMouseButtonDown(MOUSE_BUTTON_LEFT)) input.buttons|=gz::Fire;
            if(IsMouseButtonDown(MOUSE_BUTTON_RIGHT)) input.buttons|=gz::Slash;
        }
        // Keep one-shot actions until the next network send, even at >60 FPS.
        static std::uint32_t pending=0;
        if(captured) {
            if(IsKeyPressed(KEY_SPACE)) pending|=gz::Jump;
            if(IsKeyPressed(KEY_LEFT_SHIFT)) pending|=gz::Dash;
            if(IsKeyPressed(KEY_R)) pending|=gz::Reset;
        } else pending=0;
        if(opts.smoke&&connection.id) {
            input.buttons=gz::Fire;
            if(input.sequence>120&&input.sequence<160) input.buttons|=gz::Right;
            if(input.sequence==140) pending|=gz::Jump;
            if(input.sequence==270) pending|=gz::Reset;
        }
        input.yaw=yaw;input.pitch=pitch;netTime+=dt;
        if(netTime>=gz::tick) {
            // Preserve sub-tick remainder; do not burst stale inputs after a stall.
            netTime=std::fmod(netTime,gz::tick);
            input.buttons|=pending;pending=0;++input.sequence;connection.input(input);
        }
        hitFlash=std::max(0.f,hitFlash-dt);shotFlash=std::max(0.f,shotFlash-dt);
        const auto eye=local.position+gz::Vec{0,1.45f,0},aim=gz::direction(yaw,pitch);
        const auto forward=gz::direction(yaw);
        auto desired=eye-forward*4.5f+gz::Vec{0,1.5f,0}+gz::direction(yaw+PI/2)*.9f;
        auto offset=desired-eye;float distance=gz::length(offset);
        for(const auto& b:gz::arena()) distance=gz::rayBox(eye,gz::unit(offset),b,distance);
        camera.position=v(eye+gz::unit(offset)*std::max(.2f,distance-.15f));
        camera.target=v(eye+aim*30);
        BeginDrawing();ClearBackground(background);
        BeginMode3D(camera);
        const auto& boxes=gz::arena();
        for(std::size_t i=0;i<boxes.size();++i) box(boxes[i],i==0?Color{24,38,49,255}:i<5?Color{36,53,68,255}:Color{59,80,94,255});
        for(int x=-18;x<=18;x+=2) DrawLine3D({float(x),.015f,-22},{float(x),.015f,22},Color{39,61,74,255});
        for(int z=-22;z<=22;z+=2) DrawLine3D({-18,.015f,float(z)},{18,.015f,float(z)},Color{39,61,74,255});
        for(int x:{-17,17}) for(int z=-20;z<=20;z+=5) {
            DrawCube({float(x),.025f,float(z)},.12f,.04f,2,cyan);
            DrawCube({float(x),3.8f,float(z)},.08f,.1f,1.8f,Fade(cyan,.8f));
        }
        DrawCube({0,.02f,-10},5,.03f,2,Color{28,84,88,255});
        const auto& state=connection.id?connection.snapshot:preview.state;
        for(const auto& t:state.targets) {
            DrawCylinder(v(t.position),.75f,.75f,.05f,24,Color{65,81,87,255});
            if(t.hp==0) continue;
            const auto color=t.hp<50?orange:Color{227,108,97,255};
            DrawCube(v(t.position+gz::Vec{0,1,0}),.85f,2,.85f,color);
            DrawCubeWires(v(t.position+gz::Vec{0,1,0}),.86f,2.01f,.86f,RAYWHITE);
            DrawSphere(v(t.position+gz::Vec{0,2.25f,0}),.16f,cyan);
            DrawCube(v(t.position+gz::Vec{0,2.7f,0}),float(t.hp)*.012f,.08f,.08f,cyan);
        }
        for(const auto& p:state.players) character(p,p.id==connection.id?cyan:Color{177,152,240,255});
        if(shotFlash>0) {
            DrawLine3D(v(eye),v(local.shotEnd),orange);
            DrawSphere(v(eye+aim*.7f),.09f,ORANGE);
        }
        EndMode3D();
        const int width=GetScreenWidth(),h=GetScreenHeight();
        DrawRectangle(0,0,width,4,cyan);
        DrawRectangleRounded({24,23,340,78},.12f,8,panel);
        label("GUNZ / NATIVE LAB",42,36,24);
        label("01   //   FOUNDATION ARENA",43,70,15,cyan);
        DrawRectangleRounded({float(width-299),23,275,78},.12f,8,panel);
        DrawCircle(width-278,47,4,connection.id?cyan:orange);
        label(connection.id?"LOCAL SERVER / CONNECTED":"WAITING FOR LOCAL SERVER",width-264,39,15,connection.id?cyan:orange);
        label(TextFormat("%u ms   |   %i FPS   |   %s",connection.ping(),GetFPS(),renderer.c_str()),width-282,70,14,muted);
        DrawRectangleRounded({24,float(h-135),300,107},.08f,8,panel);
        label("VITALS",42,h-120,13,muted);
        label(TextFormat("%03i",local.hp),42,h-99,32);
        DrawRectangle(120,h-91,180,8,Color{39,58,72,255});
        DrawRectangle(120,h-91,int(local.hp*1.8f),8,cyan);
        label(local.dashCooldown<=0?"DASH READY":"DASH RECHARGING",42,h-52,14,local.dashCooldown<=0?cyan:muted);
        DrawRectangleRounded({float(width-270),float(h-135),246,107},.08f,8,panel);
        label("RANGE SESSION",width-252,h-120,13,muted);
        label(TextFormat("%02u  TARGETS",local.score),width-252,h-98,25,orange);
        label(TextFormat("HITS %u / SHOTS %u",local.hits,local.shots),width-252,h-58,15,muted);
        const auto cross=GetWorldToScreen(v(eye+aim*40),camera);
        const Color crossColor=hitFlash>0?orange:RAYWHITE;
        DrawLine(int(cross.x)-10,int(cross.y),int(cross.x)-4,int(cross.y),crossColor);
        DrawLine(int(cross.x)+4,int(cross.y),int(cross.x)+10,int(cross.y),crossColor);
        DrawLine(int(cross.x),int(cross.y)-10,int(cross.x),int(cross.y)-4,crossColor);
        DrawLine(int(cross.x),int(cross.y)+4,int(cross.x),int(cross.y)+10,crossColor);
        if(hitFlash>0) DrawCircleLines(int(cross.x),int(cross.y),16,orange);
        const char* controls="WASD move   SPACE jump / rebound   SHIFT dash   LMB fire   RMB slash   R respawn";
        const int controlSize=width<1100?12:14;
        label(controls,(width-MeasureText(controls,controlSize))/2,h-20,controlSize,muted);
        if(!captured&&!opts.smoke) {
            const int w=520,x=(width-w)/2,y=h/2-40;
            DrawRectangleRounded({float(x),float(y),float(w),125},.12f,10,Color{9,18,29,242});
            label(connection.id?"CLICK TO ENTER THE ARENA":"START THE NATIVE SERVER",x+28,y+22,25,cyan);
            label("Generated assets. Native test protocol. Not full 1.5 yet.",x+28,y+66,15,muted);
            label("ESC releases mouse / exits    |    F11 fullscreen",x+28,y+94,15,muted);
        }
        if(!connection.id&&elapsed>5) label("Server unavailable: launch gunz-server, then restart this client.",28,115,17,orange);
        EndDrawing();++frames;
        if(opts.seconds>0&&elapsed>=opts.seconds) finished=true;
        if(finished&&!opts.screenshot.empty()) {
            Image image=LoadImageFromScreen();
            const bool saved=ExportImage(image,opts.screenshot.c_str());
            UnloadImage(image);
            if(!saved) throw std::runtime_error("cannot export screenshot");
        }
    }
    const bool ok=havePlayer&&frames>30&&snapshots>10&&(!opts.smoke||(seenHits>0&&maxY>.5f));
    if(!opts.report.empty()) {
        std::ofstream f(opts.report);if(!f) throw std::runtime_error("cannot write client report");
        f<<"{\"ok\":"<<(ok?"true":"false")<<",\"frames\":"<<frames<<",\"snapshots\":"<<snapshots
         <<",\"hits\":"<<seenHits<<",\"shots\":"<<seenShots<<",\"max_y\":"<<maxY<<"}\n";
    }
    CloseWindow();return opts.smoke&&!ok?1:0;
} catch(const std::exception& e) {std::cerr<<"client: "<<e.what()<<'\n';return 1;}