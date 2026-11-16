# GPT-5-mini access and Phase C.1 state — 14/11/2026

**Status: API_TRANSPORT_PASS; CLINSQL pilot 0/5.** This report records actual
requests, not benchmark predictions or scores.

- `.env` is Git-ignored, contains a nonempty key, and is loaded into research
  commands by `run.py` without printing its value. Its Windows ACL was checked
  after removing inheritance: only `DAIHAITRAN\ASUS`, Administrators and SYSTEM
  have Full Control. The key value was not added to source, tests or logs. Because
  a key was previously pasted into chat, rotate it before continuing with the
  patient-data pilot; keep the replacement only in `.env` or another private
  credential store.
- The selected inference model is pinned to
  `gpt-5-mini-2025-08-07`, with Responses `reasoning.effort=medium` and
  `store=false`. The OpenAI model retrieval API returned the same model ID.
- One paid, **nonclinical** Responses access probe returned successfully:
  response ID `resp_0b083ebf9b2d08e0016af75400f1c887d2844999946bd18e82`,
  13 input tokens, 59 output tokens, 0 reported reasoning tokens. The persistent
  ledger estimates USD 0.00012125 using the GPT-5-mini input/output rates, before
  cached-input discount or tax. No clinical question, schema, SQL, result or
  patient data was sent in this probe.
- API policy is `UNLIMITED_RESEARCH_NOV_2026`. There is no aggregate USD hard
  cap; the pilot still bounds calls and tokens by the three-attempt CoT algorithm.
  The policy refuses new reservations outside November 2026 in UTC+07:00.
- Offline pilot plan verifies the five frozen validation-development questions,
  MIMIC manifest SHA-256 and schema index. Its API key presence check is true.
  `paper_sources.py` passes for all three locked official checkouts.
- A validation-only pre-freeze master manifest now pins 5 pilot, 152 development
  and 38 internal-check IDs. The test split remains sealed until configuration
  freeze. Its SHA-256 is
  `fd28d344e6fe0c118a75554abcdb6d631f33b6ebb4e06262c59b6cf71e718173`.
  The selected offline regression suite is 68/68 PASS. No CLINSQL pilot case
  has been submitted.

**Patient-data execution remains closed.** There is no Phase C.1 approval or
approved BigQuery aggregate budget under `results/restricted`; the Phase A
approval authorizes only its four locked smoke SQLs and cannot be reused. The
current `docs/PHASE_C1_APPROVAL_DRAFT.json` is intentionally invalid. The
unverified Organization/Folder IAM inheritance is still labeled
`READ_ONLY_LIKELY`, not `VERIFIED_READ_ONLY`. Await the explicit scoped risk,
BigQuery budget and artifact retention decision before generating a pilot SQL
that may be executed on MIMIC. No CLINSQL inference, judge, or test case has run.
