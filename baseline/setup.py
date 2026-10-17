#!/usr/bin/env python3
"""Prepare pinned real-game source, local compiler cache and matching data.

Explicit Microsoft license acceptance is required for a fresh SDK install.
This host uses Flatpak VS Code and Docker; no root host packages are installed.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run(*args):subprocess.run(args,check=True)


def checkout(spec,directory):
    if not (directory/'.git').is_dir():
        run('git','-c','core.hooksPath=/dev/null','clone','--no-checkout',spec['repository'],str(directory))
    current=subprocess.run(['git','-C',str(directory),'rev-parse','HEAD'],capture_output=True,text=True)
    if current.returncode==0 and current.stdout.strip()!=spec['revision']:
        dirty=subprocess.check_output(['git','-C',str(directory),'status','--porcelain'],text=True)
        if dirty:raise RuntimeError(f'Refusing to overwrite modified source: {directory}')
    run('git','-C',str(directory),'-c','core.hooksPath=/dev/null','-c','filter.lfs.smudge=',
        '-c','filter.lfs.process=','-c','filter.lfs.required=false','checkout','--detach',spec['revision'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accept-msvc-license',action='store_true')
    args=parser.parse_args()
    lock=json.loads((ROOT/'baseline/sources.json').read_text())
    build=ROOT/'build';build.mkdir(exist_ok=True)
    checkout(lock['game'],build/'reference-source')
    checkout(lock['toolchain_scripts'],build/'msvc-wine')
    run('flatpak-spawn','--host','docker','build','-t','gunz-baseline-toolchain:local',
        '-f',str(ROOT/'baseline/Toolchain.Dockerfile'),str(ROOT/'baseline'))
    for folder in ('reference-win32','reference-home'):(build/folder).mkdir(exist_ok=True)
    container=['flatpak-spawn','--host','docker','run','--rm','--user','1000:1000',
               '--mount',f'type=bind,source={build},target=/work','gunz-baseline-toolchain:local']
    if not (build/'msvc/bin/x86/cl').exists():
        if not args.accept_msvc_license:
            parser.error('Fresh Microsoft SDK install requires --accept-msvc-license after reviewing the license linked in baseline/README.md')
        run(*container,'python3','/work/msvc-wine/vsdownload.py','--major','17','--architecture','x86',
            '--host-arch','x64','--with-asan','no','--with-atl','no','--with-dia','no','--with-msbuild','no',
            '--accept-license','--dest','/work/msvc','--cache','/work/msvc-downloads')
        run('flatpak-spawn','--host','docker','run','--rm','--user','1000:1000',
            '--mount',f'type=bind,source={build},target=/work','--workdir','/work/msvc-wine',
            'gunz-baseline-toolchain:local','./install.sh','/work/msvc')
    run(sys.executable,str(ROOT/'baseline/fetch_data.py'))
    run(sys.executable,str(ROOT/'baseline/build.py'),'--configure')
    run(sys.executable,str(ROOT/'baseline/build.py'))


if __name__=='__main__':main()