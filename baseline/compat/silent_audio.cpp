// Source-built null audio ABI for the reference build. No FMOD implementation
// or proprietary runtime is used; gameplay/controller code is unchanged.
#include "fmod.h"
extern "C" {
float F_API FSOUND_GetVersion(){return FMOD_VERSION;}
signed char F_API FSOUND_Init(int,int,unsigned int){return 1;}
void F_API FSOUND_Close(){}
void F_API FSOUND_Update(){}
int F_API FSOUND_GetError(){return 0;}
int F_API FSOUND_GetNumDrivers(){return 1;}
const char* F_API FSOUND_GetDriverName(int){return "Silent source baseline";}
signed char F_API FSOUND_GetDriverCaps(int,unsigned int* caps){if(caps)*caps=0;return 1;}
int F_API FSOUND_GetMaxChannels(){return 32;}
int F_API FSOUND_GetChannelsPlaying(){return 0;}
signed char F_API FSOUND_SetOutput(int){return 1;}
signed char F_API FSOUND_SetDriver(int){return 1;}
signed char F_API FSOUND_SetHWND(void*){return 1;}
signed char F_API FSOUND_SetMinHardwareChannels(int){return 1;}
signed char F_API FSOUND_SetMaxHardwareChannels(int){return 1;}
signed char F_API FSOUND_SetVolume(int,int){return 1;}
int F_API FSOUND_GetVolume(int){return 0;}
signed char F_API FSOUND_SetPaused(int,signed char){return 1;}
signed char F_API FSOUND_SetMute(int,signed char){return 1;}
signed char F_API FSOUND_SetPan(int,int){return 1;}
signed char F_API FSOUND_SetPriority(int,int){return 1;}
signed char F_API FSOUND_StopSound(int){return 1;}
signed char F_API FSOUND_IsPlaying(int){return 0;}
int F_API FSOUND_PlaySoundEx(int,FSOUND_SAMPLE*,FSOUND_DSPUNIT*,signed char){return -1;}
FSOUND_SAMPLE* F_API FSOUND_Sample_Load(int,const char*,unsigned int,int,int){return nullptr;}
void F_API FSOUND_Sample_Free(FSOUND_SAMPLE*){}
const char* F_API FSOUND_Sample_GetName(FSOUND_SAMPLE*){return "";}
unsigned int F_API FSOUND_Sample_GetMode(FSOUND_SAMPLE*){return 0;}
signed char F_API FSOUND_Sample_SetMode(FSOUND_SAMPLE*,unsigned int){return 1;}
signed char F_API FSOUND_Sample_SetMinMaxDistance(FSOUND_SAMPLE*,float,float){return 1;}
void F_API FSOUND_3D_Listener_SetAttributes(const float*,const float*,float,float,float,float,float,float){}
void F_API FSOUND_3D_SetDistanceFactor(float){}
void F_API FSOUND_3D_SetDopplerFactor(float){}
void F_API FSOUND_3D_SetRolloffFactor(float){}
signed char F_API FSOUND_3D_SetAttributes(int,const float*,const float*){return 1;}
signed char F_API FSOUND_3D_SetMinMaxDistance(int,float,float){return 1;}
FSOUND_STREAM* F_API FSOUND_Stream_Open(const char*,unsigned int,int,int){return nullptr;}
signed char F_API FSOUND_Stream_Close(FSOUND_STREAM*){return 1;}
signed char F_API FSOUND_Stream_Stop(FSOUND_STREAM*){return 1;}
signed char F_API FSOUND_Stream_SetBufferSize(int){return 1;}
signed char F_API FSOUND_Stream_SetMode(FSOUND_STREAM*,unsigned int){return 1;}
unsigned int F_API FSOUND_Stream_GetMode(FSOUND_STREAM*){return 0;}
FSOUND_SAMPLE* F_API FSOUND_Stream_GetSample(FSOUND_STREAM*){return nullptr;}
int F_API FSOUND_Stream_PlayEx(int,FSOUND_STREAM*,FSOUND_DSPUNIT*,signed char){return -1;}
signed char F_API FSOUND_Stream_SetEndCallback(FSOUND_STREAM*,FSOUND_STREAMCALLBACK,void*){return 1;}
}