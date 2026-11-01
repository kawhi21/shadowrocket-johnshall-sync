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
            ''.join(f'DOMAIN-SUFFIX,proxy{i}.example,PROXY\n' for i in range(10)) +
            ''.join(f'DOMAIN-SUFFIX,ad{i}.example,REJECT\n' for i in range(10000)) +
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
            previous = {f.name: f.read_bytes() for f in p.parent.iterdir()}
            for invalid in cases:
                with self.subTest(size=len(invalid)):
                    with self.assertRaises(m.ValidationError):
                        m.sync(p, lambda: invalid)
                    self.assertEqual({f.name: f.read_bytes() for f in p.parent.iterdir()}, previous)

    def test_order_and_allowlisted_output(self):
        b = fixture().replace(b'GEOIP,CN,DIRECT', b'IP-CIDR,2001:db8::/32,REJECT\nGEOIP,CN,DIRECT')
        outputs = m.build_outputs(b)
        _, original = m.parse_and_validate(b)
        rebuilt = []
        for filename, policy in [('proxy.list', 'PROXY'), ('reject.list', 'REJECT')]:
            for line in outputs[filename].decode().splitlines():
                if line.startswith('#'):
                    continue
                kind, value = line.split(',')
                if kind == 'IP-CIDR6':
                    kind = 'IP-CIDR'
                rebuilt.append((kind, value.upper(), policy))
        rebuilt.extend([('GEOIP', 'CN', 'DIRECT'), ('FINAL', 'PROXY')])
        self.assertEqual(original, rebuilt)
        self.assertIn(b'IP-CIDR6,2001:db8::/32', outputs['reject.list'])
        for data in outputs.values():
            self.assertNotIn(b'dns-server', data)
            self.assertNotIn(b'[MITM]', data)

    def test_policy_topology_change_rejected(self):
        b = fixture().replace(b'DOMAIN-SUFFIX,ad1.example,REJECT', b'DOMAIN-SUFFIX,ad1.example,PROXY')
        with self.assertRaises(m.ValidationError):
            m.build_outputs(b)

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
