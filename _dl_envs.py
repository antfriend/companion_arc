"""Download wa30, cn04, ka59 environment files from competition."""
from kaggle import api
import os, zipfile
from pathlib import Path

api.authenticate()

COMPETITION = 'arc-prize-2026-arc-agi-3'
TARGETS = ['wa30-ee6fef47', 'cn04-2fe56bfb', 'ka59-38d34dbb']
DEST = Path('environment_files')

# Try to find environment_files in competition data via page tokens
page = None
all_refs = []
while True:
    resp = api.competition_list_files(COMPETITION, page_token=page)
    for f in (resp.files or []):
        if any(t in f.name for t in TARGETS):
            all_refs.append(f.name)
    page = resp.next_page_token
    if not page:
        break
    print(f'  fetched page, total so far: {len(all_refs)}')

print(f'Matching refs: {all_refs}')

if not all_refs:
    # Try competition download path
    print('Trying direct download...')
    for target in TARGETS:
        game = target.split('-')[0]
        inst = target.split('-')[1]
        fname = f'environment_files/{game}/{inst}/{game}.py'
        try:
            api.competition_download_file(COMPETITION, fname, path=str(DEST / game / inst))
            print(f'Downloaded: {fname}')
        except Exception as e:
            print(f'  {game}: {e}')
