"""Synthetic test data only; never used as release character artwork."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw

LABELS = ['000', '022.5', '045', '067.5', '090', '112.5', '135', '157.5',
          '180', '202.5', '225', '247.5', '270', '292.5', '315', '337.5']
EXPECTED = ['up', 'up-right', 'up-right', 'up-right', 'right', 'down-right', 'down-right', 'down-right',
            'down', 'down-left', 'down-left', 'down-left', 'left', 'up-left', 'up-left', 'up-left']
REPORTS = ['atlas-validation.json', 'chroma-despill.json', 'frame-review.json',
           'direction-blind-validation.json', 'pet-quality.json', 'direction-semantics.json',
           'look-continuity.json', 'visual-qa.json']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def seal_evidence(root):
    package = root / 'pets/test-mini'
    qa = root / 'qa/test-mini'
    write_json(qa / 'release-evidence.json', {
        'schemaVersion': 1,
        'package': {name: digest(package / name) for name in ['pet.json', 'spritesheet.webp']},
        'previewSha256': digest(root / 'assets/previews/test-mini.gif'),
        'reports': {name: digest(qa / name) for name in REPORTS}})


def make_fixture(root):
    package = root / 'pets/test-mini'
    qa = root / 'qa/test-mini'
    package.mkdir(parents=True)
    write_json(package / 'pet.json', {'id': 'test-mini', 'displayName': 'Test',
        'description': 'Synthetic test only', 'spriteVersionNumber': 2, 'spritesheetPath': 'spritesheet.webp'})
    image = Image.new('RGBA', (1536, 2288))
    draw = ImageDraw.Draw(image)
    for row, count in enumerate([6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]):
        for column in range(count):
            lift = [0, 12, 32, 12, 0][column] if row == 4 else 0
            draw.rectangle((column * 192 + 20 + column, row * 208 + 60 - lift,
                            column * 192 + 80 + column, row * 208 + 120 - lift), fill='blue')
    draw.rectangle((6 * 192 + 20, 60, 6 * 192 + 80, 120), fill='blue')
    atlas = package / 'spritesheet.webp'
    image.save(atlas, lossless=True)
    preview = root / 'assets/previews/test-mini.gif'
    preview.parent.mkdir(parents=True)
    Image.new('RGB', (20, 20), 'blue').save(preview, save_all=True,
        append_images=[Image.new('RGB', (20, 20), 'red')], duration=100, loop=0)
    write_json(root / 'catalog.json', {'schemaVersion': 1, 'pets': [{
        'id': 'test-mini', 'name': 'Test', 'category': 'characters', 'status': 'ready',
        'preview': 'assets/previews/test-mini.gif',
        'package': {name: digest(package / name) for name in ['pet.json', 'spritesheet.webp']}}]})
    for name in REPORTS[:5]:
        write_json(qa / name, {'ok': True, 'sha256': digest(atlas), 'encoded_bytes': atlas.stat().st_size, 'errors': []})
    write_json(qa / 'direction-semantics.json', {'directions': [
        dict(label=label, expected=expected, observed=expected, verdict='pass', reason='Synthetic landmark test fixture.')
        for label, expected in zip(LABELS, EXPECTED)]})
    write_json(qa / 'look-continuity.json', {'ok': True, 'pairs': [
        {'from': label, 'to': LABELS[(index + 1) % 16], 'centerDelta': 1, 'areaRatio': 1,
         'diffPixels': 1, 'firstPixels': 1000, 'secondPixels': 1000}
        for index, label in enumerate(LABELS)], 'warnings': [], 'alphaHoles': []})
    write_json(qa / 'visual-qa.json', {'visual_qa': 'pass', 'motion_review': 'Synthetic test fixture only.'})
    seal_evidence(root)
