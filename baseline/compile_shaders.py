#!/usr/bin/env python3
"""Regenerate D3D shader headers from upstream HLSL using the Microsoft SDK."""
from pathlib import Path
import os
import subprocess

root=Path('/work/reference-win32/source/RealSpace2')
sdk=Path('/work/msvc/Windows Kits/10/bin')
fxc=sorted(sdk.glob('*/x64/fxc.exe'))[-1]
jobs=[('skin','skin','main','vs_1_1'),('Deferred','DeferredVS','vs_main','vs_3_0'),
      ('Deferred','DeferredPS','ps_main','ps_3_0'),('Lighting','PointLightVS','vs_point_light','vs_3_0'),
      ('Lighting','PointLightPS','ps_point_light','ps_3_0'),('DepthCopy','DepthCopyVS','vs_main','vs_3_0'),
      ('DepthCopy','DepthCopyPS','ps_main','ps_3_0'),('VisualizeLinearDepth','VisualizeLinearDepth','main','ps_3_0'),
      ('Monochrome','Monochrome','main','ps_3_0'),('ColorInvert','ColorInvert','main','ps_3_0')]
env={**os.environ,'WINEDLLOVERRIDES':'d3dcompiler_47=n'}
for source,name,entry,profile in jobs:
    command=['wine',str(fxc),'/nologo','/O3','/T',profile,'/E',entry,'/Vn',name+'Data',
             '/Fh','Z:'+str(root/'Include'/f'{name}.h'), 'Z:'+str(root/'Source'/f'{source}.hlsl')]
    result=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    print(name,result.stdout.strip(),flush=True)
    if result.returncode:raise SystemExit(result.returncode)