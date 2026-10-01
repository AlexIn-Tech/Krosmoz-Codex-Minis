#!/usr/bin/env python3
"""Install verified fan-art minis. Python 3.9+, no third-party dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPOSITORY = 'AlexIn-Tech/dofus-mini-codex-pet'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
MAX_DOWNLOAD = 32 * 1024 * 1024


def read_json(data):
    return json.loads(data.decode('utf-8-sig'))


def validate_catalog(catalog):
    if not isinstance(catalog, dict) or catalog.get('schemaVersion') != 1 or not isinstance(catalog.get('pets'), list):
        raise ValueError('Unsupported catalog format')
    seen = set()
    for pet in catalog['pets']:
        if not isinstance(pet, dict):
            raise ValueError('Invalid catalog entry')
        slug = pet.get('id', '')
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug in seen:
            raise ValueError('Unsafe or duplicate catalog name')
        seen.add(slug)
        if pet.get('status') not in ('planned', 'ready'):
            raise ValueError('Invalid catalog status')
        if pet['status'] == 'ready':
            files = pet.get('package', {})
            if set(files) != {'pet.json', 'spritesheet.webp'}:
                raise ValueError('Invalid package file list')
            if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
                   for value in files.values()):
                raise ValueError('Invalid package checksum')
    return catalog['pets']


def webp_dimensions(data):
    if len(data) < 30 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        raise ValueError('Invalid WebP sprite sheet')
    if struct.unpack_from('<I', data, 4)[0] + 8 != len(data):
        raise ValueError('Truncated WebP sprite sheet')
    kind = data[12:16]
    if kind == b'VP8X':
        return (1 + int.from_bytes(data[24:27], 'little'),
                1 + int.from_bytes(data[27:30], 'little'))
    if kind == b'VP8L' and data[20] == 0x2f:
        packed = int.from_bytes(data[21:25], 'little')
        return (1 + (packed & 0x3fff), 1 + ((packed >> 14) & 0x3fff))
    if kind == b'VP8 ' and data[23:26] == b'\x9d\x01\x2a':
        return (int.from_bytes(data[26:28], 'little') & 0x3fff,
                int.from_bytes(data[28:30], 'little') & 0x3fff)
    raise ValueError('Unsupported WebP encoding')


def validate_package(pet, files):
    for name, expected in pet['package'].items():
        if hashlib.sha256(files[name]).hexdigest() != expected:
            raise ValueError('Checksum mismatch: ' + name)
    manifest = read_json(files['pet.json'])
    if (not isinstance(manifest, dict) or manifest.get('id') != pet['id'] or manifest.get('spriteVersionNumber') != 2
            or manifest.get('spritesheetPath') != 'spritesheet.webp'
            or not isinstance(manifest.get('displayName'), str)
            or not manifest['displayName'].strip()
            or not isinstance(manifest.get('description'), str)):
        raise ValueError('Invalid pet manifest or identity')
    if webp_dimensions(files['spritesheet.webp']) != (1536, 2288):
        raise ValueError('Sprite sheet must be 1536x2288 for Codex v2')


def https_get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'krosmoz-codex-minis'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(MAX_DOWNLOAD + 1)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise ValueError('Repository unavailable. For private access, run gh auth login and use --private.') from None
        raise ValueError('GitHub download failed (HTTP %s)' % error.code) from None
    if len(data) > MAX_DOWNLOAD:
        raise ValueError('Download exceeds size limit')
    return data


def gh_get(endpoint, raw=False):
    args = ['gh', 'api', endpoint]
    if raw:
        args += ['-H', 'Accept: application/vnd.github.raw+json']
    result = subprocess.run(args, capture_output=True, timeout=60)
    if result.returncode:
        # Deliberately do not echo CLI stderr or authentication details.
        raise ValueError('Private GitHub access failed. Run gh auth login and confirm repository access.')
    if len(result.stdout) > MAX_DOWNLOAD:
        raise ValueError('Download exceeds size limit')
    return result.stdout


class Source:
    def __init__(self, local, repository, ref, private):
        self.local = Path(local).resolve() if local else None
        self.repository = repository
        self.private = private
        if self.local:
            self.commit = None
            return
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid GitHub repository')
        if not ref or len(ref) > 200 or ref.startswith('-'):
            raise ValueError('Invalid Git ref')
        endpoint = 'repos/%s/commits/%s' % (repository, urllib.parse.quote(ref, safe=''))
        commit = read_json(gh_get(endpoint) if private else https_get('https://api.github.com/' + endpoint))
        self.commit = commit.get('sha', '')
        if not re.fullmatch('[0-9a-f]{40}', self.commit):
            raise ValueError('Cannot resolve repository commit')

    def get(self, relative):
        # All callers use fixed filenames and catalog-validated slugs.
        if self.local:
            target = self.local / relative
            if not target.resolve().is_relative_to(self.local):
                raise ValueError('Source path escapes repository')
            if target.stat().st_size > MAX_DOWNLOAD:
                raise ValueError('Source file exceeds size limit')
            return target.read_bytes()
        if self.private:
            return gh_get('repos/%s/contents/%s?ref=%s' % (self.repository, relative, self.commit), raw=True)
        return https_get('https://raw.githubusercontent.com/%s/%s/%s' % (self.repository, self.commit, relative))


def reject_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Refusing symlink or junction destination')
        if os.name == 'nt':
            try:
                attributes = item.lstat().st_file_attributes
            except FileNotFoundError:
                continue
            if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Refusing reparse-point destination')


def install_pet(pet, files, codex_home, force=False, dry_run=False):
    validate_package(pet, files)
    # Canonicalize the user-chosen home: macOS /var is a system symlink.
    # Links inside the resulting pets directory are still rejected.
    home = Path(codex_home).expanduser().resolve()
    destination = home / 'pets' / pet['id']
    reject_links(destination)
    if destination.exists() and not force:
        raise ValueError('Pet already exists; use --force to replace it')
    if destination.exists() and not destination.is_dir():
        raise ValueError('Pet destination is not a directory')
    if dry_run:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + pet['id'] + '-', dir=destination.parent))
    backup = destination.parent / ('.' + pet['id'] + '-backup-' + uuid.uuid4().hex)
    moved_old = False
    try:
        for name, data in files.items():
            (stage / name).write_bytes(data)
        reject_links(destination)
        if destination.exists():
            if not force:
                raise ValueError('Pet was installed concurrently; use --force')
            destination.rename(backup)
            moved_old = True
        try:
            stage.rename(destination)
        except BaseException:
            if moved_old:
                backup.rename(destination)
            raise
        if moved_old:
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pet', nargs='?', help='Installation name from the gallery')
    parser.add_argument('--list', action='store_true', help='List completed, installable minis')
    parser.add_argument('--source', help='Install from a local repository clone')
    parser.add_argument('--repo', default=REPOSITORY, help='GitHub owner/repository')
    parser.add_argument('--ref', default='main', help='Branch, tag, or commit (resolved before downloads)')
    parser.add_argument('--private', action='store_true', help='Use authenticated GitHub CLI access')
    parser.add_argument('--codex-home', default=os.environ.get('CODEX_HOME') or str(Path.home() / '.codex'))
    parser.add_argument('--force', action='store_true', help='Replace an existing pet after validation')
    parser.add_argument('--dry-run', action='store_true', help='Validate without writing files')
    args = parser.parse_args(argv)
    if not args.list and not args.pet:
        parser.error('Supply a pet name or --list')
    if args.pet and not SLUG.fullmatch(args.pet):
        parser.error('Invalid pet name; use its gallery installation name')
    try:
        source = Source(args.source, args.repo, args.ref, args.private)
        pets = validate_catalog(read_json(source.get('catalog.json')))
        if args.list:
            available = [pet for pet in pets if pet['status'] == 'ready']
            print('\n'.join('%s\t%s' % (pet['id'], pet['name']) for pet in available)
                  if available else 'No completed minis are available yet.')
            return 0
        pet = next((pet for pet in pets if pet['id'] == args.pet), None)
        if not pet:
            raise ValueError('Unknown pet name; use --list')
        if pet['status'] != 'ready':
            raise ValueError('This mini is planned and has not passed animation QA yet')
        files = {name: source.get('pets/%s/%s' % (pet['id'], name)) for name in pet['package']}
        destination = install_pet(pet, files, args.codex_home, args.force, args.dry_run)
        print(('Validated' if args.dry_run else 'Installed') + ' ' + pet['name'] + ': ' + str(destination))
        if source.commit:
            print('Source commit: ' + source.commit)
        if not args.dry_run:
            print('Restart Codex if needed, then choose the mini in the pet picker.')
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, urllib.error.URLError) as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
