# W2: Controlled lab actors, real audit events

27 October 2026. Branch codex/w2-controlled-actors, stacked on PR #10.
User authorized continuing the agreed six-persona evaluation design. Model
training/activation is not part of this change. Existing models stay untouched.

Prepare a default-dry-run actor runner and reviewable AWS lab infrastructure.
Six neutral-named assumed roles represent distinct lab machine principals, not
six people or six independent GitHub/Cloudflare users. A separate bootstrap IAM
user can assume only those roles and inspect the named CloudTrail trail. Never
reuse or broaden the collector's permissions; never run actors as root.

Create seven private encrypted retained toy S3 buckets: six routine buckets and
one synthetic confidential archive. Roles may only read the fixed toy fixture
objects and bucket location. No IAM mutations, arbitrary service calls, writes,
credential access, outside resources, public buckets or unrestricted LLM tools.
The bootstrap user gets no access to real account data. No access key in a
CloudFormation resource/output. Any credential configuration is local only.

Add optional, default-off S3 read data-event logging to the existing trail,
restricted to the toy bucket ARNs. Keep management coverage intact. Actual
execution requires verified trail logging/data selectors, expected account,
non-root bootstrap identity, fixed lab resource names, bounded API calls and
one-shot termination. Preserve provider timestamps and wait for real native
events; never synthesize a provider log or inject a scenario label into ingest.

Plan deterministic normal routines, benign high-volume controls and a transition
in persona 06 after an earlier normal run. Ground-truth phase/seed/run metadata
stay in a private experiment manifest separate from detector inputs. Neutral
role session names remain stable across runs. Record only safe action/request-ID
evidence, never temporary credentials or downloaded content. Refuse transition
without a compatible successful prior normal manifest; this is a workflow gate,
not a claim of sufficient model baseline history or detection success.

Implementation scope: new lab template generator/template, setup wrapper and
bounded runner; optional live-trail selectors in infra/aws-live.json; requestID
preservation in AWS normalization for audit correlation (no feature changes);
isolated safety tests and docs. If privileged setup authentication is missing,
finish code, dry-run and tests before requesting a local CLI sign-in. Never ask
for passwords, keys or one-time authorization codes in chat.

Acceptance: dry-run needs no credentials/network; fixed allow-lists and request
budgets; reproducible plans; same role identity across phase change; no labels
sent to SDK/provider calls; no delete/write API executable by actors; account,
root, trail and selector refusal tests; template privilege/storage checks;
baseline-manifest validation. Run all tests with sqlite-local; validate the
CloudFormation template and execute only after setup authentication is available.
Do not claim multiple real cloud humans, weeks of data, AE accuracy, production
readiness, full multi-cloud identity linking or an implemented LLM agent swarm.
