# Controlled users and a compromised-account scenario

Proposed evaluation, not an implemented or completed experiment. The current
real integration uses the owner's cloud accounts. It does not yet create five
distinct people, run an AI agent swarm, or provide cross-provider person scores.

The user's idea fits Argus: create several regular routines, then change one
existing account's behaviour while its credentials remain valid. A newly created
"attacker" with no normal history is a weaker test of compromised-account UEBA.
MITRE describes valid cloud account abuse here:
https://attack.mitre.org/techniques/T1078/004/

## Starting design

Use six personas: five remain normal; the sixth first builds normal history and
then enters the controlled compromised-account phase. Personas
are workload generators, not automatically distinct provider users. Use neutral
account names; keep any compromise label in the separate experiment manifest.
Start with
repeatable scripts and seeded variation. An LLM may choose among bounded approved
actions later; it must not invent tools, targets, credentials or destructive steps.

| Routine | Normal behaviour | Controlled deviation |
| --- | --- | --- |
| Developer | Small changes in an owned test repository | Unusually broad activity in that same test scope |
| Reviewer | Read a small recurring set of test resources | Abrupt change in resource/action diversity |
| Operator | Regular limited cloud inventory checks | A bounded burst of unfamiliar read-only actions |
| Access user | Recurring sign-in to the protected demo | A separately verified unusual authentication context |
| Automation | Clearly labelled machine activity | A legitimate burst retained as a false-positive control |

These are scenario templates, not assertions that all actions are currently
permitted or logged. Confirm provider coverage before running each scenario. AWS
management logging does not automatically include S3 object reads; GitHub Events
is repository activity, not organization audit logging or an IP/geo feed; Cloudflare
Access authentication logs do not show in-session downloads or page actions.

## Real identities versus personas

Use approved, least-privilege test identities in owned resources. Multiple workers
using one GitHub token remain one GitHub identity. AWS assumed-role session names
can distinguish test sessions but are not proof of separate humans. Cloudflare
service tokens identify machines and should not be presented as human logins.
Do not automate personal account creation or bypass interactive MFA.

Record stable provider and account identifiers. Link them only with explicit
verified or analyst-approved mappings. Equal usernames or email-looking strings
are insufficient proof. Cross-cloud person-level scoring remains planned until
the mapping and aggregation path is implemented and tested.

## Training and evaluation separation

1. Generate normal activity first, using varied but bounded routines.
2. Freeze the AE/scaler after fitting on the normal training period only. Select
   thresholds using a separate normal calibration period.
3. Evaluate later, held-out normal activity plus a controlled transition in one
   previously normal account. Include benign unusual activity and cases that the
   current telemetry cannot detect.
4. Keep scenario labels, transition times, seeds and expected actor mappings in a
   separate experiment manifest. Never insert "attacker", scenario ID, compromise
   status or evaluation labels into model input features.
5. Compare AE against the previously studied baselines on the same held-out data
   when making a performance claim. Existing CERT results do not establish accuracy
   on the new real-cloud stream.

Provider audit timestamps must stay genuine. Fast generation is still a short
real collection period; it does not create weeks of baseline history. Any
time-shifted replay must run separately, be labelled replay, and never be mixed
with real provider evidence. A small scripted dataset demonstrates workflow; it
does not establish enterprise accuracy or broad generalization.

Report collection coverage, genuinely distinct identities, normal history per
account, precision/recall or PR-AUC where meaningful, false positives on held-out
normal activity, detection delay and missed cases. Explain small sample sizes and
repeat results across seeds/routines rather than tuning one dramatic example.

## Execution limits

Before running, finish duplicate-safe collectors, source coverage indicators and
identity mappings. Use explicit action/target allow-lists, maximum calls per run,
bounded concurrency and a stop condition. No root runtime credentials, production
data, destructive cloud actions or unrestricted autonomous tool use. Begin with
one-shot scripts; a future scheduled experiment needs explicit scheduling consent.

Demonstration claim: controlled simulated behaviour exercising real cloud services,
with scenario ground truth withheld from the detector. Do not call the controlled
account a real intruder or claim an AI-generated benchmark is an independent
enterprise deployment.
