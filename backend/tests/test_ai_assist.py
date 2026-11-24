import pytest
from workspace_next import ai_assist

FINDING = {'id': 7, 'origin': 'baseline', 'title': 'Baseline risk High (87): role 123456789012',
           'details': {'source': 'aws_cloudtrail', 'day': '2026-11-15', 'score': 87, 'tier': 'High', 'history_days': 16,
                       'events_today': 35, 'facts': ['1 action kind(s) never seen in the last 28 days: ListObjects from 10.0.0.1'],
                       'signals': {'new_action': 0.6, 'new_resource': 0.9, 'unusual_hours': 1.0, 'volume': 1.0, 'sensitive_new': 0.9}}}


def test_falls_back_masks_and_caches(monkeypatch):
    ai_assist._cache.clear()
    seen, calls = [], []
    def broken(): calls.append('a'); raise TimeoutError
    def works(): calls.append('b'); return ' plan '
    def tasks(prompt):
        seen.append(prompt)
        return {'Gemini-2.5': broken, 'Groq-Llama': works}
    monkeypatch.setattr(ai_assist.ai_suggest, '_collect_tasks', tasks)
    assert ai_assist.suggest(FINDING) == {'text': 'plan', 'model': 'Groq-Llama', 'advisory': True, 'masked': True}
    assert '123456789012' not in seen[0] and '10.0.0.1' not in seen[0] and 'Unusual hours: +20 of 20' in seen[0]
    ai_assist.suggest(FINDING)
    assert calls == ['a', 'b']  # second call served from cache


def test_only_baseline_findings_and_errors(monkeypatch):
    with pytest.raises(ValueError):
        ai_assist.suggest({**FINDING, 'origin': 'rule'})
    ai_assist._cache.clear()
    monkeypatch.setattr(ai_assist.ai_suggest, '_collect_tasks', lambda p: {})
    with pytest.raises(RuntimeError):
        ai_assist.suggest(FINDING)


def test_load_keys_reads_only_provider_keys(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('DATABASE_URL=postgres://x\nGEMINI_API_KEY="k1"\nOTHER=1\n')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite-local')
    ai_assist.load_keys(env)
    import os
    assert os.environ['GEMINI_API_KEY'] == 'k1' and os.environ['DATABASE_URL'] == 'sqlite-local' and 'OTHER' not in os.environ
