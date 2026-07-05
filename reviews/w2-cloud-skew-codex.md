No confident correctness findings in this diff.

The change appears consistent with the stated train/serve contract: serving now scores the latest UTC user-day and passes strictly earlier events as history, which fixes the `new_action_count` skew without changing the frozen 12-dim cloud feature order or public API fields.

VERDICT: APPROVE
