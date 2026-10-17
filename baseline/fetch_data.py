#!/usr/bin/env python3
"""Fetch matching reference data only; never download DLLs/game executables."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPOS={"client":("open-gunz/ogz-client","6b370b78e39ae7a2a8c266aceb9086a867e3181b"),
       "server":("open-gunz/ogz-server","babf92e67c307d1f7b0103c65c88e883ef20afb6")}
ALLOWED={".ani",".dds",".elu",".wav",".tga",".xml",".mrs",".png",".jpg",".rs",".bsp",".col",".lm",".nav",".bmp",".ogg",".txt"}


def download(url,limit):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"GunZ-reference-data"}),timeout=90) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError("download size limit")
    return data


def main():
    records=[]
    for kind,(repo,rev) in REPOS.items():
        tree=json.loads(download(f"https://api.github.com/repos/{repo}/git/trees/{rev}?recursive=1",5_000_000))
        assert not tree["truncated"]
        selected=[]
        for item in tree["tree"]:
            if item["type"]!="blob" or item["mode"]!="100644":continue
            name=item["path"];path=Path(name)
            if path.suffix.lower() not in ALLOWED:continue
            if ".." in path.parts or path.is_absolute():raise ValueError("unsafe tree path")
            if kind=="client" and name.startswith("Maps/") and name.lower()!="maps/mansion.mrs":continue
            if kind=="client" and name.startswith("CUSTOM/"):continue
            if kind=="server" and path.name.lower() in ("server.xml",):continue
            selected.append(item)
        print(kind,len(selected),"data files",sum(i['size'] for i in selected),"bytes",flush=True)
        destination=ROOT/"build/reference-data"/kind
        def fetch(item):
            path=destination/item["path"]
            url=f"https://raw.githubusercontent.com/{repo}/{rev}/{urllib.parse.quote(item['path'])}"
            data=path.read_bytes() if path.is_file() else download(url,max(item["size"],1))
            blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            if blob!=item['sha'] or len(data)!=item['size']:raise ValueError("data hash mismatch: "+item['path'])
            if data.startswith((b'MZ',b'\x7fELF')):raise ValueError("executable rejected: "+item['path'])
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(data)
            return {"kind":kind,"path":item['path'],"revision":rev,"url":url,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
        with ThreadPoolExecutor(max_workers=12) as pool:
            for n,result in enumerate(pool.map(fetch,selected),1):
                records.append(result)
                if n%250==0:print(kind,n,"verified",flush=True)
    output=ROOT/"build/reference-data/provenance.json"
    output.write_text(json.dumps(records,indent=2)+"\n")
    print("Verified matching data; no downloaded executables/DLLs. Manifest:",output)


if __name__=="__main__":main()