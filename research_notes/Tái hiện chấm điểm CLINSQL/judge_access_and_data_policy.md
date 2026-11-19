# Judge access and data policy for re-running the official CLINSQL judge on MIMIC-IV (as of 2026-11-18)

Scope: whether the official CLINSQL judge (stated by the caller as Azure OpenAI "gpt-5-chat", temperature 0.2) can still be called; whether MIMIC-IV query result rows can be sent to it under PhysioNet rules; and what compliant alternatives exist. All "as of" dates are page dates read on 2026-11-18.

## 1. Is the exact official judge model still accessible?

### Takeaway
No. Both Azure versions of `gpt-5-chat` (2025-08-07 and 2025-10-03) are listed as **Retired**, and OpenAI's `gpt-5-chat-latest` was shut down on 2026-07-23. Retired Azure models return `410 Gone`, and retirement dates can't be extended. The only successor, Azure `gpt-chat-latest`, is a rolling Preview model and a different model. The exact official judge can't be re-run in Nov 2026.

### Cited findings
- The Microsoft Foundry "Model retirement schedule" (ms.date 2026-09-21, updated 2026-09-23) lists:
  - `gpt-5-chat | 2025-08-07 | Retired | 2026-06-29 | gpt-chat-latest`
  - `gpt-5-chat | 2025-10-03 | Retired | 2026-05-13 | gpt-chat-latest`
  - `gpt-5.1-chat` (2025-11-13), `gpt-5.2-chat` (2025-12-11 and 2026-02-10) and `gpt-5.3-chat` (2026-03-03) are all Retired, with replacement `gpt-chat-latest`.
  - Source: [MS Learn – Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)
- The same table lists `gpt-chat-latest` only as **Preview** versions: 2026-05-05 (retires 2026-11-17), 2026-05-28 (retires 2026-12-08), 2026-06-24 (retires 2026-11-17), 2026-08-06 (retires 2027-01-12) and 2026-10-07 (retires 2027-05-18). This is a series of rolling preview snapshots, not the 2025 gpt-5-chat weights. — [MS Learn – Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)
- The reasoning models `gpt-5` (2025-08-07, GA, retires 2027-02-09) and `gpt-5-mini` (2025-08-07, GA, retires 2027-07-13) are still available. — [MS Learn – Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)
- Search snippets of the same page conflict on dates. One version showed gpt-5-chat 2025-10-03 as "Preview, retiring 2026-06-29". A Microsoft Q&A answer gave 2026-04-15 for 2025-08-07, and Microsoft said the deprecations page is authoritative. The current page (Sept 2026) lists both versions as Retired, so the conflict doesn't change the conclusion. — [MS Learn retirement page](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule); [MS Q&A](https://learn.microsoft.com/en-us/answers/questions/5820577/clarification-on-oai-model-expiration-date)
- Lifecycle rules (page ms.date 2026-07-24):
  - Retired: "Removed from service. All inference requests return `410 Gone`."
  - Preview models: "Weights, runtime, and API schema might change", and "customers are **force-upgraded** to a replacement ... There's no option to remain on a retiring preview model."
  - FAQ: "Can I get an exception to extend a model's retirement date? No."
  - GA models: "Weights and APIs are fixed."
  - Source: [MS Learn – Foundry Models lifecycle and support policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements)
- Standard, Global Standard and Data Zone Standard deployments are auto-upgraded at retirement unless `versionUpgradeOption` is `NoAutoUpgrade`, in which case the deployment stops working. So a deployment still *named* "gpt-5-chat" may now silently serve the replacement model. — [MS Learn – lifecycle policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements)
- On the OpenAI API, the deprecations page lists `gpt-5-chat-latest` with notice date Apr 22, 2026, shutdown Jul 23, 2026, and replacement `gpt-5.6-sol`. `gpt-5.1-chat-latest` has the same dates. `gpt-5.2-chat-latest` and `gpt-5.3-chat-latest` were shut down Aug 10, 2026. — [OpenAI API deprecations](https://developers.openai.com/api/docs/deprecations); mirrored by [aiengineerguide tracker](https://aiengineerguide.com/tools/model-retirements/gpt-5-chat-latest/)
- On temperature support, the Azure reasoning-models doc (ms.date 2026-11-04) says: "Reasoning models other than GPT-6 Astra don't support the following parameters: `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `logprobs`, `top_logprobs`, `logit_bias`, `max_tokens`." `gpt-5` and `gpt-5-mini` are reasoning models, so they reject temperature=0.2. `gpt-5-chat` is not in the reasoning-model feature tables. — [MS Learn – Azure OpenAI reasoning models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)
- Third-party listings describe GPT-5 Chat as non-reasoning ("Reasoning: No"). — [pi.dev Azure gpt-5-chat-latest](https://pi.dev/models/azure/gpt-5-chat-latest); [modelcompare.dev](https://modelcompare.dev/models/openai/gpt-5-chat)
- Pricing (third-party, not verified on Microsoft's own page, which rendered without numbers): Azure gpt-5-chat was $1.25 per 1M input tokens and $10.00 per 1M output tokens, with cached input at $0.125 per 1M. One listing for a dated `gpt-chat-latest` 2026-05-05 snapshot shows $5.00 input and $30.00 output per 1M. — [Future AGI cost calculator](https://futureagi.com/llm-cost-calculator/azure-openai/gpt-5-chat); [azurespeed](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-5-chat); [pricepertoken gpt-chat-latest 05052026](https://pricepertoken.com/pricing-page/model/openai-chat-latest-05052026)
- **Which judge the paper names:** the CLINSQL paper (arXiv 2601.09876, EACL 2026) says only "GPT-5": "Consistency is ensured by employing GPT-5 as the judge". It also says "The same GPT-5 judge issues decisions and concise rationales by comparing the CSV with the rubric and gold references". The parts of the paper I read give no provider, version string or temperature. It says "proprietary models are accessed through official APIs." — [arXiv 2601.09876 (HTML)](https://arxiv.org/html/2601.09876)
- The HF dataset card points to the code at github.com/Barryshen1/ClinSQL. It describes "an LLM judge" without naming the model or temperature. The benchmark runs on BigQuery `physionet-data.mimiciv_3_1_*`. — [HF yifeis02/ClinSQL README](https://huggingface.co/datasets/yifeis02/ClinSQL/blob/main/README.md)

### Reproducibility of hosted models
- Azure's "reproducible output" feature (the `seed` parameter) is best-effort: determinism isn't guaranteed, and users are told to watch `system_fingerprint` for backend changes. — [MS Learn – reproducible output](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reproducible-output)
- OpenAI's cookbook says responses can still differ in rare cases even when the seed, parameters and `system_fingerprint` all match. — [OpenAI cookbook – seed](https://developers.openai.com/cookbook/examples/reproducible_outputs_with_the_seed_parameter)

### Inferences
- The caller's "gpt-5-chat, temperature 0.2" most likely comes from the ClinSQL code/config, not the paper. This fits: the reasoning `gpt-5` rejects temperature, so a temperature-0.2 "GPT-5" judge has to be the chat variant.
- Which Azure version the authors used (2025-08-07 or 2025-10-03) can't be determined from the paper. The arXiv v1 is dated Jan 2026, when both versions were live. If they used a Standard deployment with auto-upgrade, the version may have changed mid-experiment.
- Even if gpt-5-chat were still live, a temperature of 0.2 (not 0) with no documented seed means the official scores are only reproducible within sampling noise. Exact leaf-level agreement isn't guaranteed even with the identical model.
- `gpt-chat-latest` (Preview) is the nearest successor, but it is a different judge. It is also on a force-upgrade cycle, so it doesn't give a stable reference either.

### Gaps
- I didn't fetch github.com/Barryshen1/ClinSQL, so the judge deployment name, API version, temperature 0.2 and seed are **not verified** from code.
- I found no source saying which gpt-5-chat version produced the paper's numbers.
- I didn't verify the gpt-5-chat price on Microsoft's official pricing page.

## 2. Is sending MIMIC-IV query result rows to that judge permitted under PhysioNet rules?

### Takeaway
PhysioNet's DUA (Credentialed Health Data Use Agreement 1.5.0) forbids sharing access to restricted data with anyone else. PhysioNet's April 2023 guidance applies that to LLM services:
- **Prohibited:** ChatGPT and the APIs of companies like OpenAI.
- **Allowed, with conditions:** Azure OpenAI only after opting out of human review, Amazon Bedrock, Google Gemini via Vertex AI, and Anthropic Claude.

No PhysioNet text exempts small aggregates, and CLINSQL's results CSVs can contain row-level patient data. They should be treated as restricted data.

### Cited findings
- The MIMIC-IV v3.1 DUA is the "PhysioNet Credentialed Health Data Use Agreement" v1.5.0. Key clauses:
  - Clause 3: "I will not share access to PhysioNet restricted data with anyone else."
  - Clause 1: "I will not attempt to identify any individual or institution referenced in PhysioNet restricted data."
  - Clause 2: "I will exercise all reasonable and prudent care to avoid disclosure of the identity of any individual..."
  - Clause 9: "If I openly disseminate my results, I will also contribute the code used to produce those results..."
  - Source: [PhysioNet – MIMIC-IV 3.1 DUA](https://physionet.org/content/mimiciv/view-dua/3.1/)
- PhysioNet news post "Responsible use of MIMIC data with online services like GPT" (posted 2023-04-18, no update date shown):
  - The DUA "explicitly prohibits sharing access to the data with third parties", which includes "sending it through APIs provided by companies like OpenAI" or "using it in online platforms like ChatGPT".
  - On Azure OpenAI: "You'll need to opt out of human review of the data". The justification to give Microsoft is that "you do not have the right to permit Microsoft to process the data for abuse detection".
  - On Amazon Bedrock: "data is not shared back to the base model for training".
  - On Vertex AI: "Gemini doesn't use your prompts or its responses as data to train its models". For Trusted Tester features, "you should obtain the appropriate opt-outs for data sharing".
  - On Anthropic Claude: not used for training by default, and no routine human review.
  - Source: [PhysioNet news – Responsible use of MIMIC data with online services like GPT](https://physionet.org/news/post/gpt-responsible-use)
- Azure's data commitments (page ms.date 2026-05-18): prompts and completions "are NOT available to OpenAI", are "NOT used ... to improve their models", and Models sold by Azure "do NOT interact with any services operated by ... OpenAI (e.g. ChatGPT, or the OpenAI API)". — [MS Learn – Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
- Default Azure abuse monitoring:
  - Flagged prompts and completions are stored in a per-geography abuse-monitoring data store.
  - They can be human-reviewed by "authorized Microsoft employees" via SAWs/JIT.
  - "This human review abuse monitoring process won't take place if the customer has been approved for modified abuse monitoring."
  - With modified abuse monitoring, "the data storage and human review process described above is not performed. However, automated review may still be conducted".
  - Sources: [MS Learn – Abuse monitoring](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/abuse-monitoring); [MS Learn – Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
- Microsoft says "Azure Preview features, including Models sold by Azure in preview, may employ different privacy practices, including with respect to abuse monitoring." This matters because `gpt-chat-latest` is Preview. — [MS Learn – Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
- The CLINSQL judge receives "CSV outputs produced by executing the candidate SQL", i.e. real MIMIC-IV query outputs. — [arXiv 2601.09876](https://arxiv.org/html/2601.09876)

### Inferences
- Sending CLINSQL result CSVs to the OpenAI public API (e.g. `gpt-5-chat-latest`, which is now retired anyway) would violate PhysioNet's guidance. The guidance names "APIs provided by companies like OpenAI" outright.
- Sending them to Azure OpenAI with default abuse monitoring also doesn't meet PhysioNet's stated condition (opting out of human review). Only an Azure subscription approved for modified abuse monitoring matches the guidance.
- **Aggregates:** I found no PhysioNet text treating small aggregates (counts, means) differently. Clause 3 is about "access to PhysioNet restricted data". Many CLINSQL outputs are cohort-level aggregates, but others list `subject_id`/`hadm_id`, dates and lab values per patient. The prudent reading is that any result CSV derived from MIMIC-IV is restricted data unless it is truly aggregated and non-identifying. Publishing aggregate statistics in a paper is normal practice, but that is publication, not handing raw query outputs to a third-party processor. This is inference, not policy text.
- CLINSQL itself runs on BigQuery under each user's own credentialed Google Cloud project, so that part is already an approved route.

### Gaps
- PhysioNet's guidance is from April 2023 and doesn't mention Microsoft's Oct 2025 or Nov 2026 abuse-monitoring changes. I found no newer PhysioNet statement.
- I found no PhysioNet FAQ ruling on whether derived aggregate results count as "restricted data".
- The CLINSQL paper text I read has no statement on how its authors met PhysioNet's LLM guidance, such as whether they had modified abuse monitoring on Azure.

## 3. What would a compliant path look like, and what alternatives exist?

### Takeaway
A compliant run of the *official* judge is now impossible because the model is retired. Even for a successor Azure model, the compliant route needs modified abuse monitoring approval. That approval is limited to "customers and partners managed by a Microsoft account team or under an eligible program", and Microsoft is phasing it out for models released on or after 2026-11-01.

Realistic compliant options:
- **Judge with Azure GA `gpt-5`/`gpt-5-mini`:** only on an Azure subscription with modified abuse monitoring, and these reasoning models take no temperature.
- **Judge with Gemini or Claude on Vertex AI, or a Bedrock model:** under PhysioNet's listed conditions.
- **Run the judge only on non-sensitive content:** SQL-tree leaves only, or synthetic or aggregate-only result summaries.

Every option is a different judge, so scores must be reported as a re-judged approximation, not the official numbers.

### Cited findings
- On eligibility for modified abuse monitoring: "At this time, modified Guardrails ... and/or modified abuse monitoring for Models sold by Azure are available only to customers and partners managed by a Microsoft account team or under an eligible program, and are subject to additional requirements." The application is via a Microsoft Customer Voice form. — [MS Learn – Limited access](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/limited-access)
- "Some advanced Models sold by Azure may have more stringent criteria for turning off abuse monitoring." — [MS Learn – Abuse monitoring](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/abuse-monitoring)
- Upcoming change: "For models made available on or after November 1, 2026, Modified Abuse Monitoring will no longer be available, beginning on a future date to be announced", with at least 30 days' notice. Existing approvals continue for models released before 2026-11-01. — [MS Learn – Abuse monitoring](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/abuse-monitoring); [MS Learn – Limited access](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/limited-access)
- To verify approval, the resource JSON shows the capability `"ContentLogging": "false"`, via the portal or `az cognitiveservices account show`. — [MS Learn – Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
- PhysioNet's guidance accepts Google Gemini via Vertex AI, Amazon Bedrock and Anthropic Claude under its stated conditions. — [PhysioNet news](https://physionet.org/news/post/gpt-responsible-use)
- I found no evidence that gpt-5-chat was ever offered on Vertex AI. The OpenAI models listed as served by Microsoft are Azure-hosted, and OpenAI's own API is the other host. — inferred from [MS Learn – Data, privacy, and security](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy) and [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations)

### Cost estimate (inference; prices from third-party listings)
- Assumptions: 190 predictions; about 12 leaves per tree, two trees (SQL + results), so about 24 leaf judgments per prediction, or about 4,560 calls. About 3,000 input tokens per call (rubric, gold SQL, schema hints, candidate SQL or CSV) and about 200 output tokens.
- At the gpt-5-chat rates ($1.25 input / $10 output per 1M): 13.7M input ≈ $17, plus 0.91M output ≈ $9, for **≈ $26 total**.
- If the judge is called once per tree instead of once per leaf (380 calls × ~6k input), the cost is about $3–5.
- At the third-party `gpt-chat-latest` snapshot rate ($5 / $30), the per-leaf case is about $68 + $27 ≈ **$95**.
- Cost is not the binding constraint. Model retirement and modified-abuse-monitoring eligibility are.
- Timeline: I found no Microsoft-published turnaround time for modified-abuse-monitoring approval. Anecdotally it takes weeks, but that is **unverified**. For an individual student without a Microsoft account team, eligibility itself is the blocker, per the "managed by a Microsoft account team" text.

### Inferences
- A practical, defensible plan:
  - (a) Report the official CLINSQL numbers as published.
  - (b) Re-judge all systems, including the authors' baselines if their predictions are available, with one fixed, PhysioNet-compliant judge, e.g. Gemini on Vertex AI in the same GCP project as the BigQuery MIMIC access. Use temperature 0 where supported, and pin a dated model version.
  - (c) Note in the paper that the gpt-5-chat judge was retired (Azure 2026-05-13 / 2026-06-29; OpenAI 2026-07-23), so exact replication isn't possible.
  - (d) Measure judge agreement on a subset, e.g. against execution-match or a manual audit.
- Using Azure `gpt-5` (GA until 2027-02-09) is the closest in model family. But it rejects temperature 0.2, so it isn't the same judge configuration, and it still needs modified abuse monitoring to be PhysioNet-compliant.

### Gaps
- I couldn't find the current eligibility details or processing time for the modified abuse monitoring form, or whether academic or student subscriptions qualify ("eligible program" isn't defined on the page).
- I didn't verify current Vertex AI Gemini or Claude-on-Vertex pricing or model-version pinning.
- I didn't verify the price of `gpt-chat-latest` on Microsoft's official pricing page.
