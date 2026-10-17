#!/usr/bin/env python3
"""Run the real Windows baseline in isolated Wine, not the native experiment."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
command=['flatpak-spawn','--host','docker','run','--rm','--name','gunz-reference-session',
         '--user','1000:1000','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges',
         '--env','HOME=/work/reference-home','--env','WINEPREFIX=/work/reference-home/game-wine',
         '--env','WINEDEBUG=-all','--env','DISPLAY=:1','--env','LIBGL_ALWAYS_SOFTWARE=1',
         '--mount',f'type=bind,source={ROOT}/build,target=/work',
         '--mount',f'type=bind,source={ROOT}/baseline,target=/baseline,readonly',
         '--mount','type=bind,source=/tmp/.X11-unix,target=/tmp/.X11-unix,readonly',
         'gunz-baseline-toolchain:local','python3','/baseline/runtime.py',*sys.argv[1:]]
raise SystemExit(subprocess.call(command))