#!/usr/bin/env python3
"""Check every installable package and its release evidence."""
import argparse
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install import validate_catalog, validate_package

COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]


def check(root):
    pets = validate_catalog(json.loads((root / 'catalog.json').read_text(encoding='utf-8-sig')))
    ready = [pet for pet in pets if pet['status'] == 'ready']
    for pet in ready:
        slug = pet['id']
        package = root / 'pets' / slug
        files = {name: (package / name).read_bytes() for name in pet['package']}
        validate_package(pet, files)
        with Image.open(package / 'spritesheet.webp') as source:
            if source.mode != 'RGBA':
                raise ValueError(slug + ': sprite sheet must have alpha')
            atlas = source.convert('RGBA')
            if not atlas.getbbox():
                raise ValueError(slug + ': empty sprite sheet')
            for row, count in enumerate(COUNTS):
                for column in range(8):
                    cell = atlas.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208))
                    bbox = cell.getchannel('A').getbbox()
                    used = column < count or (row, column) == (0, 6)
                    if used and not bbox:
                        raise ValueError('%s: empty required cell %s/%s' % (slug, row, column))
                    if not used and bbox:
                        raise ValueError('%s: nonempty unused cell %s/%s' % (slug, row, column))
                    if bbox and (bbox[0] <= 0 or bbox[1] <= 0 or bbox[2] >= 192 or bbox[3] >= 208):
                        raise ValueError('%s: clipped cell %s/%s' % (slug, row, column))
        preview_path = 'assets/previews/%s.gif' % slug
        if pet.get('preview') != preview_path:
            raise ValueError(slug + ': invalid preview path')
        with Image.open(root / preview_path) as preview:
            if preview.format != 'GIF' or getattr(preview, 'n_frames', 1) < 2:
                raise ValueError(slug + ': preview must actually animate')
        qa_root = root / 'qa' / slug
        for name in ['atlas-validation.json', 'chroma-despill.json', 'frame-review.json',
                     'direction-blind-validation.json', 'pet-quality.json']:
            report = json.loads((qa_root / name).read_text(encoding='utf-8'))
            if report.get('ok') is not True:
                raise ValueError(slug + ': QA failed: ' + name)
        semantics = json.loads((qa_root / 'direction-semantics.json').read_text(encoding='utf-8'))
        verdicts = semantics.get('directions', [])
        if len(verdicts) != 16 or any(item.get('verdict') == 'fail' for item in verdicts):
            raise ValueError(slug + ': missing or failed direction semantics')
        if not (qa_root / 'look-continuity.json').is_file():
            raise ValueError(slug + ': missing continuity evidence')
        print('Validated: ' + slug)
    # Orphan release packages must not silently bypass catalog validation.
    package_root = root / 'pets'
    if package_root.exists():
        expected = {pet['id'] for pet in ready}
        actual = {item.name for item in package_root.iterdir() if item.is_dir()}
        if actual != expected:
            raise ValueError('Pet package folders do not match completed catalog entries')
    print('%s ready; %s planned' % (len(ready), len(pets) - len(ready)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        check(args.root)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('Release validation failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
