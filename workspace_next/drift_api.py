"""Read-only drift observations for the workspace (written by backend/drift_monitor.py; nothing here scores)."""
from datetime import datetime, timezone
import json

from fastapi import APIRouter

from backend import event_store as store
from backend.baseline_scorer import MYT

router = APIRouter()


def _latest(alert_type, where='', args=()):
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute(f'SELECT user_id,day,title,details FROM alerts WHERE alert_type={store._PH}{where} ORDER BY day DESC,id DESC',
                    (alert_type, *args))
        rows = store._rows(cur)
    out = {}
    for r in rows:
        if r['user_id'] in out:
            continue
        try:
            d = json.loads(r['details'] or '{}')
        except ValueError:
            d = {}
        out[r['user_id']] = {'day': r['day'], 'facts': d.get('facts', []), 'fired': d.get('fired', []),
                             'windows': d.get('windows'), 'monitoring_infrastructure': bool(d.get('monitoring_infrastructure'))}
    return out


@router.get('/workspace/drift')
def behaviour_drift(account: str):
    """Newest behaviour-drift observation for one account, or {'drift': null}."""
    return {'drift': _latest('behaviour_drift', f' AND user_id={store._PH}', (account,)).get(account)}


@router.get('/workspace/source-drift')
def source_drift_today():
    """Today's (MYT) source-drift observations per provider."""
    today = datetime.now(timezone.utc).astimezone(MYT).date().isoformat()
    return {'day': today, 'sources': {k: v for k, v in _latest('source_drift', f' AND day={store._PH}', (today,)).items()}}
