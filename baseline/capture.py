#!/usr/bin/env python3
"""Capture only the Open GunZ X11 window (no whole desktop screenshot)."""
from pathlib import Path
from Xlib import X, display
from PIL import Image

d=display.Display()
def windows(parent):
    for window in parent.query_tree().children:
        yield window
        yield from windows(window)

for w in windows(d.screen().root):
    try:
        if w.get_wm_name()!='Open GunZ':continue
        geometry=w.get_geometry()
        image=w.get_image(0,0,geometry.width,geometry.height,X.ZPixmap,0xffffffff)
        output=Path('/work/reference-runtime/reference.png')
        Image.frombytes('RGB',(geometry.width,geometry.height),image.data,'raw','BGRX').save(output)
        print('Captured real Open GunZ window:',output,hex(w.id),geometry.width,geometry.height)
        break
    except Exception as e:print(type(e).__name__,str(e))
else:raise SystemExit('Open GunZ window not found')