#!/usr/bin/env python3
"""Compatibility entry point; prefer ../play.sh or ../launch.py.

Preserves this developer wrapper's historical practice default. The public
launcher defaults to login/signup and has no VS Code/Flatpak requirement.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launch import main, LauncherError
import subprocess

if __name__=='__main__':
    args=sys.argv[1:]
    if '--login' not in args and '--practice' not in args:
        args=['--practice',*args]
    try:
        raise SystemExit(main(args))
    except (LauncherError,OSError,subprocess.TimeoutExpired) as error:
        print('GunZ:',error,file=sys.stderr)
        raise SystemExit(1)