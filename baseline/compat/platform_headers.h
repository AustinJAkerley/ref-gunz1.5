#pragma once
#ifdef __cplusplus
// Establish the same Win32 macro hygiene as upstream before standalone headers.
#include <winsock2.h>
#undef CreateEvent
#undef GetMessage
#endif