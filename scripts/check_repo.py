"""Offline checks for public templates, generated data and common credential leaks."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
AI_MATCHES = [('DOMAIN-SUFFIX', 'muse.ai'), ('DOMAIN', 'hatch.metaaivm.com'),
              ('DOMAIN-SUFFIX', 'chatgpt.com'), ('DOMAIN-SUFFIX', 'openai.com'),
              ('DOMAIN-SUFFIX', 'oaistatic.com'), ('DOMAIN-SUFFIX', 'oaiusercontent.com'),
              ('DOMAIN-SUFFIX', 'claude.ai'), ('DOMAIN-SUFFIX', 'anthropic.com'),
              ('DOMAIN-SUFFIX', 'gemini.google.com')]
PUBLIC = 'templates/Public-Starter.conf'
PUBLIC_AI = 'templates/AI-Public.sgmodule'
PERSONAL = 'templates/personal/Johnshall-AI-Extended.conf.example'
PERSONAL_AI = 'templates/personal/AI-Stable-Routing.sgmodule.example'
BASE_URL = 'https://raw.githubusercontent.com/kawhi21/shadowrocket-johnshall-sync/main/generated/'
EXPECTED_RULES = [f'RULE-SET,{BASE_URL}proxy.list,PROXY',
                  f'RULE-SET,{BASE_URL}reject.list,REJECT', 'GEOIP,CN,DIRECT', 'FINAL,PROXY']

def sections(text):
    result = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            if line in result:
                raise ValueError('Duplicate section')
            result[line] = []
            current = line
        elif current is None:
            raise ValueError('Content outside section')
        else:
            result[current].append(line)
    return result

def check_templates(root=ROOT):
    for filename in [PUBLIC, 'templates/Johnshall-Auto-Rules.conf',
                     'templates/Johnshall-Auto-Rules.conf.example']:
        data = sections((root / filename).read_text(encoding='utf-8-sig'))
        if set(data) != {'[General]', '[Rule]'} or data['[Rule]'] != EXPECTED_RULES:
            raise ValueError('Public routing order or policy changed')
        if any(line.split('=', 1)[0].strip() in ('update-url', 'include')
               for line in data['[General]']):
            raise ValueError('Public base must be local and independent')
    for filename, policy in [(PUBLIC_AI, 'PROXY'), (PERSONAL_AI, 'AI-Stable')]:
        data = sections((root / filename).read_text(encoding='utf-8'))
        expected = [','.join((*match, policy)) for match in AI_MATCHES]
        if data != {'[Rule]': expected}:
            raise ValueError('AI module targets or domains changed')
    overlay = sections((root / PERSONAL).read_text(encoding='utf-8'))
    if overlay != {'[General]': ['include = Johnshall-Auto-Rules.conf'],
                   '[Proxy Group]': ['AI-Stable = select, PROXY']}:
        raise ValueError('Personal template contains a nonlocal binding')

def check_generated(root=ROOT):
    report = json.loads((root / 'generated/validation.json').read_bytes())
    if report.get('schema_version') != 2 or report.get('validation') != 'passed':
        raise ValueError('Invalid validation report')
    if report.get('source') != ('https://raw.githubusercontent.com/Johnshall/'
                              'Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip_ad.conf'):
        raise ValueError('Unexpected upstream')
    if not re.fullmatch(r'[0-9a-f]{64}', report.get('sha256', '')) or not 100_000 <= report.get('bytes', 0) <= 8_000_000:
        raise ValueError('Invalid source identity')
    if not 10_000 <= report.get('rule_count', 0) <= 200_000 or report['policies'].get('REJECT', 0) < 1000 or report['policies'].get('PROXY', 0) < 10:
        raise ValueError('Unexpected rule population')
    from collections import Counter
    types = Counter()
    for name, policy in [('proxy.list', 'PROXY'), ('reject.list', 'REJECT')]:
        body = (root / 'generated' / name).read_bytes()
        if report['outputs'][name] != {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}:
            raise ValueError('Rule snapshot hash mismatch')
        count = 0
        for raw in body.decode('utf-8').splitlines():
            if not raw or raw.startswith('#'):
                continue
            fields = raw.split(',')
            if len(fields) != 2:
                raise ValueError('Remote list must contain type and value only')
            kind, value = fields
            if kind in ('IP-CIDR', 'IP-CIDR6'):
                network = ipaddress.ip_network(value, strict=False)
                if network.version != (4 if kind == 'IP-CIDR' else 6):
                    raise ValueError('CIDR family mismatch')
            elif kind not in ('DOMAIN-SUFFIX', 'DOMAIN-KEYWORD') or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
                raise ValueError('Unsafe rule field')
            types['IP-CIDR' if kind == 'IP-CIDR6' else kind] += 1
            count += 1
        if count != report['policies'][policy] - (1 if policy == 'PROXY' else 0):
            raise ValueError('Rule count mismatch')
    types.update({'FINAL': 1, 'GEOIP': 1})
    if dict(types) != report['rule_types'] or sum(types.values()) != report['rule_count']:
        raise ValueError('Rule type totals mismatch')
    if report['policies'].get('DIRECT') != 1:
        raise ValueError('CN direct tail changed')
    return report

def check_secrets(text, config=False):
    patterns = [r'(?i)(?:ss|ssr|vmess|vless|trojan|hysteria2?)://',
                r'(?i)https?://[^\s"\x27<>]+[?&](?:token|key|password|auth)=[^\s"\x27<>]+',
                r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b',
                r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
                r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----']
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError('Possible credential: content withheld')
    if config:
        active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('#', ';')))
        if re.search(r'(?im)^\s*\[Proxy\]\s*$|^\s*(?:password|server|uuid|private-key|certificate)\s*=', active):
            raise ValueError('Public config contains private connection data')

def check_repository(root=ROOT):
    for path in root.rglob('*'):
        if not path.is_file() or any(p in ('.git', '__pycache__', 'dist') for p in path.relative_to(root).parts):
            continue
        if any(p in ('private', 'backups') for p in path.relative_to(root).parts):
            raise ValueError('Private backup directory found in public source')
        check_secrets(path.read_text(encoding='utf-8-sig'),
                      any(s in path.name for s in ('.conf', '.sgmodule', '.list')))
    check_templates(root)
    check_generated(root)

if __name__ == '__main__':
    check_repository()
    print('Public templates, generated hashes and credential checks passed.')
