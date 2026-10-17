#include <windows.h>
// Source-only replacement for obsolete diagnostics; no rendering behavior change.
extern "C" const char* WINAPI DXGetErrorStringA(HRESULT) {return "DirectX HRESULT (see log)";}
extern "C" const char* WINAPI DXGetErrorDescriptionA(HRESULT) {return "DirectX operation failed";}