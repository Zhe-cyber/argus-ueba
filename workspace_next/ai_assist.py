"""On-demand AI suggestion for one baseline finding (Gemini / DeepSeek / Groq via backend.ai_suggest).

Advisory only: it never changes a score, tier or status, and it is called only when an analyst clicks. The prompt
holds just the finding's own score, signal breakdown and fact strings, masked (account ids, IPs, e-mails, opaque ids).
"""
import hashlib
import json
import os
import re
from pathlib import Path

from backend import ai_suggest
from backend.baseline_scorer import WEIGHTS

KEYS = ('GEMINI_API_KEY', 'DEEPSEEK_API_KEY', 'GROQ_API_KEY')
LABELS = {'new_action': 'New actions', 'new_resource': 'New resources', 'unusual_hours': 'Unusual hours',
          'volume': 'Volume', 'sensitive_new': 'New sensitive resource'}
PROVIDERS = {'aws_cloudtrail': 'AWS CloudTrail', 'cloudflare_access': 'Cloudflare Access', 'github_audit': 'GitHub audit log'}
_cache = {}  # ponytail: in-process cache, lost on restart; fine for on-demand demo use


def load_keys(path):
    """Copy only the provider key lines from an env file (never DATABASE_URL or anything else)."""
    if not path or not Path(path).is_file():
        return
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        name, _, value = line.partition('=')
        if name.strip() in KEYS and value.strip() and not os.environ.get(name.strip()):
            os.environ[name.strip()] = value.strip().strip('"\'')


def mask(text):
    text = re.sub(r'[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,}', '<email>', str(text))
    text = re.sub(r'\b\d{12}\b', '<account>', text)
    text = re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', '<ip>', text)
    text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<id>', text, flags=re.I)
    return re.sub(r'\b[0-9a-f]{32,}\b', '<id>', text, flags=re.I)


def breakdown(signals):
    avail = {k: v for k, v in (signals or {}).items() if v is not None and k in WEIGHTS}
    total = sum(WEIGHTS[k] for k in avail)
    return [f'{LABELS[k]}: +{100 * WEIGHTS[k] * v / total:.0f} of {100 * WEIGHTS[k] / total:.0f}'
            for k, v in avail.items()] if total else []


def prompt(finding):
    d = finding.get('details') or {}
    facts = '\n'.join('- ' + mask(f) for f in d.get('facts', [])) or '- (none)'
    parts = '\n'.join('- ' + p for p in breakdown(d.get('signals'))) or '- (not available)'
    return f"""You help a security analyst at a small organisation review ONE finding from Argus, an explainable
behaviour-analytics tool. The score below is fixed and already explained by the facts. Do not re-score it, do not
invent events, and do not claim an attack happened. Use only the facts given; where something is not in them, say
what to check instead of assuming.

Finding: {mask(finding.get('title', ''))}
Log source: {PROVIDERS.get(d.get('source'), mask(d.get('source') or 'unknown'))}
Day (Malaysia time): {d.get('day')}
Score: {d.get('score')}/100, tier {d.get('tier')}, compared with this account's own previous 28 days
({d.get('history_days')} prior active days, {d.get('events_today')} events that day).
How the score adds up:
{parts}
Facts:
{facts}

Reply in plain English, under 170 words, with exactly these sections:
**What this means:** one or two sentences.
**Check first:** three numbered steps, each naming the exact place to look (for example the provider's event history
filtered to this account and day).
**Likely harmless if:** one or two bullets.
**Escalate if:** one or two bullets.
**Suggested status:** one of Acknowledge / Resolve / False positive / Open a case, with a one-line reason."""


def suggest(finding):
    """{'text', 'model'}; raises RuntimeError when no provider is configured or all fail."""
    if finding.get('origin') != 'baseline' or not (finding.get('details') or {}).get('facts'):
        raise ValueError('AI suggestions are available for baseline findings with facts')
    text = prompt(finding)
    key = (finding['id'], hashlib.sha256(text.encode()).hexdigest())
    if key not in _cache:
        tasks = ai_suggest._collect_tasks(text)  # Gemini, then DeepSeek, then Groq: first answer wins
        if not tasks:
            raise RuntimeError('No AI provider key configured')
        errors = []
        for model, call in tasks.items():
            try:
                _cache[key] = {'text': call().strip(), 'model': model}
                break
            except Exception as error:  # noqa: BLE001 - try the next provider
                errors.append(f'{model}: {type(error).__name__}')
        else:
            raise RuntimeError('All AI providers failed (' + ', '.join(errors) + ')')
    return {**_cache[key], 'advisory': True, 'masked': True}


if __name__ == '__main__':
    assert mask('acct 123456789012 from 10.1.2.3 by a.b@c.com id 0123456789abcdef0123456789abcdef') == \
        'acct <account> from <ip> by <email> id <id>'
    assert breakdown({'new_action': 1, 'new_resource': None, 'unusual_hours': 0, 'volume': 0, 'sensitive_new': 0})[0] == \
        'New actions: +33 of 33'
    p = prompt({'title': 'x', 'details': {'facts': ['1 action kind(s) never seen: 123456789012'], 'signals': {}}})
    assert '123456789012' not in p and '<account>' in p
    print(json.dumps({'self_check': 'ok'}))
