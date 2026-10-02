#!/usr/bin/env python3
"""Enlarge Toross's README preview without changing the reviewed release GIF."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]


def main():
    frames, durations = [], []
    with Image.open(ROOT / 'assets/previews/toross-mordal.gif') as source:
        loop = source.info.get('loop', 0)
        for index in range(source.n_frames):
            source.seek(index)
            frames.append(source.convert('RGBA'))
            durations.append(source.info['duration'])
    if len(frames) != sum(COUNTS):
        raise ValueError('Unexpected animation frame count')
    output = []
    start = 0
    for count in COUNTS:
        group = frames[start:start + count]
        boxes = [frame.getchannel('A').getbbox() for frame in group]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        width, height = box[2] - box[0], box[3] - box[1]
        scale = min(182 / width, 198 / height)
        size = (round(width * scale), round(height * scale))
        for frame in group:
            # One transform per animation preserves movement within the loop.
            crop = frame.crop(box).resize(size, Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (192, 208))
            canvas.paste(crop, ((192 - size[0]) // 2, 203 - size[1]))
            indexed = canvas.convert('RGB').quantize(colors=255)
            indexed.putpalette(indexed.getpalette()[:765] + [0, 0, 0])
            transparent = canvas.getchannel('A').point(lambda alpha: 255 if alpha < 128 else 0)
            indexed.paste(255, mask=transparent)
            indexed.info['transparency'] = 255
            output.append(indexed)
        start += count
    output[0].save(ROOT / 'assets/previews/toross-mordal-gallery.gif', save_all=True,
                   append_images=output[1:], duration=durations, loop=loop,
                   transparency=255, disposal=2, optimize=False)


if __name__ == '__main__':
    main()
