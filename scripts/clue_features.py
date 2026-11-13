"""clue_behavior_v1: isolated ten-feature offline benchmark contract.

Dataset: Landauer et al., CLUE-LDS, DOI 10.5281/zenodo.7119953, CC BY 4.0.
No AWS/CERT runtime registration. Native event types retain their exact spelling.
"""
from datetime import datetime, timezone
import hashlib

PROFILE = 'clue_behavior_v1'
FEATURES = ['event_count', 'unique_actions', 'unique_paths', 'utc_off_hours_events',
            'new_action_count', 'file_access_events', 'login_attempt_events',
            'login_success_events', 'sharing_events', 'permission_change_events']
SHARING = frozenset(f'{prefix}_{kind}' for prefix in ('shared', 'unshared')
                    for kind in ('email', 'group', 'link', 'user'))
# Table III of the authors' paper; underscore spellings observed in native JSON.
KNOWN_ACTIONS = frozenset('''admin_settings_changed app_disabled app_enabled command_executed
email_changed fullname_changed password_changed permission_changed public_share_accessed
public_share_expiration_date_changed public_share_password_changed public_share_update_permission
version_deleted version_restored quota_changed comment_added comment_deleted file_accessed
file_copied file_created file_deleted file_renamed file_updated file_written deleted_from_trashbin
restored_from_trashbin group_created group_deleted user_became_groupadmin groupadmin_removed_from_group
login_attempt login_failed login_successful logout_occurred user_added_to_group user_assign
user_created user_data_viewed user_deleted user_disabled user_removed_from_group'''.split()) | SHARING | {'logout_occured'}
REQUIRED_PATH = frozenset({'file_accessed', 'file_deleted', 'file_updated', 'permission_changed',
                           'version_deleted', 'deleted_from_trashbin', 'comment_added', 'comment_deleted',
                           'public_share_update_permission'})


def instant(value):
    if not isinstance(value, str):
        raise ValueError('CLUE timestamp must be a string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('CLUE timestamp must have a timezone')
    return result.astimezone(timezone.utc)


class Window:
    def __init__(self):
        self.counts = dict.fromkeys(FEATURES, 0)
        self.actions, self.paths = set(), set()
        self.path_events = self.missing_required_paths = self.unknown_actions = 0

    def add(self, row):
        timestamp = instant(row['time'])
        action = row['type']
        if not isinstance(action, str) or not action or len(action) > 128:
            raise ValueError('Invalid native action')
        params = row.get('params', {})
        if not isinstance(params, dict):
            raise ValueError('Invalid params object')
        path = params.get('path')
        if path is not None and not isinstance(path, str):
            raise ValueError('Invalid path field')
        self.counts['event_count'] += 1
        self.counts['utc_off_hours_events'] += timestamp.weekday() >= 5 or not 7 <= timestamp.hour < 19
        self.counts['file_access_events'] += action == 'file_accessed'
        self.counts['login_attempt_events'] += action == 'login_attempt'
        self.counts['login_success_events'] += action == 'login_successful'
        self.counts['sharing_events'] += action in SHARING
        self.counts['permission_change_events'] += action == 'permission_changed'
        self.actions.add(action)
        self.unknown_actions += action not in KNOWN_ACTIONS
        self.missing_required_paths += action in REQUIRED_PATH and not path
        if path:
            self.path_events += 1
            self.paths.add(hashlib.sha256(path.encode()).digest())

    def finish(self, prior_actions):
        result = dict(self.counts)
        result['unique_actions'] = len(self.actions)
        result['unique_paths'] = len(self.paths)
        result['new_action_count'] = len(self.actions - prior_actions)
        return result
