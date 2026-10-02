#!/usr/bin/env python3
"""Build the end-user README gallery from the release catalog."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install import validate_catalog

GALLERY_ORDER = [
    'goultard', 'qilby', 'toross-mordal', 'goultard-dark', 'dark-vlad', 'ruel', 'kerubim',
    'ignemikhal', 'terrakourial', 'dardondakal', 'grougalorasalar', 'aguabrial', 'aerafal',
    'dofus-emerald', 'dofus-turquoise', 'dofus-crimson', 'dofus-ochre', 'dofus-ivory', 'dofus-ebony',
]


def render_cards(pets):
    rows = []
    for start in range(0, len(pets), 4):
        cards = []
        for pet in pets[start:start + 4]:
            preview = pet.get('preview', '')
            if preview != 'assets/previews/%s.gif' % pet['id']:
                raise ValueError('Invalid gallery preview path')
            if pet['id'] == 'toross-mordal':
                preview = 'assets/previews/toross-mordal-gallery.gif'
            cards.append('<img src="%s" alt="%s" width="160"><br><strong>%s</strong><br><code>%s</code>' %
                         (preview, pet['name'], pet['name'], pet['id']))
        cards.extend([''] * (4 - len(cards)))
        rows.append('| ' + ' | '.join(cards) + ' |')
    return '\n'.join(['| | | | |', '| --- | --- | --- | --- |', *rows])


def render(catalog):
    pets = validate_catalog(catalog)
    ready = [pet for pet in pets if pet['status'] == 'ready']
    ideas = [pet for pet in pets if pet['status'] == 'planned']
    rank = {name: index for index, name in enumerate(GALLERY_ORDER)}
    ordered = sorted(ready, key=lambda pet: (rank.get(pet['id'], len(rank)), pet['name'].casefold()))
    featured = [pet for pet in ordered if pet['category'] == 'characters']
    dragons = [pet for pet in ordered if pet['category'] == 'dragons']
    dofus = [pet for pet in ordered if pet['category'] == 'eggs']
    gallery = []
    for title, group in [('Characters', featured), ('Dragons', dragons), ('Dofus', dofus)]:
        if group:
            if gallery:
                gallery.append('')
            gallery.extend(['### ' + title, '', render_cards(group)])
    if not gallery:
        gallery = ['No minis are available yet.']
    idea_names = ', '.join(pet['name'] for pet in ideas) + '.' if ideas else 'No future ideas listed.'
    return '''# Krosmoz Codex Minis

Unofficial animated fan art for **Codex**. This project is not affiliated with
or endorsed by Ankama or OpenAI. See [credits](CREDITS.md).

## Animated minis

Choose a mini below. Each preview shows its animations. Use the code beneath it
as the install name.

<!-- gallery:start -->
%s
<!-- gallery:end -->

## Install

Requires Python 3.9+ and a Codex desktop version with custom pet support.
Clone the repository, then run:

```sh
git clone https://github.com/AlexIn-Tech/Krosmoz-Codex-Minis.git
cd Krosmoz-Codex-Minis
python install.py --source . --list
python install.py goultard --source .
```

Replace `goultard` with any install name in the gallery. On Windows, use
`py` if `python` is unavailable; on macOS or Linux, use `python3`. Restart
Codex if needed, then choose the mini in the pet picker.

## Ideas

%s

Code is licensed under MIT; that license does not cover the character artwork.
''' % ('\n'.join(gallery), idea_names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((args.root / 'catalog.json').read_text(encoding='utf-8-sig'))
    text = render(catalog)
    path = args.root / 'README.md'
    if args.check:
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            print('README gallery is stale; run python tools/gallery.py', file=sys.stderr)
            return 1
    else:
        with path.open('w', encoding='utf-8', newline='\n') as output:
            output.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
