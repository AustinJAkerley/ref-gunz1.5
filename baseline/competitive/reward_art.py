#!/usr/bin/env python3
"""Build-only GBucks art: original blue digits/plus, generated italic label.

The pinned v5007 ELU UVs/quad sizes and v1003 animation keys are read directly.
Only the word GBucks is typeset (Liberation Serif Bold Italic, sampled gradient).
Requires Pillow, like hit_art.py. No game artwork or fonts are committed.
"""
import argparse
from io import BytesIO
import math
from pathlib import Path
import struct

from PIL import Image, ImageDraw, ImageFont
from hit_art import find_font


def mesh(path, name):
    data = path.read_bytes()
    if struct.unpack_from('<4I', data) != (0x0107f060, 0x5007, 1, 1):
        raise ValueError('Unexpected reward mesh format: ' + str(path))
    # One material: IDs, three colors, power/submaterial count, two 256-byte
    # filenames, two-sided/additive/alpha-test flags. Then one named node.
    node = 16 + 8 + 48 + 8 + 512 + 12
    if data[80:336].split(b'\0')[0] != b'exp_num.tga':
        raise ValueError('Unexpected reward texture')
    if data[node:node + 40].split(b'\0')[0].decode('ascii') != name:
        raise ValueError('Unexpected reward node')
    matrix = struct.unpack_from('<16f', data, node + 80)
    if matrix[:12] != (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0):
        raise ValueError('Reward base must be translation only')
    at = node + 80 + 64 + 12 + 32 + 64
    count, = struct.unpack_from('<I', data, at)
    if count != 4:
        raise ValueError('Reward mesh must be a quad')
    at += 4
    points = [struct.unpack_from('<3f', data, at + i * 12) for i in range(4)]
    at += 48
    count, = struct.unpack_from('<I', data, at)
    if count != 2:
        raise ValueError('Reward mesh must have two triangles')
    vertices = {}
    for i in range(count):
        face = struct.unpack_from('<3I9f2I', data, at + 4 + i * 56)
        for j, index in enumerate(face[:3]):
            vertices[index] = (face[3 + j * 3], face[4 + j * 3], points[index])
    if len(vertices) != 4:
        raise ValueError('Incomplete reward quad')
    left = min(vertices.values(), key=lambda v: v[2][0])
    right = max(vertices.values(), key=lambda v: v[2][0])
    top = max(vertices.values(), key=lambda v: v[2][1])
    bottom = min(vertices.values(), key=lambda v: v[2][1])
    bounds = (left[2][0], top[2][1], right[2][0], bottom[2][1])
    uv = (min(v[0] for v in vertices.values()), min(v[1] for v in vertices.values()),
          max(v[0] for v in vertices.values()), max(v[1] for v in vertices.values()))
    if right[0] <= left[0] or bottom[1] <= top[1]:
        raise ValueError('Unexpected reward quad orientation')
    return bounds, uv, matrix


def animation(path, name, base):
    data = path.read_bytes()
    signature, version, frames, nodes, mode = struct.unpack_from('<5I', data)
    if (signature, version, frames, nodes) != (0x0107f060, 0x1003, 30, 1):
        raise ValueError('Unexpected reward animation')
    if data[20:60].split(b'\0')[0].decode('ascii') != name:
        raise ValueError('Unexpected animation node')
    at, keys = 60, []
    if mode == 3:
        count, = struct.unpack_from('<I', data, at)
        at += 4
        for i in range(count):
            *matrix, frame = struct.unpack_from('<16fI', data, at + 68 * i)
            scale = matrix[0]
            expected = list(base)
            for j in (0, 5, 10):
                expected[j] = scale
            if matrix != expected:
                raise ValueError('Reward animation is no longer uniform scale')
            keys.append((frame, scale))
        at += count * 68
    elif mode == 2:
        if struct.unpack_from('<16f', data, at) != base:
            raise ValueError('Unexpected static reward transform')
        at += 64
        if struct.unpack_from('<2I', data, at) != (0, 0):
            raise ValueError('Unexpected reward position/rotation keys')
        at += 8
    else:
        raise ValueError('Unsupported reward animation type')
    count, = struct.unpack_from('<I', data, at)
    at += 4
    visibility = [struct.unpack_from('<fI', data, at + 8 * i) for i in range(count)]
    if at + count * 8 != len(data) or not visibility or visibility[-1] != (0, 4800):
        raise ValueError('Unexpected reward animation duration')
    return keys, visibility


def make_art(data_root, font_path=None):
    directory = data_root / 'client/Interface/default/combat'
    original = Image.open(directory / 'exp_num.tga.dds').convert('RGBA')
    if original.size != (256, 64):
        raise ValueError('Unexpected blue number sheet size')
    atlas = Image.new('RGBA', (1024, 128))
    glyphs, rects, x, motion, fade = [], [], 2, None, None
    for suffix, name in [(f'num_{i}', f'exp_num_{i}') for i in range(10)] + [('+', 'exp +')]:
        bounds, uv, base = mesh(directory / f'ef_exp_{suffix}.elu', name)
        keys, visibility = animation(directory / f'ef_exp_{suffix}.elu.ani', name, base)
        if fade is not None and fade != visibility:
            raise ValueError('Reward glyph fades disagree')
        fade = visibility
        if keys:
            if motion is not None and motion != keys:
                raise ValueError('Reward digit motion differs')
            motion = keys
        # Keep the original pixels and fractional UVs, including transparent
        # padding; unlike generated numbers, these are the actual blue glyphs.
        box = (max(0, math.floor(uv[0] * 256)), max(0, math.floor(uv[1] * 64)),
               min(256, math.ceil(uv[2] * 256)), min(64, math.ceil(uv[3] * 64)))
        image = original.crop(box)
        atlas.paste(image, (x, 2))
        tex = (x + uv[0] * 256 - box[0], 2 + uv[1] * 64 - box[1],
               x + uv[2] * 256 - box[0], 2 + uv[3] * 64 - box[1])
        glyphs.append((*bounds, *tex))
        rects.append((x, 2, image.width, image.height))
        x += image.width + 4
        if suffix == 'num_0':
            anchor = base[12:15]
            sample = image
            pixel_scale = (bounds[1] - bounds[3]) / ((uv[3] - uv[1]) * 64)
        if suffix == '+':
            # Original two-digit popup's plus sign left edge, same baseline.
            left = base[12] + 30 + bounds[0]
            number_gap = anchor[0] - (base[12] + 30 + bounds[2])

    # Sample blue gradient from the real zero. Mix the upper highlight toward
    # silver for a readable metallic italic GBucks label, not another XP label.
    crop = sample.crop(sample.getchannel('A').getbbox())
    font = ImageFont.truetype(str(font_path or find_font()), 256)
    bounds = font.getbbox('GBucks')
    mask = Image.new('L', (bounds[2] - bounds[0] + 8, bounds[3] - bounds[1] + 8))
    ImageDraw.Draw(mask).text((4 - bounds[0], 4 - bounds[1]), 'GBucks', font=font, fill=255)
    mask = mask.crop(mask.getbbox())
    height = crop.height
    mask = mask.resize((round(mask.width * height / mask.height), height), Image.Resampling.LANCZOS)
    label = Image.new('RGBA', mask.size)
    for y in range(height):
        pixels = [crop.getpixel((px, y))[:3] for px in range(crop.width) if crop.getpixel((px, y))[3] >= 200]
        if not pixels:
            pixels = [crop.getpixel((px, y))[:3] for px in range(crop.width) if crop.getpixel((px, y))[3] > 0]
        color = tuple(sorted(p[c] for p in pixels)[len(pixels) // 2] for c in range(3))
        silver = .8 * (1 - y / max(1, height - 1))
        color = tuple(round(c * (1 - silver) + 240 * silver) for c in color)
        for px in range(mask.width):
            label.putpixel((px, y), (*color, mask.getpixel((px, y))))
    if x + label.width + 2 > atlas.width or label.height + 4 > atlas.height:
        raise ValueError('Reward atlas overflow')
    atlas.paste(label, (x, 2))
    h = height * pixel_scale
    glyphs.append((0, h / 2, mask.width * pixel_scale, -h / 2, x, 2, x + mask.width, 2 + height))
    rects.append((x, 2, mask.width, height))
    if not motion or motion[-1][0] != 4800:
        raise ValueError('Missing one-second original reward motion')
    return atlas, glyphs, rects, (left, anchor[1], anchor[2], number_gap), motion, fade


def header(data_root, font_path=None):
    atlas, glyphs, _, anchor, motion, fade = make_art(data_root, font_path)
    encoded = BytesIO()
    atlas.save(encoded, format='PNG')
    png = encoded.getvalue()
    def f(value):
        return format(value, '.9f') + 'f'
    return ('// Generated: original blue reward glyphs/ELU animation; typeset GBucks only.\n#pragma once\n'
            'namespace competitive { namespace reward_art {\n'
            'constexpr int atlasWidth=1024, atlasHeight=128, plusGlyph=10, labelGlyph=11;\n'
            'struct Glyph {float left,top,right,bottom,u,v,u2,v2;};\n'
            'constexpr Glyph glyphs[]={\n' + ',\n'.join('{' + ','.join(f(v) for v in g) + '}' for g in glyphs) + '\n};\n'
            + '\n'.join('constexpr float ' + name + '=' + f(value) + ';' for name, value in zip(('left', 'baseline', 'depth', 'numberGap'), anchor))
            + '\n// Original playback is 4.8 animation ticks per millisecond.\n'
            'constexpr float ticksPerMS=4.8f;\nconstexpr unsigned durationMS=1000;\n'
            'struct Key {unsigned frame;float value;};\n'
            'constexpr Key scaleKeys[]={' + ','.join('{' + str(frame) + ',' + f(v) + '}' for frame, v in motion) + '};\n'
            'constexpr Key opacityKeys[]={' + ','.join('{' + str(frame) + ',' + f(v) + '}' for v, frame in fade) + '};\n'
            'constexpr unsigned char png[]={\n' + ',\n'.join(','.join(str(v) for v in png[i:i + 32]) for i in range(0, len(png), 32)) + '\n};\n}}\n')


def preview(data_root, path, font_path=None):
    atlas, _, rects, _, _, _ = make_art(data_root, font_path)
    canvas = Image.new('RGBA', (620, 300), (24, 32, 46, 255))
    for row, amount in enumerate((10, 15, 20, 150)):
        x = 20
        for index in [11, 10] + [int(c) for c in str(amount)]:
            gx, gy, w, h = rects[index]
            image = atlas.crop((gx, gy, gx + w, gy + h))
            canvas.alpha_composite(image, (x, 15 + row * 70 + (42 - h) // 2))
            x += w + 8
    canvas.convert('RGB').save(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--header', type=Path)
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    if args.header:
        args.header.write_text(header(args.data, args.font))
    if args.preview:
        preview(args.data, args.preview, args.font)