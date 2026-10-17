#!/usr/bin/env python3
"""Container-internal real game session; only locally compiled game executables."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from competitive.data import install_items


def backup_before_competitive(database, backup_dir):
    """Back up only pre-migration databases; never launch a process here."""
    if not database.exists():return None
    with closing(sqlite3.connect(database)) as source:
        migrated=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='CompetitiveStarter'").fetchone()
        if migrated:return None
        backup_dir.mkdir(parents=True,exist_ok=True)
        backup=backup_dir/('pre-competitive-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sq3')
        with closing(sqlite3.connect(backup)) as target:source.backup(target)
        return backup


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--seconds",type=int,default=0)
    parser.add_argument("--login",action="store_true")
    args=parser.parse_args()
    work=Path('/work');runtime=work/'reference-runtime';runtime.mkdir(exist_ok=True)
    for kind,exe in [('client','Gunz.exe'),('server','MatchServer.exe')]:
        target=runtime/kind
        if not target.exists():shutil.copytree(work/'reference-data'/kind,target)
        shutil.copy2(work/'reference-win32'/exe,target/exe)
    shutil.copy2('/baseline/system.xml',runtime/'client/system/system.xml')
    shutil.copy2('/baseline/server.ini',runtime/'server/server.ini')
    # Match the client/server item overlay and take a one-time online-safe SQLite
    # backup before the new server performs its transactional startup migration.
    install_items(work/'reference-data',runtime)
    database=runtime/'server/GunzDB.sq3'
    backup=backup_before_competitive(database,runtime/'backups')
    if backup:print('Saved database backup:',backup,flush=True)
    env=os.environ.copy();prefix=Path(env['WINEPREFIX'])
    with (runtime/'wineboot.log').open('a') as log:
        if not (prefix/'system.reg').exists():
            subprocess.run(['wineboot','--init'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90,check=True)
    users=prefix/'drive_c/users'
    for user in users.iterdir():
        if user.name=='Public' or not user.is_dir():continue
        docs=user/'Documents'
        # Wine may point Documents to the container user's home. Keep all data local.
        if docs.is_symlink():docs.unlink()
        docs.mkdir(exist_ok=True)
        config=docs/'Open GunZ';config.mkdir(exist_ok=True)
        if not (config/'config.xml').exists():shutil.copy2('/baseline/config.xml',config/'config.xml')
    processes=[]
    with (runtime/'server-console.log').open('w') as serverlog,(runtime/'client-console.log').open('w') as clientlog:
        try:
            server=subprocess.Popen(['wine',str(runtime/'server/MatchServer.exe')],cwd=runtime/'server',env=env,stdout=serverlog,stderr=subprocess.STDOUT)
            processes.append(server)
            command=['wine',str(runtime/'client/Gunz.exe'),*(['launch'] if args.login else ['game','mansion'])]
            client=subprocess.Popen(command,cwd=runtime/'client',env=env,stdout=clientlog,stderr=subprocess.STDOUT)
            processes.append(client)
            print('Real GunZ reference launched; mode:', 'login' if args.login else 'original standalone Mansion',flush=True)
            try:
                code=client.wait(timeout=args.seconds if args.seconds else None)
                print('Client exited:',code,flush=True)
                if code!=0:raise RuntimeError(f'Real client exited with code {code}')
            except subprocess.TimeoutExpired:
                logs=list(users.glob('*/Documents/Open GunZ/Logs/*'))
                latest=max(logs,key=lambda p:p.stat().st_mtime)
                text=latest.read_text(errors='replace')
                marker='OnCreate() done' if args.login else 'ZGame Created'
                if marker not in text:raise RuntimeError('Client stayed open but did not complete initialization: '+str(latest))
                print('Timed validation complete; original client initialization verified.',flush=True)
            print('MatchServer status:',server.poll(),flush=True)
            if server.poll() is not None:raise RuntimeError('MatchServer stopped unexpectedly')
        finally:
            subprocess.run(['wineserver','-k'],env=env,check=False)
            for process in processes:
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()