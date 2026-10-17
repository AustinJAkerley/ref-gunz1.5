#!/usr/bin/env python3
"""Container-only smoke: real XML loaders and MatchServer, no game or live DB.

Run in a disposable --network none container, compiler Wine prefix, with the build
cache mounted at /work and baseline mounted read-only at /baseline; no X11 mount.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from competitive.data import install_items
from runtime import wait_for_server


def main():
    if os.environ.get('WINEPREFIX')!='/work/reference-home/compiler-wine':
        raise RuntimeError('Refusing anything other than the isolated compiler Wine prefix')
    if os.environ.get('DISPLAY'):raise RuntimeError('Headless smoke test must not access the desktop')
    with tempfile.TemporaryDirectory(prefix='gunz-server-smoke-') as d:
        root=Path(d);shutil.copytree('/work/reference-data/server',root/'server')
        if (root/'server/GunzDB.sq3').exists():raise RuntimeError('Source data unexpectedly contains a database')
        install_items(Path('/work/reference-data'),root)
        shutil.copy2('/baseline/server.ini',root/'server/server.ini')
        integration='/work/reference-win32/CompetitiveIntegration.exe'
        subprocess.run(['wine',integration,'--xml-test','Z:'+str(root)],check=True)
        log=root/'server.log'
        with log.open('w') as output:
            server=subprocess.Popen(['wine','/work/reference-win32/MatchServer.exe'],cwd=root/'server',stdout=output,stderr=subprocess.STDOUT)
            try:
                wait_for_server(server,log)
                print('PASS: actual MatchServer completed startup and accepts TCP connections on 6000; scratch DB only',flush=True)
            finally:
                subprocess.run(['wineserver','-k'],check=False)
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()