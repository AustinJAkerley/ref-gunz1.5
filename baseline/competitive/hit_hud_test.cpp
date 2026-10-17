// Standalone render test: hidden window on isolated Xvfb, never starts Gunz.exe.
#include <cassert>
#include <windows.h>
#include <d3d9.h>
#include <objidl.h>
#include <gdiplus.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include "MUtil.h"
#include "RMath.h"
using namespace RealSpace2;
#include "hit_hud.hpp"

static void check(bool value,const char* why){if(!value)throw std::runtime_error(why);}
int main()try{
    using namespace competitive;
    for(int amount:{1,7,43,108,999,10000}){
        auto quads=hitLayout(amount);check(!quads.empty()&&quads[0].glyph==0,"HIT is first");
        const float h=quads[0].top-quads[0].bottom;
        for(size_t i=1;i<quads.size();++i){
            check(std::abs(quads[i].top-quads[0].top)<.001f,"aligned tops");
            check(std::abs((quads[i].top-quads[i].bottom)-h)<.001f,"same visible height");
            check(quads[i].left>quads[i-1].right,"no overlap");
        }
    }
    const auto two=hitLayout(43);check(two.size()==3&&two[1].glyph==5&&two[2].glyph==4,"43 digit order");
    check(hitLayout(0).empty()&&hitLayout(-1).empty()&&hitLayout(10001).empty(),"invalid numbers suppressed");
    check(hitOpacity(0)==0&&hitOpacity(33)==1&&hitOpacity(550)==1&&hitOpacity(650)==0,"fade lifetime");
    Gdiplus::GdiplusStartupInput startup;ULONG_PTR token=0;
    check(Gdiplus::GdiplusStartup(&token,&startup,nullptr)==Gdiplus::Ok,"GDI+ startup");
    HGLOBAL buffer=GlobalAlloc(GMEM_MOVEABLE,sizeof(hit_art::png));check(buffer!=nullptr,"PNG buffer");
    memcpy(GlobalLock(buffer),hit_art::png,sizeof(hit_art::png));GlobalUnlock(buffer);
    IStream* stream=nullptr;check(SUCCEEDED(CreateStreamOnHGlobal(buffer,TRUE,&stream)),"PNG stream");
    auto* image=Gdiplus::Bitmap::FromStream(stream);
    check(image&&image->GetLastStatus()==Gdiplus::Ok&&image->GetWidth()==1024&&image->GetHeight()==64,"GDI+ reads generated PNG");
    HWND window=CreateWindowA("STATIC","HIT renderer test",WS_POPUP,0,0,1600,1200,nullptr,nullptr,GetModuleHandle(nullptr),nullptr);
    check(window!=nullptr,"hidden test window");
    auto* d3d=Direct3DCreate9(D3D_SDK_VERSION);check(d3d!=nullptr,"D3D9 interface");
    for(const auto size:{std::pair<int,int>{800,600},{1280,800},{1920,1080}}){
        const int width=size.first,height=size.second;
        D3DPRESENT_PARAMETERS pp{};pp.Windowed=TRUE;pp.SwapEffect=D3DSWAPEFFECT_DISCARD;
        pp.hDeviceWindow=window;pp.BackBufferWidth=width;pp.BackBufferHeight=height;pp.BackBufferFormat=D3DFMT_X8R8G8B8;
        IDirect3DDevice9* device=nullptr;
        check(SUCCEEDED(d3d->CreateDevice(0,D3DDEVTYPE_HAL,window,D3DCREATE_SOFTWARE_VERTEXPROCESSING,&pp,&device)),"D3D9 test device");
        IDirect3DTexture9* texture=nullptr;
        check(SUCCEEDED(device->CreateTexture(1024,64,1,0,D3DFMT_A8R8G8B8,D3DPOOL_MANAGED,&texture,nullptr)),"atlas texture");
        Gdiplus::BitmapData pixels;Gdiplus::Rect rect(0,0,1024,64);
        check(image->LockBits(&rect,Gdiplus::ImageLockModeRead,PixelFormat32bppARGB,&pixels)==Gdiplus::Ok,"atlas pixels");
        D3DLOCKED_RECT target{};check(SUCCEEDED(texture->LockRect(0,&target,nullptr,0)),"texture pixels");
        for(int y=0;y<64;++y)memcpy(static_cast<char*>(target.pBits)+y*target.Pitch,static_cast<char*>(pixels.Scan0)+y*pixels.Stride,1024*4);
        texture->UnlockRect(0);image->UnlockBits(&pixels);
        for(bool fix:{false,true})for(int damage:{7,43,108,10000}){
            device->SetRenderState(D3DRS_SCISSORTESTENABLE,FALSE);
            device->Clear(0,nullptr,D3DCLEAR_TARGET,0xff000000,1,0);
            // Deliberately hostile prior HUD state: renderer must override + restore it.
            device->SetRenderState(D3DRS_SCISSORTESTENABLE,TRUE);
            RECT clip{0,0,1,1};device->SetScissorRect(&clip);
            check(SUCCEEDED(device->BeginScene()),"begin render");
            DrawCompetitiveHit(device,texture,width,height,fix,damage,100);
            check(SUCCEEDED(device->EndScene()),"end render");
            DWORD restored=FALSE;device->GetRenderState(D3DRS_SCISSORTESTENABLE,&restored);check(restored==TRUE,"restore render state");
            IDirect3DSurface9 *back=nullptr,*copy=nullptr;device->GetRenderTarget(0,&back);
            check(SUCCEEDED(device->CreateOffscreenPlainSurface(width,height,D3DFMT_X8R8G8B8,D3DPOOL_SYSTEMMEM,&copy,nullptr)),"readback surface");
            check(SUCCEEDED(device->GetRenderTargetData(back,copy)),"render readback");
            D3DLOCKED_RECT output{};copy->LockRect(&output,nullptr,D3DLOCK_READONLY);
            int left=width,right=0,top=height,bottom=0,lit=0;
            for(int y=0;y<height;++y){auto* row=reinterpret_cast<unsigned*>(static_cast<char*>(output.pBits)+y*output.Pitch);
                for(int x=0;x<width;++x)if(row[x]&0x00ffffff){++lit;left=std::min(left,x);right=std::max(right,x);top=std::min(top,y);bottom=std::max(bottom,y);}}
            check(lit>100&&left>width/2&&top<height/4,"visible upper-right HIT damage");
            check(right<width-2&&top>0&&bottom<height/3,"one-to-five digits fit on screen");
            printf("PASS: HIT %d at %dx%d fix=%d bounds=(%d,%d)-(%d,%d)\n",damage,width,height,fix,left,top,right,bottom);
            copy->UnlockRect();copy->Release();back->Release();
        }
        texture->Release();device->Release();
    }
    delete image;stream->Release();d3d->Release();DestroyWindow(window);Gdiplus::GdiplusShutdown(token);
    puts("PASS: original-size HIT layout, GDI+ PNG load, actual D3D rendering and state restoration");return 0;
}catch(const std::exception& e){fprintf(stderr,"FAIL: %s\n",e.what());return 1;}