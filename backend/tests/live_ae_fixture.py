"""Test-only comparator bundles and persona events for the live autoencoder (never pilot evidence).

make_bundle() writes an untrained, seeded 9-6-3-6-9 model in the v2 bundle layout so load() accepts it; tests that
need it as the live comparator pin its manifest sha256 (monkeypatching live_ae.EXPECTED_MANIFEST_SHA256)."""
from backend import live_ae

ACCOUNT, STACK = '1' * 12, 'argus-lab'  # synthetic scope


def make_bundle(out, run_kind='controlled_lab', seed=0, threshold=0.5):
    """Write the bundle into the fresh directory `out`; returns its manifest sha256."""
    import torch
    torch.manual_seed(seed)
    model = live_ae.build_model()
    out.mkdir(parents=True)
    torch.save({'profile': live_ae.PROFILE, 'features': live_ae.FEATURES, 'state_dict': model.state_dict()}, out / 'weights.pt')
    n = len(live_ae.FEATURES)
    (out / 'scaler.json').write_bytes(live_ae.canonical({'mean': [0.0] * n, 'scale': [1.0] * n, 'transform': 'standardise',
                                                         'constant_features': []}))
    manifest = {'profile': live_ae.PROFILE, 'model_version': live_ae.MODEL_VERSION, 'purpose': 'test fixture',
                'features': live_ae.FEATURES, 'feature_contract_sha256': live_ae.CONTRACT_SHA, 'method': live_ae.METHOD,
                'run_kind': run_kind, 'threshold': threshold,
                'artifact_sha256': {name: live_ae.sha(out / name) for name in live_ae.ARTIFACTS}}
    (out / 'manifest.json').write_bytes(live_ae.canonical(manifest))
    return live_ae.sha(out / 'manifest.json')


def persona_event(n, when, name='GetObject', bucket='argus-lab-b1', persona='persona-01'):
    """An /ingest body: S3 call by the lab persona's assumed role (in live_ae.scope)."""
    role = f'{STACK}-{persona}'
    return {'source': 'aws_cloudtrail', 'source_account_id': ACCOUNT, 'event': {
        'eventID': f'persona-{n}', 'eventTime': when, 'eventName': name, 'eventSource': 's3.amazonaws.com',
        'recipientAccountId': ACCOUNT, 'requestParameters': {'bucketName': bucket},
        'userIdentity': {'type': 'AssumedRole', 'arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{role}/session',
                         'principalId': 'AROATESTPERSONA:session', 'accountId': ACCOUNT,
                         'sessionContext': {'sessionIssuer': {'type': 'Role', 'principalId': 'AROATESTPERSONA',
                                                              'arn': f'arn:aws:iam::{ACCOUNT}:role/{role}',
                                                              'userName': role}}}}}


def persona_stream():
    """Six active October days for one persona (so the sixth is scorable by both scorers)."""
    return [persona_event(f'{d}-{i}', f'2026-10-{d:02d}T02:{i:02d}:00Z') for d in range(10, 16) for i in range(3)]

