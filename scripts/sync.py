"""Publish validated, credential-free routing lists; never publish a proxy config."""
import collections
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request

SOURCE = 'https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip_ad.conf'
MIN_BYTES, MAX_BYTES = 100_000, 8_000_000

class ValidationError(Exception):
    pass

def require(ok):
    if not ok:
        raise ValidationError('Upstream validation failed; previous report preserved.')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError('Unexpected redirect rejected.')

def download():
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(SOURCE, headers={'User-Agent': 'johnshall-metadata-validator/1'})
    with opener.open(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == SOURCE)
        require(response.headers.get_content_type() in ('text/plain', 'application/octet-stream'))
        body = response.read(MAX_BYTES + 1)
    require(MIN_BYTES <= len(body) <= MAX_BYTES)
    return body

def parse_and_validate(body):
    require(MIN_BYTES <= len(body) <= MAX_BYTES)
    try:
        text = body.decode('utf-8-sig')
    except UnicodeError:
        raise ValidationError('Invalid encoding.') from None
    require(not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text))
    # Fail closed on node/credential markers, including otherwise ignored sections.
    require(not re.search(r'(?i)(?:ss|ssr|vmess|vless|trojan|hysteria2?)://|password\s*[:=]|passwd\s*[:=]|private[-_ ]?key\s*[:=]|subscription\s*[:=]|ai-stable|<!doctype|<html', text))
    sections = []
    rules = []
    section = None
    counts = collections.Counter()
    policies = collections.Counter()
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('['):
            require(line in ('[General]', '[Rule]', '[URL Rewrite]', '[MITM]') and line not in sections)
            sections.append(line)
            section = line
            continue
        require(section is not None and len(line) < 4096)
        if section != '[Rule]':
            continue
        parts = [p.strip() for p in line.split(',')]
        kind = parts[0].upper()
        require(kind in ('DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'GEOIP', 'FINAL'))
        require(len(parts) == (2 if kind == 'FINAL' else 3))
        policy = parts[-1].upper()
        require(policy in ('DIRECT', 'PROXY', 'REJECT'))
        if kind == 'DOMAIN-SUFFIX':
            require(bool(re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', parts[1])))
        elif kind == 'DOMAIN-KEYWORD':
            require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', parts[1])))
        elif kind == 'IP-CIDR':
            try:
                ipaddress.ip_network(parts[1], strict=False)
            except ValueError:
                raise ValidationError('Invalid CIDR.') from None
        elif kind == 'GEOIP':
            require(parts[1].upper() == 'CN' and policy == 'DIRECT')
        counts[kind] += 1
        policies[policy] += 1
        rules.append(tuple(p.upper() for p in parts))
    require(sections == ['[General]', '[Rule]', '[URL Rewrite]', '[MITM]'])
    require(10_000 <= len(rules) <= 200_000)
    require(counts['FINAL'] == 1 and counts['GEOIP'] == 1)
    require(rules[-1] == ('FINAL', 'PROXY'))
    require(('GEOIP', 'CN', 'DIRECT') in rules)
    require(policies['REJECT'] >= 1000 and policies['PROXY'] >= 10)
    report = {'schema_version': 2, 'source': SOURCE, 'validation': 'passed',
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
            'rule_count': len(rules), 'rule_types': dict(sorted(counts.items())),
            'policies': dict(sorted(policies.items()))}
    return report, rules

def validate(body):
    return parse_and_validate(body)[0]

def build_outputs(body):
    report, rules = parse_and_validate(body)
    # A fixed local RULE-SET wrapper can preserve upstream order only for this topology.
    # Fail closed if upstream ever interleaves policies or changes the CN/final tail.
    phases = []
    for rule in rules:
        if not phases or phases[-1] != rule[-1]:
            phases.append(rule[-1])
    require(phases == ['PROXY', 'REJECT', 'DIRECT', 'PROXY'])
    require(rules[-2:] == [('GEOIP', 'CN', 'DIRECT'), ('FINAL', 'PROXY')])
    header = ('# Derived from Johnshall/Shadowrocket-ADBlock-Rules-Forever\n'
              '# License: CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/\n'
              '# Modified: routing-only, comments/settings removed, IPv6 type normalized.\n')
    outputs = {}
    for policy, name in [('PROXY', 'proxy.list'), ('REJECT', 'reject.list')]:
        lines = []
        for rule in rules[:-2]:
            if rule[-1] != policy:
                continue
            kind, value = rule[:-1]
            if kind == 'IP-CIDR' and ':' in value:
                kind = 'IP-CIDR6'
            lines.append(f'{kind},{value.lower()}')
        outputs[name] = (header + '\n'.join(lines) + '\n').encode()
    report['outputs'] = {name: {'sha256': hashlib.sha256(data).hexdigest(),
                              'bytes': len(data)} for name, data in outputs.items()}
    outputs['validation.json'] = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    return outputs

def sync(destination, fetch=download):
    outputs = build_outputs(fetch())  # No mutation before every validation passes.
    directory = Path(destination).parent
    if all((directory / name).exists() and (directory / name).read_bytes() == data
           for name, data in outputs.items()):
        return False
    directory.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for filename, data in outputs.items():
            fd, name = tempfile.mkstemp(prefix='.validated-', dir=directory)
            staged.append((name, directory / filename))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
        for name, target in staged:
            os.replace(name, target)
    finally:
        for name, _ in staged:
            if os.path.exists(name):
                os.unlink(name)
    return True

if __name__ == '__main__':
    try:
        changed = sync('generated/validation.json')
        print('Validation passed; routing lists updated.' if changed else 'Validation passed; unchanged.')
    except Exception:
        # Never echo downloaded bytes, remote errors, credentials or response headers.
        print('Sync failed; last-known-good metadata preserved.', file=sys.stderr)
        sys.exit(1)
