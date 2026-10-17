// Pure queue/layout tests also build natively. On Windows the same target tests
// the actual GDI+ PNG decoder and D3D9 draw/readback in a hidden Xvfb window.
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <utility>
#include "reward_layout.hpp"

inline competitive::GBucksRewardQueue& CompetitiveGBucksPopup() {
    static competitive::GBucksRewardQueue value;
    return value;
}
static void check(bool value, const char* why) { if (!value) throw std::runtime_error(why); }

static void testState() {
    using namespace competitive;
    ClearCompetitiveGBucksRewards();
    check(!CurrentCompetitiveGBucksReward(0), "no speculative award");
    for (int n : {INT_MIN, -1, 0, 1, 9, 21, INT_MAX})
        check(!AddCompetitiveGBucksReward(n, false, 0), "kill amount requires server range 10..20");
    for (int n : {INT_MIN, -1, 0})
        check(!AddCompetitiveGBucksReward(n, true, 0), "completion must be positive");
    check(AddCompetitiveGBucksReward(15, false, 100), "server kill notice");
    check(AddCompetitiveGBucksReward(1, true, 101), "positive completion notice");
    check(AddCompetitiveGBucksReward(INT_MAX, true, 102), "positive int completion is representable");
    auto* current = CurrentCompetitiveGBucksReward(1099);
    check(current && current->amount == 15 && !current->completion && current->at == 100, "first notice holds independently");
    current = CurrentCompetitiveGBucksReward(1100);
    check(current && current->amount == 1 && current->completion && current->at == 1100, "FIFO advances at exact expiry");
    current = CurrentCompetitiveGBucksReward(2100);
    check(current && current->amount == INT_MAX && current->at == 2100, "no aggregation or amount recomputation");
    check(!CurrentCompetitiveGBucksReward(3100), "final notice expires");
    check(AddCompetitiveGBucksReward(10, false, 5000), "new notice after gap");
    check(!CurrentCompetitiveGBucksReward(4999), "future notice is not visible on clock rollback");
    ClearCompetitiveGBucksRewards();
    check(!CurrentCompetitiveGBucksReward(5000), "disconnect/stage clear removes presentation");
    for (std::size_t i = 0; i < GBucksRewardQueue::capacity; ++i)
        check(AddCompetitiveGBucksReward(10, false, 0), "bounded burst enqueue");
    check(!AddCompetitiveGBucksReward(20, false, 0), "burst overflow is bounded");
    check(!CurrentCompetitiveGBucksReward(100000), "hidden/paused frames do not resurrect stale queue");
    check(!AddCompetitiveGBucksReward(10, false, UINT64_MAX), "clock overflow fails closed");
    check(AddCompetitiveGBucksReward(10, false, 0), "timestamp zero is valid");
    ClearCompetitiveGBucksRewards();
}

static void testLayout() {
    using namespace competitive;
    for (int amount : {10, 15, 20, 1, 150, INT_MAX}) {
        const bool completion = amount < 10 || amount > 20;
        auto q = rewardLayout(amount, completion, 100);
        check(q.size() >= 3 && q[0].glyph == reward_art::labelGlyph && q[1].glyph == reward_art::plusGlyph, "GBucks plus prefix");
        check(std::abs(q[0].left - reward_art::left) < .001f, "original popup region");
        for (std::size_t i = 0; i < q.size(); ++i) {
            check(q[i].right > q[i].left && q[i].top > q[i].bottom, "positive glyph geometry");
            if (i) check(q[i].left > q[i - 1].right, "resting glyphs do not overlap");
        }
        check(q.back().right < 400, "completion amount fits original 800-wide screen");
        auto grown = rewardLayout(amount, completion, 950);
        check(std::abs((grown[0].right - grown[0].left) - (q[0].right - q[0].left)) < .001f, "label holds like original plus");
        check(grown[2].right - grown[2].left > q[2].right - q[2].left, "original digit pop on exit");
    }
    auto q = rewardLayout(15, false, 100);
    check(q.size() == 4 && q[2].glyph == 1 && q[3].glyph == 5, "actual blue 15 digit order");
    check(rewardLayout(9, false, 100).empty() && rewardLayout(21, false, 100).empty() &&
          rewardLayout(0, true, 100).empty() && rewardLayout(10, false, 1000).empty(), "invalid/expired layout suppressed");
    check(rewardOpacity(0) == 0 && rewardOpacity(67) == 1 && rewardOpacity(833) == 1 &&
          rewardOpacity(900) > 0 && rewardOpacity(900) < 1 && rewardOpacity(1000) == 0, "original fade keys");
    check(rewardScale(833) == 1 && std::abs(rewardScale(900) - 1.8f) < .001f, "original stepped scale keys");
    puts("PASS: GBucks server-notice queue, validation, FIFO, expiry, clear, original geometry/motion");
}

#ifdef _WIN32
#include <windows.h>
#include <d3d9.h>
#include <objidl.h>
#include <gdiplus.h>
#include "MUtil.h"
#include "RMath.h"
using namespace RealSpace2;
#include "reward_hud.hpp"

static void testD3D() {
    using namespace competitive;
    Gdiplus::GdiplusStartupInput startup;
    ULONG_PTR token = 0;
    check(Gdiplus::GdiplusStartup(&token, &startup, nullptr) == Gdiplus::Ok, "GDI+ startup");
    HGLOBAL buffer = GlobalAlloc(GMEM_MOVEABLE, sizeof(reward_art::png));
    check(buffer != nullptr, "PNG memory");
    void* bytes = GlobalLock(buffer); check(bytes != nullptr, "lock PNG memory");
    memcpy(bytes, reward_art::png, sizeof(reward_art::png)); GlobalUnlock(buffer);
    IStream* stream = nullptr;
    check(SUCCEEDED(CreateStreamOnHGlobal(buffer, TRUE, &stream)), "PNG stream");
    auto* image = Gdiplus::Bitmap::FromStream(stream);
    const int aw = reward_art::atlasWidth, ah = reward_art::atlasHeight;
    check(image && image->GetLastStatus() == Gdiplus::Ok && image->GetWidth() == aw && image->GetHeight() == ah, "decode embedded reward atlas");
    HWND window = CreateWindowA("STATIC", "GBucks isolated render test", WS_POPUP, 0, 0, 1920, 1080,
                                nullptr, nullptr, GetModuleHandle(nullptr), nullptr);
    check(window != nullptr, "hidden test window");
    auto* d3d = Direct3DCreate9(D3D_SDK_VERSION); check(d3d != nullptr, "D3D9 interface");
    for (const auto size : {std::pair<int, int>{800, 600}, {1280, 800}, {1920, 1080}}) {
        const int width = size.first, height = size.second;
        D3DPRESENT_PARAMETERS pp{};
        pp.Windowed = TRUE; pp.SwapEffect = D3DSWAPEFFECT_DISCARD; pp.hDeviceWindow = window;
        pp.BackBufferWidth = width; pp.BackBufferHeight = height; pp.BackBufferFormat = D3DFMT_X8R8G8B8;
        IDirect3DDevice9* device = nullptr;
        check(SUCCEEDED(d3d->CreateDevice(0, D3DDEVTYPE_HAL, window, D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &device)), "D3D test device");
        IDirect3DTexture9* texture = nullptr;
        check(SUCCEEDED(device->CreateTexture(aw, ah, 1, 0, D3DFMT_A8R8G8B8, D3DPOOL_MANAGED, &texture, nullptr)), "reward texture");
        Gdiplus::BitmapData pixels; Gdiplus::Rect rect(0, 0, aw, ah);
        check(image->LockBits(&rect, Gdiplus::ImageLockModeRead, PixelFormat32bppARGB, &pixels) == Gdiplus::Ok, "atlas read");
        D3DLOCKED_RECT target{};
        check(SUCCEEDED(texture->LockRect(0, &target, nullptr, 0)), "texture lock");
        for (int y = 0; y < ah; ++y)
            memcpy(static_cast<char*>(target.pBits) + y * target.Pitch, static_cast<char*>(pixels.Scan0) + y * pixels.Stride, aw * 4);
        texture->UnlockRect(0); image->UnlockBits(&pixels);
        for (bool fix : {false, true}) for (int amount : {10, 15, 20, 150, INT_MAX}) for (unsigned elapsed : {0u, 100u, 900u, 1000u}) {
            device->SetRenderState(D3DRS_SCISSORTESTENABLE, FALSE);
            check(SUCCEEDED(device->Clear(0, nullptr, D3DCLEAR_TARGET, 0xff000000, 1, 0)), "clear readback target");
            // Hostile prior HUD state must not crop/fill/occlude the reward.
            device->SetRenderState(D3DRS_SCISSORTESTENABLE, TRUE);
            device->SetRenderState(D3DRS_COLORWRITEENABLE, 0);
            device->SetRenderState(D3DRS_FILLMODE, D3DFILL_WIREFRAME);
            RECT clip{0, 0, 1, 1}; device->SetScissorRect(&clip);
            D3DMATRIX transform{}; transform._11 = 2; transform._22 = 3; transform._33 = transform._44 = 1;
            device->SetTransform(D3DTS_WORLD, &transform);
            device->SetTransform(D3DTS_VIEW, &transform);
            device->SetTransform(D3DTS_PROJECTION, &transform);
            check(SUCCEEDED(device->BeginScene()), "begin reward render");
            DrawCompetitiveGBucks(device, texture, width, height, fix, amount, amount > 20, elapsed);
            check(SUCCEEDED(device->EndScene()), "end reward render");
            DWORD restored = 0;
            device->GetRenderState(D3DRS_SCISSORTESTENABLE, &restored); check(restored == TRUE, "restore scissor");
            device->GetRenderState(D3DRS_COLORWRITEENABLE, &restored); check(restored == 0, "restore color write");
            device->GetRenderState(D3DRS_FILLMODE, &restored); check(restored == D3DFILL_WIREFRAME, "restore fill mode");
            for (auto kind : {D3DTS_WORLD, D3DTS_VIEW, D3DTS_PROJECTION}) {
                D3DMATRIX value{}; device->GetTransform(kind, &value);
                check(memcmp(&value, &transform, sizeof(value)) == 0, "restore transforms");
            }
            IDirect3DSurface9 *back = nullptr, *copy = nullptr;
            check(SUCCEEDED(device->GetRenderTarget(0, &back)), "render target");
            check(SUCCEEDED(device->CreateOffscreenPlainSurface(width, height, D3DFMT_X8R8G8B8, D3DPOOL_SYSTEMMEM, &copy, nullptr)), "readback surface");
            check(SUCCEEDED(device->GetRenderTargetData(back, copy)), "D3D readback");
            D3DLOCKED_RECT output{}; check(SUCCEEDED(copy->LockRect(&output, nullptr, D3DLOCK_READONLY)), "readback pixels");
            int left = width, right = 0, top = height, bottom = 0, lit = 0, blue = 0;
            for (int y = 0; y < height; ++y) {
                auto* row = reinterpret_cast<unsigned*>(static_cast<char*>(output.pBits) + y * output.Pitch);
                for (int x = 0; x < width; ++x) if (row[x] & 0x00ffffff) {
                    ++lit; left = (std::min)(left, x); right = (std::max)(right, x);
                    top = (std::min)(top, y); bottom = (std::max)(bottom, y);
                    if ((row[x] & 255) > ((row[x] >> 16) & 255) + 30) ++blue;
                }
            }
            if (elapsed == 0 || elapsed == 1000) check(lit == 0, "no pixels outside original lifetime");
            else {
                check(lit > 100 && blue > 50, "visible blue GBucks reward");
                check(left > 0 && left < width / 3 && top > 0 && bottom < height / 2 && right < width - 2, "original upper-left region, all amounts fit");
            }
            copy->UnlockRect(); copy->Release(); back->Release();
        }
        printf("PASS: GBucks D3D %dx%d, both InterfaceFix modes, five amounts, fade/growth/expiry, state restored\n", width, height);
        texture->Release(); device->Release();
    }
    delete image; stream->Release(); d3d->Release(); DestroyWindow(window); Gdiplus::GdiplusShutdown(token);
}
#endif

int main() try {
    testState(); testLayout();
#ifdef _WIN32
    testD3D();
#endif
    return 0;
} catch (const std::exception& e) { fprintf(stderr, "FAIL: %s\n", e.what()); return 1; }