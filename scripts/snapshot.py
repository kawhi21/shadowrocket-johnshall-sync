"""Build/verify a deterministic allowlisted release. No private files are bundled."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from check_repo import ROOT, check_repository, check_secrets

PATHS = ('generated/proxy.list', 'generated/reject.list', 'generated/validation.json',
         'templates/Public-Starter.conf', 'templates/AI-Public.sgmodule',
         'templates/Johnshall-Auto-Rules.conf',
         'templates/personal/Johnshall-AI-Extended.conf.example',
         'templates/personal/AI-Stable-Routing.sgmodule.example', 'NOTICE.md')
REPOSITORY = 'kawhi21/shadowrocket-johnshall-sync'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def build(root, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('A full reviewed commit is required')
    check_repository(root)
    payload = {}
    for name in PATHS:
        body = (root / name).read_bytes()
        if name.endswith('.conf'):
            body = body.replace(b'/main/generated/', f'/{revision}/generated/'.encode())
        payload[name] = body
    manifest = {'schema_version': 1, 'repository': REPOSITORY, 'commit': revision,
                'files': {name: {'bytes': len(body), 'sha256': digest(body)}
                          for name, body in sorted(payload.items())}}
    metadata = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    tag = 'rules-' + digest(metadata)
    payload['snapshot.json'] = metadata
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    return tag, metadata, stream.getvalue()

def verify(bundle, expected_tag):
    if not re.fullmatch(r'rules-[0-9a-f]{64}', expected_tag):
        raise ValueError('Invalid release tag')
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        if len(names) != len(set(names)) or set(names) != set(PATHS) | {'snapshot.json'}:
            raise ValueError('Unexpected snapshot paths')
        if sum(i.file_size for i in entries) > 12_000_000:
            raise ValueError('Snapshot too large')
        for entry in entries:
            if ((entry.external_attr >> 16) & 0o170000) not in (0, 0o100000):
                raise ValueError('Nonregular snapshot file')
        metadata = archive.read('snapshot.json')
        if 'rules-' + digest(metadata) != expected_tag:
            raise ValueError('Snapshot identity mismatch')
        manifest = json.loads(metadata)
        if manifest['schema_version'] != 1 or manifest['repository'] != REPOSITORY:
            raise ValueError('Unknown snapshot schema/repository')
        if set(manifest['files']) != set(PATHS) or not re.fullmatch(r'[0-9a-f]{40}', manifest['commit']):
            raise ValueError('Invalid manifest')
        payload = {}
        for name in PATHS:
            body = archive.read(name)
            if manifest['files'][name] != {'bytes': len(body), 'sha256': digest(body)}:
                raise ValueError('Snapshot file hash mismatch')
            check_secrets(body.decode('utf-8-sig'), config=name.endswith(('.conf', '.example', '.sgmodule', '.list')))
            payload[name] = body
        return manifest, payload

def extract(bundle, expected_tag, destination):
    manifest, payload = verify(bundle, expected_tag)
    # Verify everything first. Never merge into an existing device backup or source tree.
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Extraction requires a new directory')
    destination.mkdir(parents=True)
    for name, body in payload.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    (destination / 'snapshot.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    create.add_argument('--commit', required=True)
    create.add_argument('--out', type=Path, default=ROOT / 'dist')
    restore = commands.add_parser('extract')
    restore.add_argument('--zip', type=Path, required=True)
    restore.add_argument('--tag', required=True)
    restore.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        tag, metadata, bundle = build(ROOT, args.commit)
        verify(bundle, tag)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'snapshot.json').write_bytes(metadata)
        (args.out / 'snapshot.zip').write_bytes(bundle)
        (args.out / 'tag.txt').write_text(tag + '\n')
        print(tag)
    else:
        extract(args.zip.read_bytes(), args.tag, args.out)
        print('Verified snapshot extracted; no active device configuration was changed.')
