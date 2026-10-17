#pragma once
#include <windows.h>
// Diagnostic formatting only; replaces the obsolete precompiled dxerr helper.
inline const char* WINAPI DXGetErrorStringA(HRESULT) {return "DirectX error";}
inline const char* WINAPI DXGetErrorDescriptionA(HRESULT) {return "See HRESULT in log";}
inline const char* WINAPI DXGetErrorString8A(HRESULT h) {return DXGetErrorStringA(h);}
#define DXGetErrorString DXGetErrorStringA
#define DXGetErrorDescription DXGetErrorDescriptionA
#define DXGetErrorString8 DXGetErrorString8A