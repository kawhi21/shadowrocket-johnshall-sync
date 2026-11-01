"""Validate public upstream in memory; publish fixed-schema metadata only."""
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

def validate(body):
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
    # Only fixed keys, numeric counts and a content hash cross the publication boundary.
    return {'schema_version': 1, 'source': SOURCE, 'validation': 'passed',
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
            'rule_count': len(rules), 'rule_types': dict(sorted(counts.items())),
            'policies': dict(sorted(policies.items()))}

def sync(destination, fetch=download):
    report = validate(fetch())  # No output mutation before all checks pass.
    content = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    destination = Path(destination)
    if destination.exists() and destination.read_bytes() == content:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.report-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True

if __name__ == '__main__':
    try:
        changed = sync('generated/validation.json')
        print('Validation passed; metadata updated.' if changed else 'Validation passed; unchanged.')
    except Exception:
        # Never echo downloaded bytes, remote errors, credentials or response headers.
        print('Sync failed; last-known-good metadata preserved.', file=sys.stderr)
        sys.exit(1)
