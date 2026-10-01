#!/usr/bin/env python3
"""Check every installable package and its release evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install import validate_catalog, validate_package

COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]
LABELS = ['000', '022.5', '045', '067.5', '090', '112.5', '135', '157.5',
          '180', '202.5', '225', '247.5', '270', '292.5', '315', '337.5']
EXPECTED = ['up', 'up-right', 'up-right', 'up-right', 'right', 'down-right', 'down-right', 'down-right',
            'down', 'down-left', 'down-left', 'down-left', 'left', 'up-left', 'up-left', 'up-left']
REPORTS = ['atlas-validation.json', 'chroma-despill.json', 'frame-review.json',
           'direction-blind-validation.json', 'pet-quality.json', 'direction-semantics.json',
           'look-continuity.json', 'visual-qa.json']


def read_report(path):
    report = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(report, dict):
        raise ValueError('QA report must be an object: ' + path.name)
    return report


def check_evidence(root, pet, files):
    slug = pet['id']
    qa = root / 'qa' / slug
    reports = {name: read_report(qa / name) for name in REPORTS}
    evidence = read_report(qa / 'release-evidence.json')
    if evidence.get('schemaVersion') != 1 or evidence.get('package') != pet['package']:
        raise ValueError(slug + ': QA evidence is for a different package')
    hashes = evidence.get('reports', {})
    if not isinstance(hashes, dict) or set(hashes) != set(REPORTS):
        raise ValueError(slug + ': incomplete QA evidence hashes')
    for name in REPORTS:
        if hashes[name] != hashlib.sha256((qa / name).read_bytes()).hexdigest():
            raise ValueError(slug + ': QA report changed after review: ' + name)
    preview = root / pet['preview']
    if evidence.get('previewSha256') != hashlib.sha256(preview.read_bytes()).hexdigest():
        raise ValueError(slug + ': preview differs from reviewed evidence')
    for name in REPORTS[:5]:
        if reports[name].get('ok') is not True or reports[name].get('errors'):
            raise ValueError(slug + ': QA failed: ' + name)
    for name in ['atlas-validation.json', 'pet-quality.json']:
        if (reports[name].get('sha256') != pet['package']['spritesheet.webp']
                or reports[name].get('encoded_bytes') != len(files['spritesheet.webp'])):
            raise ValueError(slug + ': stale sprite-sheet QA: ' + name)
    directions = reports['direction-semantics.json'].get('directions')
    if not isinstance(directions, list) or len(directions) != 16:
        raise ValueError(slug + ': all sixteen semantic reviews are required')
    for record, label, expected in zip(directions, LABELS, EXPECTED):
        if (not isinstance(record, dict) or record.get('label') != label
                or record.get('expected') != expected or record.get('verdict') not in ('pass', 'warning')
                or not isinstance(record.get('observed'), str) or not record['observed'].strip()
                or not isinstance(record.get('reason'), str) or not record['reason'].strip()):
            raise ValueError(slug + ': incomplete or incorrect direction review: ' + label)
        if label in ('000', '090', '180', '270') and record['verdict'] != 'pass':
            raise ValueError(slug + ': cardinal directions must pass unambiguously')
    continuity = reports['look-continuity.json']
    pairs = continuity.get('pairs')
    if continuity.get('ok') is not True or not isinstance(pairs, list) or len(pairs) != 16:
        raise ValueError(slug + ': invalid continuity evidence')
    for index, pair in enumerate(pairs):
        if (not isinstance(pair, dict) or pair.get('from') != LABELS[index]
                or pair.get('to') != LABELS[(index + 1) % 16]
                or not isinstance(pair.get('centerDelta'), (int, float))
                or not isinstance(pair.get('areaRatio'), (int, float))):
            raise ValueError(slug + ': incomplete continuity pair')
    visual = reports['visual-qa.json']
    if visual.get('visual_qa') != 'pass' or not isinstance(visual.get('motion_review'), str) or not visual['motion_review'].strip():
        raise ValueError(slug + ': missing independent visual motion review')


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
        check_evidence(root, pet, files)
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
