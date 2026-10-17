#!/usr/bin/env python3
"""Enter throwaway local test credentials into the focused original-client UI.

The password is generated locally, never printed, and stored only in the ignored
runtime cache with mode 0600. This is not a user/production account.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

file=Path('/work/reference-runtime/test-account.json')
if file.exists():
    account=json.loads(file.read_text())
else:
    account={'username':'localtester','password':'Gz7'+secrets.token_hex(8),'email':'localtester@example.invalid'}
    fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:json.dump(account,output)
if not any(c.isupper() for c in account['password']):
    account['password']='Gz7'+secrets.token_hex(8)
    file.write_text(json.dumps(account))
window=subprocess.check_output(['xdotool','search','--name','^Open GunZ$'],text=True).splitlines()[0]
def field(x,y,text):
    subprocess.run(['xdotool','mousemove','--window',window,str(x),str(y),'click','1'],check=True)
    # Original Mint edit boxes do not implement Ctrl+A consistently.
    subprocess.run(['xdotool','key','--clearmodifiers','End'],check=True)
    subprocess.run(['xdotool','key','--clearmodifiers','--repeat','100','--repeat-delay','1','BackSpace'],check=True)
    subprocess.run(['xdotool','type','--clearmodifiers','--delay','30',text],check=True)
if sys.argv[1]=='register':
    field(650,362,account['username']);field(650,393,account['password']);field(650,421,account['email'])
    subprocess.run(['xdotool','mousemove','--window',window,'630','469','click','1'],check=True)
elif sys.argv[1]=='login':
    field(527,616,account['username']);field(650,616,account['password'])
    subprocess.run(['xdotool','mousemove','--window',window,'753','616','click','1'],check=True)
else:raise SystemExit('register or login required')
print('Submitted local test account through original client UI; password not displayed.')