#!/usr/bin/env python3
"""Record source-preservation, actual runtime and dependency evidence."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'build'
source=build/'reference-source/src'
stage=build/'reference-win32/source'
gameplay=['Gunz/ZMyCharacter.cpp','Gunz/ZCharacter.cpp','Gunz/ZModule_Movable.cpp',
          'Gunz/ZGameInput.cpp','Gunz/ZGame.cpp','Gunz/ZCamera.cpp',
          'RealSpace2/Source/RVisualMesh.cpp','RealSpace2/Source/RSolidBsp.cpp']
records={}
for name in gameplay:
    original=(source/name).read_bytes().replace(b'\r\n',b'\n')
    compiled=(stage/name).read_bytes().replace(b'\r\n',b'\n')
    if original!=compiled:raise SystemExit('Gameplay source changed: '+name)
    records[name]=hashlib.sha256(original).hexdigest()
practice_name='Gunz/ZTestGame.cpp'
practice_original=(source/practice_name).read_bytes().replace(b'\r\n',b'\n')
practice_expected=practice_original
practice_items={'MMCIP_PRIMARY':(6001,6002),'MMCIP_SECONDARY':(8003,6004)}
for slot,(old,new) in practice_items.items():
    before=f'info.nEquipedItemDesc[{slot}] = {old};'.encode()
    if practice_expected.count(before)!=1:raise SystemExit('Unexpected upstream practice loadout: '+slot)
    practice_expected=practice_expected.replace(before,f'info.nEquipedItemDesc[{slot}] = {new};'.encode())
if (stage/practice_name).read_bytes().replace(b'\r\n',b'\n')!=practice_expected:
    raise SystemExit('Practice harness changed beyond the two requested weapon slots')
for data_dir in ('reference-data','reference-runtime'):
    items={item.get('id'):item for item in ET.parse(build/data_dir/'client/system/zitem.xml').getroot()}
    for _,item_id in practice_items.values():
        item=items[str(item_id)]
        if item.get('weapon')!='shotgun' or int(item.get('damage','0'))<=0:
            raise SystemExit('Practice weapon is not a standard damaging shotgun')
executables={}
for name in ('Gunz.exe','MatchServer.exe'):
    p=build/'reference-win32'/name
    data=p.read_bytes()
    if data[:2]!=b'MZ':raise SystemExit('Expected locally built Windows executable')
    executables[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
logs=list((build/'reference-home/game-wine/drive_c/users').glob('*/Documents/Open GunZ/Logs/*'))
text='\n'.join(p.read_text(errors='replace') for p in logs)
serverlog=(build/'reference-runtime/server-console.log').read_text(errors='replace')
evidence={'gameplay_source_unchanged_sha256':records,'executables':executables,
          'practice_loadout':{'primary':6002,'secondary':6004,'sword_preserved':True,'only_two_slot_changes':True},
          'game_created_in_original_client':'ZGame Created' in text,
          'original_login_succeeded':'Login Successful.' in text,
          'real_matchserver_started':'Match Server Created (Port:6000)' in serverlog}
db=build/'reference-runtime/server/GunzDB.sq3'
if db.exists():
    with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as connection:
        evidence['accounts']=connection.execute('SELECT count(*) FROM Account').fetchone()[0]
        evidence['hashed_logins']=connection.execute('SELECT count(*) FROM Login WHERE length(PasswordData)>20').fetchone()[0]
        evidence['characters']=connection.execute('SELECT count(*) FROM Character').fetchone()[0]
for flag in ('game_created_in_original_client','original_login_succeeded','real_matchserver_started'):
    if not evidence[flag]:raise SystemExit('Missing evidence: '+flag)
(build/'reference-runtime/verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))