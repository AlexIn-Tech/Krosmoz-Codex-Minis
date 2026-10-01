"""Install real temporary packages; never touch the user's pet collection."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'install.py'


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.dest = self.root / 'codex'
        self.package = self.source / 'pets' / 'test-mini'
        self.package.mkdir(parents=True)
        self.manifest = {'id': 'test-mini', 'displayName': 'Test Mini',
                         'description': 'Test fixture, not release artwork.',
                         'spriteVersionNumber': 2, 'spritesheetPath': 'spritesheet.webp'}
        self.write_manifest()
        Image.new('RGBA', (1536, 2288)).save(self.package / 'spritesheet.webp', lossless=True)
        self.entry = {'id': 'test-mini', 'name': 'Test Mini', 'category': 'characters',
                      'status': 'ready', 'package': {}}
        self.write_catalog()

    def write_manifest(self):
        (self.package / 'pet.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def write_catalog(self):
        self.entry['package'] = {name: hashlib.sha256((self.package / name).read_bytes()).hexdigest()
                                 for name in ('pet.json', 'spritesheet.webp')}
        (self.source / 'catalog.json').write_text(json.dumps({'schemaVersion': 1, 'pets': [self.entry]}), encoding='utf-8')

    def run_install(self, *args):
        return subprocess.run([sys.executable, str(INSTALLER), '--source', str(self.source),
                               '--codex-home', str(self.dest), *args], capture_output=True, text=True)

    def test_valid_package_installs_both_exact_files(self):
        result = self.run_install('test-mini')
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('pet.json', 'spritesheet.webp'):
            self.assertEqual((self.dest / 'pets/test-mini' / name).read_bytes(), (self.package / name).read_bytes())

    def test_unknown_name_does_not_create_target(self):
        result = self.run_install('unknown')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dest.exists())

    def test_planned_pet_is_not_installable_or_listed(self):
        self.entry['status'] = 'planned'
        self.write_catalog()
        self.assertNotEqual(self.run_install('test-mini').returncode, 0)
        self.assertNotIn('test-mini', self.run_install('--list').stdout)

    def test_bad_checksum_preserves_existing_pet_even_with_force(self):
        self.assertEqual(self.run_install('test-mini').returncode, 0)
        installed = self.dest / 'pets/test-mini/pet.json'
        old = installed.read_bytes()
        (self.package / 'pet.json').write_bytes(b'corrupt')
        self.assertNotEqual(self.run_install('test-mini', '--force').returncode, 0)
        self.assertEqual(installed.read_bytes(), old)

    def test_manifest_identity_and_sprite_path_are_validated(self):
        for field, value in [('id', 'other'), ('spritesheetPath', '../secret.webp'), ('spriteVersionNumber', 1)]:
            with self.subTest(field=field):
                original = self.manifest[field]
                self.manifest[field] = value
                self.write_manifest()
                self.write_catalog()
                self.assertNotEqual(self.run_install('test-mini').returncode, 0)
                self.manifest[field] = original
        self.assertFalse(self.dest.exists())

    def test_bad_atlas_dimensions_rejected(self):
        Image.new('RGBA', (192, 208)).save(self.package / 'spritesheet.webp', lossless=True)
        self.write_catalog()
        self.assertNotEqual(self.run_install('test-mini').returncode, 0)
        self.assertFalse(self.dest.exists())

    def test_existing_pet_requires_force_and_force_replaces(self):
        self.assertEqual(self.run_install('test-mini').returncode, 0)
        self.manifest['description'] = 'New description'
        self.write_manifest()
        self.write_catalog()
        self.assertNotEqual(self.run_install('test-mini').returncode, 0)
        self.assertEqual(self.run_install('test-mini', '--force').returncode, 0)
        actual = json.loads((self.dest / 'pets/test-mini/pet.json').read_text())
        self.assertEqual(actual['description'], 'New description')

    def test_dry_run_makes_no_files(self):
        self.assertEqual(self.run_install('test-mini', '--dry-run').returncode, 0)
        self.assertFalse(self.dest.exists())

    def test_traversal_slug_is_rejected(self):
        self.entry['id'] = '../escape'
        self.write_catalog()
        self.assertNotEqual(self.run_install('../escape').returncode, 0)
        self.assertFalse((self.root / 'escape').exists())

    def test_symlink_destination_is_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.dest / 'pets').mkdir(parents=True)
        try:
            (self.dest / 'pets/test-mini').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks requires privileges on this host')
        self.assertNotEqual(self.run_install('test-mini', '--force').returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_replacement_restores_old_package(self):
        spec = importlib.util.spec_from_file_location('mini_installer', INSTALLER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = {name: (self.package / name).read_bytes() for name in self.entry['package']}
        module.install_pet(self.entry, files, self.dest)
        old = (self.dest / 'pets/test-mini/pet.json').read_bytes()
        real_rename = Path.rename

        def interrupted_rename(path, target):
            if path.name.startswith('.test-mini-') and '-backup-' not in path.name:
                raise OSError('Simulated installation failure')
            return real_rename(path, target)

        with patch.object(Path, 'rename', interrupted_rename):
            with self.assertRaises(OSError):
                module.install_pet(self.entry, files, self.dest, force=True)
        self.assertEqual((self.dest / 'pets/test-mini/pet.json').read_bytes(), old)
        self.assertEqual([p.name for p in (self.dest / 'pets').iterdir()], ['test-mini'])


if __name__ == '__main__':
    unittest.main()
