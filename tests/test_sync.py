import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/sync.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture():
    return ('[General]\ndns-server = system\n[Rule]\n' +
            ''.join(f'DOMAIN-SUFFIX,ad{i}.example,REJECT\n' for i in range(10000)) +
            ''.join(f'DOMAIN-SUFFIX,proxy{i}.example,PROXY\n' for i in range(10)) +
            'GEOIP,CN,DIRECT\nFINAL,PROXY\n[URL Rewrite]\n[MITM]\n').encode()

class Tests(unittest.TestCase):
    def test_success_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'validation.json'
            self.assertTrue(m.sync(p, fixture))
            self.assertFalse(m.sync(p, fixture))
            r = json.loads(p.read_text())
            self.assertEqual(r['rule_count'], 10012)
            self.assertNotIn('ad0.example', p.read_text())

    def test_failures_preserve_last_good(self):
        b = fixture()
        cases = [b'', b'<html>' * 20000, b'\xff' * 100001, b'x' * (m.MAX_BYTES + 1),
                 b.replace(b'[MITM]', b'[Proxy]'), b.replace(b'GEOIP,CN,DIRECT', b'GEOIP,CN,PROXY'),
                 b.replace(b'FINAL,PROXY', b'FINAL,DIRECT'),
                 b + b'\npassword = synthetic-secret\n', b + b'\nvmess://synthetic\n',
                 b.replace(b'ad0.example', b'bad@example'), b.replace(b'REJECT', b'PRIVATE')]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'validation.json'
            m.sync(p, fixture)
            previous = p.read_bytes()
            for invalid in cases:
                with self.subTest(size=len(invalid)):
                    with self.assertRaises(m.ValidationError):
                        m.sync(p, lambda: invalid)
                    self.assertEqual(p.read_bytes(), previous)

    def test_network_failure_preserves_output(self):
        def fail():
            raise TimeoutError('synthetic')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'validation.json'
            p.write_bytes(b'last good')
            with self.assertRaises(TimeoutError):
                m.sync(p, fail)
            self.assertEqual(p.read_bytes(), b'last good')

    def test_redirect_rejected(self):
        with self.assertRaises(m.ValidationError):
            m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com/')

if __name__ == '__main__':
    unittest.main()
