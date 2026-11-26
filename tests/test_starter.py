import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_repo as checks
import snapshot
from publish_release import publish

REVISION = '1' * 40

class Templates(unittest.TestCase):
    def test_public_profile_needs_no_private_group(self):
        checks.check_templates()
        base = checks.sections((checks.ROOT / checks.PUBLIC).read_text())
        self.assertNotIn('[Proxy Group]', base)
        self.assertTrue(all(line.split(',')[-1] in ('PROXY', 'DIRECT', 'REJECT') for line in base['[Rule]']))
        self.assertNotIn('AI-Stable', (checks.ROOT / checks.PUBLIC_AI).read_text())

    def test_public_ai_module_resolves_only_builtin_policy(self):
        ai = checks.sections((checks.ROOT / checks.PUBLIC_AI).read_text())['[Rule]']
        policies = {rule.split(',')[-1] for rule in ai}
        self.assertEqual(policies, {'PROXY'})
        self.assertEqual(len(ai), 9)

    def test_personal_ai_domains_match_public_and_bind_locally(self):
        public = checks.sections((checks.ROOT / checks.PUBLIC_AI).read_text())['[Rule]']
        personal = checks.sections((checks.ROOT / checks.PERSONAL_AI).read_text())['[Rule]']
        self.assertEqual([r.rsplit(',', 1)[0] for r in public], [r.rsplit(',', 1)[0] for r in personal])
        self.assertTrue(all(r.endswith(',AI-Stable') for r in personal))

    def test_credential_detector_rejects_connection_material(self):
        samples = ['vmess' + '://synthetic', 'https://example.invalid/sub?' + 'token=synthetic',
                   '-'.join(['12345678', '1234', '1234', '1234', '123456789abc']),
                   'gh' + 'p_' + 'A' * 30, '[Proxy]\nnode = synthetic',
                   'server = example.invalid', 'password = synthetic']
        for sample in samples:
            with self.subTest(length=len(sample)), self.assertRaises(ValueError):
                checks.check_secrets(sample, config=True)

    def test_generated_content_matches_manifest(self):
        checks.check_generated()

class Snapshots(unittest.TestCase):
    def test_deterministic_and_commit_pinned(self):
        a = snapshot.build(checks.ROOT, REVISION)
        self.assertEqual(a, snapshot.build(checks.ROOT, REVISION))
        manifest, payload = snapshot.verify(a[2], a[0])
        self.assertEqual(manifest['commit'], REVISION)
        self.assertIn(f'/{REVISION}/generated/'.encode(), payload[checks.PUBLIC])
        self.assertNotIn(b'/main/generated/', payload[checks.PUBLIC])

    def test_tamper_wrong_tag_and_unexpected_paths_rejected(self):
        tag, _, bundle = snapshot.build(checks.ROOT, REVISION)
        with self.assertRaises(ValueError):
            snapshot.verify(bundle, 'rules-' + '0' * 64)
        for extra in ('../escaped.conf', 'snapshot.json'):
            stream = io.BytesIO(bundle)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(stream, 'a') as z:
                    z.writestr(extra, 'synthetic')
            with self.assertRaises(ValueError):
                snapshot.verify(stream.getvalue(), tag)
        stream = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(stream, 'w') as target:
            for name in source.namelist():
                target.writestr(name, source.read(name) + (b'\n' if name == 'NOTICE.md' else b''))
        with self.assertRaises(ValueError):
            snapshot.verify(stream.getvalue(), tag)

    def test_rollback_extracts_only_to_new_directory(self):
        tag, _, bundle = snapshot.build(checks.ROOT, REVISION)
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d) / 'rollback'
            snapshot.extract(bundle, tag, destination)
            original = (destination / checks.PUBLIC).read_bytes()
            with self.assertRaises(ValueError):
                snapshot.extract(bundle, tag, destination)
            self.assertEqual((destination / checks.PUBLIC).read_bytes(), original)

class FakeGitHub:
    def __init__(self):
        self.release = None
        self.assets = {}
        self.calls = []
        self.fail_once = False

    def __call__(self, *args):
        self.calls.append(args)
        if args == ('list',):
            return json.dumps([[self.release] if self.release else []])
        operation, tag = args[1:3]
        if operation == 'create':
            self.release = {'tag_name': tag, 'draft': True, 'target_commitish': args[args.index('--target') + 1]}
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError('simulated incomplete asset upload')
            self.assets = {p.name: p.read_bytes() for p in args[3:5]}
        elif operation == 'upload':
            assert self.release['draft']
            self.assets = {p.name: p.read_bytes() for p in args[3:5]}
        elif operation == 'download':
            destination = args[args.index('--dir') + 1]
            for name, body in self.assets.items():
                (destination / name).write_bytes(body)
        elif operation == 'edit':
            assert self.assets
            self.release['draft'] = False
        else:
            raise AssertionError(operation)
        return ''

class Publishing(unittest.TestCase):
    def test_draft_verified_before_publish_and_retry_is_idempotent(self):
        remote = FakeGitHub()
        url = publish(checks.ROOT, REVISION, remote)
        self.assertIn('/releases/tag/rules-', url)
        self.assertFalse(remote.release['draft'])
        operations = [c[1] for c in remote.calls if c[0] != 'list']
        self.assertEqual(operations, ['create', 'download', 'edit'])
        remote.calls.clear()
        self.assertEqual(publish(checks.ROOT, REVISION, remote), url)
        self.assertEqual([c[1] for c in remote.calls if c[0] != 'list'], ['download'])

    def test_incomplete_draft_is_retryable(self):
        remote = FakeGitHub()
        remote.fail_once = True
        with self.assertRaises(RuntimeError):
            publish(checks.ROOT, REVISION, remote)
        self.assertTrue(remote.release['draft'])
        publish(checks.ROOT, REVISION, remote)
        self.assertFalse(remote.release['draft'])

    def test_published_mismatch_is_never_overwritten(self):
        remote = FakeGitHub()
        publish(checks.ROOT, REVISION, remote)
        remote.assets['snapshot.zip'] = b'synthetic corrupt snapshot'
        remote.calls.clear()
        with self.assertRaises(ValueError):
            publish(checks.ROOT, REVISION, remote)
        self.assertFalse(remote.release['draft'])
        self.assertEqual([c[1] for c in remote.calls if c[0] != 'list'], ['download'])

if __name__ == '__main__':
    unittest.main()
