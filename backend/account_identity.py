"""Source-scoped native principals; labels never establish cross-provider identity."""
import hashlib
import json
import os
import re


def enabled():
    return os.getenv('ARGUS_ACCOUNT_KEYS') == 'source-principal-v1'


def is_key(value):
    return isinstance(value, str) and re.fullmatch(r'acct_[0-9a-f]{64}', value) is not None


def identify(event):
    """Resolve only native evidence; None means insufficient identity evidence."""
    source, namespace = event.get('source'), event.get('source_account_id')
    meta = event.get('metadata') or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (ValueError, TypeError):
            return None
    if not isinstance(meta, dict) or not isinstance(namespace, str) or not namespace.strip():
        return None
    label = str(event.get('user') or '')
    owner, principal, kind, basis = namespace, None, 'account', None
    if source == 'aws_cloudtrail':
        identity = meta.get('userIdentity')
        if not isinstance(identity, dict):
            return None
        owner = str(identity.get('accountId') or namespace)
        identity_type = identity.get('type')
        if identity_type == 'Root':
            principal, kind, basis, label = 'root', 'root', 'aws_account_root', 'AWS root'
        elif identity_type == 'AssumedRole':
            context = identity.get('sessionContext') or {}
            issuer = context.get('sessionIssuer') if isinstance(context, dict) else None
            if isinstance(issuer, dict) and issuer.get('type') == 'Role' and issuer.get('principalId'):
                principal = str(issuer['principalId'])
                label = str(issuer.get('userName') or issuer.get('arn') or label)
                basis = 'aws_role_issuer_id'
            else:
                native = identity.get('principalId')
                if isinstance(native, str) and re.fullmatch(r'AROA[A-Z0-9]+:.+', native):
                    principal, basis = native.split(':', 1)[0], 'aws_role_principal_prefix'
                    label = principal
            kind = 'role'
        elif identity_type in {'IAMUser', 'FederatedUser'} and identity.get('principalId'):
            principal, kind, basis = str(identity['principalId']), identity_type, 'aws_principal_id'
            label = str(identity.get('userName') or identity.get('arn') or label)
        elif identity_type == 'AWSService' and identity.get('invokedBy'):
            principal, kind, basis = str(identity['invokedBy']), 'service', 'aws_service_principal'
            label = principal
    elif source == 'github_events':
        actor = meta.get('actor_id')
        if type(actor) is int and actor > 0:
            principal, basis = str(actor), 'github_actor_id'
    elif source == 'cloudflare_access':
        if meta.get('connection') == 'nonidentity':
            client_id = meta.get('service_client_id')
            if isinstance(client_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.access', client_id):
                principal, basis, kind = client_id, 'cloudflare_service_client_id', 'service_token'
                label = 'Cloudflare service ' + client_id[:8]
        else:
            user_id = meta.get('user_id')
            if isinstance(user_id, str) and user_id.strip():
                principal, basis = user_id, 'cloudflare_user_id'
    if not principal or not basis:
        return None
    value = ['source-principal-v1', source, namespace, owner, kind, principal]
    key = 'acct_' + hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return {'account_key': key, 'account_label': label or principal,
            'account_kind': kind, 'account_basis': basis}
