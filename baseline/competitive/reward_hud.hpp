#pragma once
#include "reward_layout.hpp"

// Same D3D screen-effect projection as the original mesh pass. No Mint text,
// progression variables, kill hooks, sound triggers, or balance mutation.
inline void DrawCompetitiveGBucks(IDirect3DDevice9* device, IDirect3DTexture9* texture,
                                 int width, int height, bool interfaceFix,
                                 int amount, bool completion, std::uint64_t elapsed) {
    if (!device || !texture || width <= 0 || height <= 0) return;
    const auto quads = competitive::rewardLayout(amount, completion, elapsed);
    const float opacity = competitive::rewardOpacity(elapsed);
    if (quads.empty() || opacity <= 0) return;
    IDirect3DStateBlock9* state = nullptr;
    if (FAILED(device->CreateStateBlock(D3DSBT_ALL, &state))) return;
    if (FAILED(state->Capture())) { state->Release(); return; }
    // D3DSBT_ALL does not promise transform capture on every implementation.
    D3DMATRIX savedWorld, savedView, savedProjection;
    device->GetTransform(D3DTS_WORLD, &savedWorld);
    device->GetTransform(D3DTS_VIEW, &savedView);
    device->GetTransform(D3DTS_PROJECTION, &savedProjection);
    auto view = ViewMatrix(rvector(0, 0, -650), rvector(0, 0, 1), rvector(0, 1, 0));
    float fov = ToRadian(70);
    const float aspect = float(width) / height;
    if (interfaceFix) fov = 2.f * atan(tan(fov / 2.f) / (4.f / 3.f) * aspect);
    else view = ScalingMatrix({1, (4.f / 3.f) / aspect, 1, 1}) * view;
    const auto projection = PerspectiveProjectionMatrixViewport(width, height, fov, 5, 10000);
    const auto world = GetIdentityMatrix();
    device->SetTransform(D3DTS_WORLD, static_cast<const D3DMATRIX*>(world));
    device->SetTransform(D3DTS_VIEW, static_cast<const D3DMATRIX*>(view));
    device->SetTransform(D3DTS_PROJECTION, static_cast<const D3DMATRIX*>(projection));
    device->SetVertexShader(nullptr); device->SetPixelShader(nullptr);
    device->SetFVF(D3DFVF_XYZ | D3DFVF_DIFFUSE | D3DFVF_TEX1);
    device->SetRenderState(D3DRS_ZENABLE, FALSE); device->SetRenderState(D3DRS_ZWRITEENABLE, FALSE);
    device->SetRenderState(D3DRS_LIGHTING, FALSE); device->SetRenderState(D3DRS_FOGENABLE, FALSE);
    device->SetRenderState(D3DRS_CULLMODE, D3DCULL_NONE); device->SetRenderState(D3DRS_ALPHATESTENABLE, FALSE);
    device->SetRenderState(D3DRS_SCISSORTESTENABLE, FALSE); device->SetRenderState(D3DRS_STENCILENABLE, FALSE);
    device->SetRenderState(D3DRS_COLORWRITEENABLE, 0xf); device->SetRenderState(D3DRS_FILLMODE, D3DFILL_SOLID);
    device->SetRenderState(D3DRS_SEPARATEALPHABLENDENABLE, FALSE);
    device->SetRenderState(D3DRS_ALPHABLENDENABLE, TRUE); device->SetRenderState(D3DRS_BLENDOP, D3DBLENDOP_ADD);
    device->SetRenderState(D3DRS_SRCBLEND, D3DBLEND_SRCALPHA); device->SetRenderState(D3DRS_DESTBLEND, D3DBLEND_INVSRCALPHA);
    device->SetTexture(0, texture);
    device->SetTextureStageState(0, D3DTSS_COLOROP, D3DTOP_MODULATE);
    device->SetTextureStageState(0, D3DTSS_COLORARG1, D3DTA_TEXTURE); device->SetTextureStageState(0, D3DTSS_COLORARG2, D3DTA_DIFFUSE);
    device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_MODULATE);
    device->SetTextureStageState(0, D3DTSS_ALPHAARG1, D3DTA_TEXTURE); device->SetTextureStageState(0, D3DTSS_ALPHAARG2, D3DTA_DIFFUSE);
    device->SetTextureStageState(0, D3DTSS_TEXCOORDINDEX, 0); device->SetTextureStageState(0, D3DTSS_TEXTURETRANSFORMFLAGS, D3DTTFF_DISABLE);
    device->SetTextureStageState(1, D3DTSS_COLOROP, D3DTOP_DISABLE); device->SetTextureStageState(1, D3DTSS_ALPHAOP, D3DTOP_DISABLE);
    device->SetSamplerState(0, D3DSAMP_MINFILTER, D3DTEXF_LINEAR); device->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_LINEAR);
    device->SetSamplerState(0, D3DSAMP_ADDRESSU, D3DTADDRESS_CLAMP); device->SetSamplerState(0, D3DSAMP_ADDRESSV, D3DTADDRESS_CLAMP);
    const DWORD color = (DWORD(opacity * 255.f) << 24) | 0x00ffffff;
    struct Vertex { float x, y, z; DWORD color; float u, v; };
    for (const auto& q : quads) {
        const auto& g = competitive::reward_art::glyphs[q.glyph];
        const float u = g.u / competitive::reward_art::atlasWidth, v = g.v / competitive::reward_art::atlasHeight;
        const float u2 = g.u2 / competitive::reward_art::atlasWidth, v2 = g.v2 / competitive::reward_art::atlasHeight;
        const float z = competitive::reward_art::depth;
        Vertex vertices[] = {{q.left, q.top, z, color, u, v}, {q.right, q.top, z, color, u2, v},
                             {q.left, q.bottom, z, color, u, v2}, {q.right, q.bottom, z, color, u2, v2}};
        device->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP, 2, vertices, sizeof(Vertex));
    }
    state->Apply(); state->Release();
    device->SetTransform(D3DTS_WORLD, &savedWorld);
    device->SetTransform(D3DTS_VIEW, &savedView);
    device->SetTransform(D3DTS_PROJECTION, &savedProjection);
}