"""GitHub missing counts must not become fabricated zero-count observations."""
import copy

import pytest

from backend.normalizer import SOURCE_GITHUB, normalize


@pytest.mark.parametrize("payload", [
    {}, {"size": None}, {"size": False}, {"size": True}, {"size": -1},
    {"size": "3"}, {"size": 3.0}, {"size": []}, {"size": {}},
    {"commits": [{"sha": "example"}]},
])
def test_unknown_push_count_is_not_zero(payload):
    event = {"id": "native-push-id", "type": "PushEvent", "payload": payload}
    before = copy.deepcopy(event)
    result = normalize(event, SOURCE_GITHUB)
    assert result["action"] == "Code push"
    assert result["metadata"]["commit_count_status"] == "unknown"
    assert "commits" not in result["metadata"]
    assert result["raw"] == before
    assert event == before
    assert result["metadata"]["event_id"] == "native-push-id"


@pytest.mark.parametrize("size,label", [(0, "0 commits"), (1, "1 commit"), (7, "7 commits")])
def test_explicit_push_count_is_preserved(size, label):
    result = normalize({"type": "PushEvent", "payload": {"size": size}}, SOURCE_GITHUB)
    assert result["action"] == f"Code push ({label})"
    assert result["metadata"]["commits"] == size
    assert result["metadata"]["commit_count_status"] == "known"


def test_non_push_action_is_unchanged():
    result = normalize({"type": "IssueCommentEvent", "payload": {}}, SOURCE_GITHUB)
    assert result["action"] == "Issue comment"
    assert "commit_count_status" not in result["metadata"]
