"""Release tooling must keep planned art out of installable galleries."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import json
import hashlib
from PIL import Image, ImageDraw
from release_fixture import make_fixture, seal_evidence, write_json

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def validate(self, root):
        return subprocess.run([sys.executable, str(ROOT / 'tools/validate_release.py'), '--root', str(root)], capture_output=True, text=True)

    def test_complete_release_evidence_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            result = self.validate(root)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_changing_atlas_and_catalog_cannot_reuse_old_qa(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            atlas = root / 'pets/test-mini/spritesheet.webp'
            with Image.open(atlas) as source:
                changed = source.convert('RGBA')
            changed.putpixel((30, 70), (255, 0, 0, 255))
            changed.save(atlas, lossless=True)
            catalog = json.loads((root / 'catalog.json').read_text())
            catalog['pets'][0]['package']['spritesheet.webp'] = hashlib.sha256(atlas.read_bytes()).hexdigest()
            write_json(root / 'catalog.json', catalog)
            self.assertNotEqual(self.validate(root).returncode, 0)

    def test_empty_direction_verdicts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            write_json(root / 'qa/test-mini/direction-semantics.json', {'directions': [{}] * 16})
            seal_evidence(root)
            self.assertNotEqual(self.validate(root).returncode, 0)

    def test_duplicate_direction_verdicts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            path = root / 'qa/test-mini/direction-semantics.json'
            semantics = json.loads(path.read_text())
            semantics['directions'][1] = semantics['directions'][0]
            write_json(path, semantics)
            seal_evidence(root)
            self.assertNotEqual(self.validate(root).returncode, 0)

    def test_continuity_requires_valid_json_and_a_passing_report(self):
        for content in ['not json', '{"ok": false}', '{"ok": true, "pairs": []}']:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                make_fixture(root)
                (root / 'qa/test-mini/look-continuity.json').write_text(content, encoding='utf-8')
                seal_evidence(root)
                self.assertNotEqual(self.validate(root).returncode, 0)

    def test_gallery_renders_ready_names_and_animated_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = {'schemaVersion': 1, 'pets': [
                {'id': 'goultard', 'name': 'Goultard', 'category': 'characters', 'status': 'ready',
                 'preview': 'assets/previews/goultard.gif',
                 'package': {'pet.json': 'a' * 64, 'spritesheet.webp': 'b' * 64}},
                {'id': 'nox', 'name': 'Nox', 'category': 'characters', 'status': 'planned'}]}
            (root / 'catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/gallery.py'), '--root', str(root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            readme = (root / 'README.md').read_text(encoding='utf-8')
            self.assertIn('![Goultard](assets/previews/goultard.gif)', readme)
            self.assertIn('`goultard`', readme)
            gallery = readme.split('<!-- gallery:start -->')[1].split('<!-- gallery:end -->')[0]
            self.assertNotIn('nox', gallery)
            self.assertIn('Nox', readme.split('Planned collection')[1])

    def test_gallery_check_detects_stale_readme(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'catalog.json').write_text(json.dumps({'schemaVersion': 1, 'pets': []}), encoding='utf-8')
            (root / 'README.md').write_text('stale', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/gallery.py'), '--root', str(root), '--check'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_release_rejects_empty_art_even_with_matching_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'pets/empty-mini'
            package.mkdir(parents=True)
            (package / 'pet.json').write_text(json.dumps({'id': 'empty-mini', 'displayName': 'Empty',
                'description': 'Test only', 'spriteVersionNumber': 2, 'spritesheetPath': 'spritesheet.webp'}), encoding='utf-8')
            Image.new('RGBA', (1536, 2288)).save(package / 'spritesheet.webp', lossless=True)
            hashes = {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                      for name in ('pet.json', 'spritesheet.webp')}
            (root / 'catalog.json').write_text(json.dumps({'schemaVersion': 1, 'pets': [
                {'id': 'empty-mini', 'name': 'Empty', 'category': 'characters', 'status': 'ready',
                 'package': hashes, 'preview': 'assets/previews/empty-mini.gif'}]}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/validate_release.py'), '--root', str(root)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('empty', result.stderr.lower())

    def test_native_v2_counts_include_failure_loop_and_neutral_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'pets/test-mini'
            package.mkdir(parents=True)
            (package / 'pet.json').write_text(json.dumps({'id': 'test-mini', 'displayName': 'Test',
                'description': 'Synthetic test only', 'spriteVersionNumber': 2, 'spritesheetPath': 'spritesheet.webp'}), encoding='utf-8')
            image = Image.new('RGBA', (1536, 2288))
            draw = ImageDraw.Draw(image)
            for row, count in enumerate([6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]):
                for column in range(count):
                    draw.rectangle((column * 192 + 20, row * 208 + 20,
                                    column * 192 + 80, row * 208 + 80), fill='blue')
            draw.rectangle((6 * 192 + 20, 20, 6 * 192 + 80, 80), fill='blue')
            image.save(package / 'spritesheet.webp', lossless=True)
            preview = root / 'assets/previews/test-mini.gif'
            preview.parent.mkdir(parents=True)
            Image.new('RGB', (20, 20), 'blue').save(preview, save_all=True,
                append_images=[Image.new('RGB', (20, 20), 'red')], duration=100, loop=0)
            hashes = {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                      for name in ('pet.json', 'spritesheet.webp')}
            (root / 'catalog.json').write_text(json.dumps({'schemaVersion': 1, 'pets': [
                {'id': 'test-mini', 'name': 'Test', 'category': 'characters', 'status': 'ready',
                 'package': hashes, 'preview': 'assets/previews/test-mini.gif'}]}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools/validate_release.py'), '--root', str(root)], capture_output=True, text=True)
            self.assertIn('atlas-validation.json', result.stderr)


if __name__ == '__main__':
    unittest.main()
