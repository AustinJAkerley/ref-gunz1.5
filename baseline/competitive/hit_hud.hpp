#pragma once
#include "hit_layout.hpp"

// Called inside the original screen-effects pass. Use exactly its view/projection,
// not guessed normalized coordinates or an unrelated Mint font.
inline void DrawCompetitiveHit(IDirect3DDevice9* device,IDirect3DTexture9* texture,
                              int width,int height,bool interfaceFix,int damage,unsigned long long elapsed){
    if(!texture)return;
    const auto quads=competitive::hitLayout(damage);
    const float opacity=competitive::hitOpacity(elapsed);
    if(quads.empty()||opacity<=0)return;
    IDirect3DStateBlock9* state=nullptr;
    if(FAILED(device->CreateStateBlock(D3DSBT_ALL,&state)))return;
    state->Capture();
    auto view=ViewMatrix(rvector(0,0,-650),rvector(0,0,1),rvector(0,1,0));
    float fov=ToRadian(70);
    const float aspect=float(width)/height;
    if(interfaceFix)fov=2.f*atan(tan(fov/2.f)/(4.f/3.f)*aspect);
    else view=ScalingMatrix({1,(4.f/3.f)/aspect,1,1})*view;
    const auto projection=PerspectiveProjectionMatrixViewport(width,height,fov,5,10000);
    const auto world=GetIdentityMatrix();
    device->SetTransform(D3DTS_WORLD,static_cast<const D3DMATRIX*>(world));
    device->SetTransform(D3DTS_VIEW,static_cast<const D3DMATRIX*>(view));
    device->SetTransform(D3DTS_PROJECTION,static_cast<const D3DMATRIX*>(projection));
    device->SetVertexShader(nullptr);device->SetPixelShader(nullptr);
    device->SetFVF(D3DFVF_XYZ|D3DFVF_DIFFUSE|D3DFVF_TEX1);
    device->SetRenderState(D3DRS_ZENABLE,FALSE);device->SetRenderState(D3DRS_ZWRITEENABLE,FALSE);
    device->SetRenderState(D3DRS_LIGHTING,FALSE);device->SetRenderState(D3DRS_FOGENABLE,FALSE);
    device->SetRenderState(D3DRS_CULLMODE,D3DCULL_NONE);device->SetRenderState(D3DRS_ALPHATESTENABLE,FALSE);
    device->SetRenderState(D3DRS_SCISSORTESTENABLE,FALSE);device->SetRenderState(D3DRS_STENCILENABLE,FALSE);
    device->SetRenderState(D3DRS_COLORWRITEENABLE,0xf);device->SetRenderState(D3DRS_FILLMODE,D3DFILL_SOLID);
    device->SetRenderState(D3DRS_SEPARATEALPHABLENDENABLE,FALSE);
    device->SetRenderState(D3DRS_ALPHABLENDENABLE,TRUE);device->SetRenderState(D3DRS_BLENDOP,D3DBLENDOP_ADD);
    device->SetRenderState(D3DRS_SRCBLEND,D3DBLEND_SRCALPHA);device->SetRenderState(D3DRS_DESTBLEND,D3DBLEND_INVSRCALPHA);
    device->SetTexture(0,texture);
    device->SetTextureStageState(0,D3DTSS_COLOROP,D3DTOP_MODULATE);
    device->SetTextureStageState(0,D3DTSS_COLORARG1,D3DTA_TEXTURE);device->SetTextureStageState(0,D3DTSS_COLORARG2,D3DTA_DIFFUSE);
    device->SetTextureStageState(0,D3DTSS_ALPHAOP,D3DTOP_MODULATE);
    device->SetTextureStageState(0,D3DTSS_ALPHAARG1,D3DTA_TEXTURE);device->SetTextureStageState(0,D3DTSS_ALPHAARG2,D3DTA_DIFFUSE);
    device->SetTextureStageState(0,D3DTSS_TEXCOORDINDEX,0);device->SetTextureStageState(0,D3DTSS_TEXTURETRANSFORMFLAGS,D3DTTFF_DISABLE);
    device->SetTextureStageState(1,D3DTSS_COLOROP,D3DTOP_DISABLE);device->SetTextureStageState(1,D3DTSS_ALPHAOP,D3DTOP_DISABLE);
    device->SetSamplerState(0,D3DSAMP_MINFILTER,D3DTEXF_LINEAR);device->SetSamplerState(0,D3DSAMP_MAGFILTER,D3DTEXF_LINEAR);
    device->SetSamplerState(0,D3DSAMP_ADDRESSU,D3DTADDRESS_CLAMP);device->SetSamplerState(0,D3DSAMP_ADDRESSV,D3DTADDRESS_CLAMP);
    const DWORD color=(DWORD(opacity*255.f)<<24)|0x00ffffff;
    struct Vertex {float x,y,z;DWORD color;float u,v;};
    for(const auto& q:quads){
        const auto& g=competitive::hit_art::glyphs[q.glyph];
        const float u=float(g.x)/competitive::hit_art::atlasWidth,v=float(g.y)/competitive::hit_art::atlasHeight;
        const float u2=float(g.x+g.width)/competitive::hit_art::atlasWidth,v2=float(g.y+g.height)/competitive::hit_art::atlasHeight;
        const float z=competitive::hit_art::depth;
        Vertex vertices[]={{q.left,q.top,z,color,u,v},{q.right,q.top,z,color,u2,v},
                           {q.left,q.bottom,z,color,u,v2},{q.right,q.bottom,z,color,u2,v2}};
        device->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP,2,vertices,sizeof(Vertex));
    }
    state->Apply();state->Release();
}