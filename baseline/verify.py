#!/usr/bin/env python3
"""Verify unchanged engine files and exact feature patches without a game launch."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from competitive.patch_source import changes,FILES
from competitive.data import CONFIG,header

ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'build'
source=build/'reference-source/src'
stage=build/'reference-win32/source'
gameplay=['Gunz/ZMyCharacter.cpp','Gunz/ZCharacter.cpp','Gunz/ZModule_Movable.cpp',
          'Gunz/ZGameInput.cpp','Gunz/ZCamera.cpp',
          'RealSpace2/Source/RVisualMesh.cpp','RealSpace2/Source/RSolidBsp.cpp']
records={}
for name in gameplay:
    original=(source/name).read_bytes().replace(b'\r\n',b'\n')
    compiled=(stage/name).read_bytes().replace(b'\r\n',b'\n')
    if original!=compiled:raise SystemExit('Gameplay source changed: '+name)
    records[name]=hashlib.sha256(original).hexdigest()
patches={}
for name in FILES:
    original=(source/name).read_bytes().decode('latin1').replace('\r\n','\n')
    expected=changes(name,original).encode('latin1')
    compiled=(stage/name).read_bytes().replace(b'\r\n',b'\n')
    if compiled!=expected:raise SystemExit('Unexpected changes beyond reviewed feature patches: '+name)
    patches[name]={'original_sha256':hashlib.sha256(original.encode('latin1')).hexdigest(),
                   'compiled_sha256':hashlib.sha256(compiled).hexdigest()}
if (build/'reference-win32/competitive_config.hpp').read_text()!=header(build/'reference-data'):
    raise SystemExit('Generated equipment configuration does not match validated source data')
items={item.get('id'):item for item in ET.parse(build/'reference-data/client/system/zitem.xml').getroot()}
for item_id in (CONFIG['primary'],CONFIG['secondary']):
    item=items[str(item_id)]
    if item.get('weapon')!='shotgun' or int(item.get('damage','0'))<=0:
        raise SystemExit('Starter weapon is not a standard damaging shotgun')
executables={}
for name in ('Gunz.exe','MatchServer.exe'):
    p=build/'reference-win32'/name
    data=p.read_bytes()
    if data[:2]!=b'MZ':raise SystemExit('Expected locally built Windows executable')
    executables[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
evidence={'gameplay_source_unchanged_sha256':records,'executables':executables,
          'exact_reviewed_patches':patches,'starter_config':CONFIG,
          'verification_scope':'Source/build evidence only. No live game, live database, visual HUD, or two-player Duel validation.'}
(build/'reference-win32/verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))