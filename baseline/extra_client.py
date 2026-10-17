#!/usr/bin/env python3
"""Another client in the existing container; never owns or stops the session."""
from pathlib import Path
import os
import socket
import subprocess
import sys


def main(work=Path('/work')):
    if os.environ.get('WINEPREFIX')!='/work/reference-home/game-wine':
        raise RuntimeError('Extra clients must use the running game session Wine prefix.')
    client=work/'reference-runtime/client/Gunz.exe'
    if not client.is_file():raise RuntimeError('The current session has no prepared client executable.')
    log=work/'reference-runtime/server-console.log'
    text=log.read_text(errors='replace') if log.exists() else ''
    if 'Match Server Created (Port:6000)' not in text or 'MMatchServer::Create failed' in text:
        raise RuntimeError('The existing server is not ready. Check its launcher terminal; nothing was restarted.')
    try:
        with socket.create_connection(('127.0.0.1',6000),timeout=2):pass
    except OSError as error:
        raise RuntimeError('The existing local server is not accepting connections; no extra client was opened.') from error
    # No runtime preparation, DB migration or wineserver cleanup. The original
    # runtime remains the session owner; closing this child only closes this child.
    return subprocess.call(['wine',str(client),'launch'],cwd=client.parent)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,RuntimeError) as error:
        print('GunZ extra client:',error,file=sys.stderr)
        raise SystemExit(1)