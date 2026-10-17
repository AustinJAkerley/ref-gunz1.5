#!/usr/bin/env python3
"""Build-only HIT/digit atlas. Original HIT pixels; generated matching serif digits.

Requires Pillow and Liberation Serif Bold Italic (already in the toolchain image).
No downloaded font/game art is committed or required outside the existing cache.
"""
import argparse
from io import BytesIO
from pathlib import Path
import struct
from PIL import Image, ImageDraw, ImageFont


def hit_geometry(path):
    """Read the pinned single-quad ELU v5005, fail closed if its layout changes."""
    data=path.read_bytes()
    if struct.unpack_from('<4I',data)!=(0x0107f060,0x5005,1,1):
        raise ValueError('Unexpected HIT mesh format')
    node=16+8+48+8+80+8
    if data[node:node+40].split(b'\0')[0]!=b'hit':raise ValueError('Unexpected HIT node')
    matrix=struct.unpack_from('<16f',data,node+80)
    at=node+80+64+12+32+64
    count,=struct.unpack_from('<I',data,at);at+=4
    if count!=4:raise ValueError('HIT must be one quad')
    points=[struct.unpack_from('<3f',data,at+i*12) for i in range(4)];at+=48
    count,=struct.unpack_from('<I',data,at);at+=4
    if count!=2:raise ValueError('HIT must have two triangles')
    vertices={}
    for _ in range(count):
        face=struct.unpack_from('<3I9f2I',data,at);at+=56
        for i,index in enumerate(face[:3]):
            p=points[index]
            world=tuple(sum(p[k]*matrix[k*4+j] for k in range(3))+matrix[12+j] for j in range(3))
            vertices[index]=(face[3+i*3],face[4+i*3],world)
    low=min(vertices.values(),key=lambda v:v[0]);high=max(vertices.values(),key=lambda v:v[0])
    top=min(vertices.values(),key=lambda v:v[1]);bottom=max(vertices.values(),key=lambda v:v[1])
    sx=(high[2][0]-low[2][0])/(high[0]-low[0])
    sy=(bottom[2][1]-top[2][1])/(bottom[1]-top[1])
    if sx<=0 or sy>=0:raise ValueError('Unexpected HIT orientation')
    return (low[2][0]-low[0]*sx,top[2][1]-top[1]*sy,top[2][2],sx,sy)


def find_font():
    for root in (Path('/usr/share/fonts'),Path('/app/share/fonts')):
        matches=list(root.rglob('LiberationSerif-BoldItalic.ttf'))
        if matches:return matches[0]
    raise RuntimeError('Install fonts-liberation to generate the HIT numerals')


def make_art(data_root,font_path=None):
    directory=data_root/'client/Interface/default/combat'
    original=Image.open(directory/'hit.tga.dds').convert('RGBA')
    box=original.getchannel('A').getbbox()
    hit=original.crop(box)
    height=hit.height
    # Sample the actual HIT's yellow-to-orange gradient, excluding translucent edges.
    gradient=[]
    for y in range(box[1],box[3]):
        pixels=[original.getpixel((x,y))[:3] for x in range(box[0],box[2]) if original.getpixel((x,y))[3]>=240]
        if not pixels:
            pixels=[original.getpixel((x,y))[:3] for x in range(box[0],box[2]) if original.getpixel((x,y))[3]>0]
        if not pixels:raise ValueError('HIT gradient has an empty scanline')
        gradient.append(tuple(sorted(p[c] for p in pixels)[len(pixels)//2] for c in range(3)))
    font=ImageFont.truetype(str(font_path or find_font()),256)
    glyphs=[hit]
    for number in range(10):
        text=str(number);bounds=font.getbbox(text)
        mask=Image.new('L',(bounds[2]-bounds[0]+8,bounds[3]-bounds[1]+8))
        ImageDraw.Draw(mask).text((4-bounds[0],4-bounds[1]),text,font=font,fill=255)
        mask=mask.crop(mask.getbbox())
        mask=mask.resize((round(mask.width*height/mask.height),height),Image.Resampling.LANCZOS)
        digit=Image.new('RGBA',mask.size)
        for y,color in enumerate(gradient):
            for x in range(mask.width):digit.putpixel((x,y),(*color,mask.getpixel((x,y))))
        glyphs.append(digit)
    atlas=Image.new('RGBA',(1024,64));rects=[];x=2
    for glyph in glyphs:
        if x+glyph.width+2>atlas.width:raise ValueError('HIT atlas overflow')
        atlas.paste(glyph,(x,2));rects.append((x,2,glyph.width,glyph.height));x+=glyph.width+4
    gx,gy,gz,sx,sy=hit_geometry(directory/'ef_hit.elu')
    geometry=(gx+sx*box[0]/original.width,gy+sy*box[1]/original.height,gz,
              sx/original.width,-sy/original.height)
    return atlas,rects,geometry


def header(data_root,font_path=None):
    atlas,rects,geometry=make_art(data_root,font_path)
    encoded=BytesIO();atlas.save(encoded,format='PNG');png=encoded.getvalue()
    values=',\n'.join(','.join(str(v) for v in png[i:i+32]) for i in range(0,len(png),32))
    return ('// Generated from pinned HIT artwork and Liberation Serif Bold Italic.\n#pragma once\n'
            'namespace competitive { namespace hit_art {\n'
            'struct Glyph {int x,y,width,height;};\n'
            'constexpr int atlasWidth=1024, atlasHeight=64;\n'
            'constexpr Glyph glyphs[]={'+','.join('{'+','.join(map(str,r))+'}' for r in rects)+'};\n'
            +'\n'.join('constexpr float '+name+'='+format(value,'.9f')+'f;' for name,value in zip(('left','top','depth','pixelX','pixelY'),geometry))
            +'\nconstexpr unsigned char png[]={\n'+values+'\n};\n}}\n')


def preview(data_root,path):
    atlas,rects,_=make_art(data_root)
    def row(amount):
        indices=[0]+[1+int(c) for c in str(amount)];width=sum(rects[i][2] for i in indices)+8+3*(len(indices)-2)
        image=Image.new('RGBA',(width,52));x=0
        for position,i in enumerate(indices):
            gx,gy,w,h=rects[i];image.alpha_composite(atlas.crop((gx,gy,gx+w,gy+h)),(x,0));x+=w+(8 if position==0 else 3)
        return image
    rows=[row(n) for n in (43,7,108,10000)]
    canvas=Image.new('RGBA',(max(i.width for i in rows)+40,4*82+20),(24,32,46,255))
    for i,image in enumerate(rows):canvas.alpha_composite(image,(20,20+82*i))
    canvas.convert('RGB').save(path)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--header',type=Path);parser.add_argument('--preview',type=Path);args=parser.parse_args()
    if args.header:args.header.write_text(header(args.data))
    if args.preview:preview(args.data,args.preview)