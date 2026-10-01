"""Release tooling must keep planned art out of installable galleries."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import json
import hashlib
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
