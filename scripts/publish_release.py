"""Publish only verified snapshots; stage as draft and never overwrite public assets."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from snapshot import ROOT, REPOSITORY, build, verify

def gh(*args):
    result = subprocess.run(['gh', *map(str, args), '--repo', REPOSITORY],
                            check=True, capture_output=True, text=True, timeout=120)
    return result.stdout

def publish(root, revision, run=gh):
    tag, metadata, bundle = build(root, revision)
    verify(bundle, tag)
    # Paginate all releases so old versions are not accidentally recreated.
    # gh api uses -R neither here nor implicitly: use an explicit REST path.
    if run is gh:
        result = subprocess.run(['gh', 'api', '--paginate', '--slurp',
                                 f'repos/{REPOSITORY}/releases?per_page=100'],
                                check=True, capture_output=True, text=True, timeout=120)
        pages = json.loads(result.stdout)
    else:
        pages = json.loads(run('list'))
    matches = [release for page in pages for release in page if release['tag_name'] == tag]
    if len(matches) > 1:
        raise ValueError('Duplicate release tags')
    existing = matches[0] if matches else None
    if existing and existing.get('target_commitish') != revision:
        raise ValueError('Release target does not match the verified commit')
    with tempfile.TemporaryDirectory() as scratch:
        directory = Path(scratch)
        zip_path, manifest_path = directory / 'snapshot.zip', directory / 'snapshot.json'
        zip_path.write_bytes(bundle)
        manifest_path.write_bytes(metadata)
        if existing is None:
            notes = directory / 'notes.md'
            notes.write_text(f'Validated routing snapshot of commit {revision}.\n\n'
                             'Contains public rules and credential-free templates only. '
                             'Local node bindings and iPad background refresh require device validation.\n'
                             'Attribution and license: see NOTICE.md inside snapshot.zip.\n')
            run('release', 'create', tag, zip_path, manifest_path, '--draft', '--target', revision,
                '--title', f'Routing snapshot {revision[:12]}', '--notes-file', notes)
        elif existing['draft']:
            run('release', 'upload', tag, zip_path, manifest_path, '--clobber')
        downloaded = directory / 'downloaded'
        downloaded.mkdir()
        run('release', 'download', tag, '--pattern', 'snapshot.zip', '--pattern', 'snapshot.json',
            '--dir', downloaded)
        if (downloaded / 'snapshot.zip').read_bytes() != bundle or (downloaded / 'snapshot.json').read_bytes() != metadata:
            raise ValueError('Remote snapshot mismatch; public release was not modified')
        verify((downloaded / 'snapshot.zip').read_bytes(), tag)
        if existing is None or existing['draft']:
            run('release', 'edit', tag, '--draft=false', '--latest')
    return f'https://github.com/{REPOSITORY}/releases/tag/{tag}'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    # CLI stderr and downloaded content must not leak into workflow output.
    try:
        print(publish(ROOT, args.commit))
    except Exception:
        raise SystemExit('Release failed safely. A draft may remain; existing public snapshots were not overwritten.')
