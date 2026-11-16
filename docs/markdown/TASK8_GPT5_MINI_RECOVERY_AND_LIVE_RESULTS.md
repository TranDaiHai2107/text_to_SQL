# Task 8 GPT-5-mini recovery and live results

## Model and experiment scope

Every generative inference stage in the benchmark resolves to `gpt-5-mini-2025-08-07`. CoT uses Responses for generation and refinement. MAC-SQL uses Responses for Selector, Decomposer and Refiner. SDE-SQL uses Chat Completions for exploration, generation, diagnosis, refinement and voting. Ours uses Responses for linking, planning, generation, verification, correction and selection. Requests reserve budget with the stage, provider and model ID recorded together. A configured or returned model outside the snapshot fails with `MODEL_MISMATCH`.

The former EvidenceRouter selected a loopback Qwen model whenever the prompt contained restricted evidence. That routing was an experimental change I made. The production runner rejects its flags and never dispatches to Qwen. The loopback server was stopped. Its debugging records remain under the method-specific evidence and structured retry directories in restricted storage, outside the pinned GPT-5-mini run. The earlier MAC attempt ended at SQL guard after two local model calls, with no final prediction artifact. Five Qwen Ours cases stopped in the linker.

## Single-case verification

- **CLINSQL CoT 5/5, SDE-SQL 5/5.** Reused the ten saved predictions and verified complete result artifacts by SHA-256. The CoT audit and saved SDE inference events confirm the same GPT-5-mini snapshot.
- **Ours 0/5.** Diagnostic Procedures Easy/058 reached schema retrieval and the linker with a nonempty clinical dictionary payload. Its trace records `RESTRICTED_EVIDENCE_EGRESS` at `link`. The case made zero API and BigQuery calls. OpenAI Responses separately accepted the strict linker schema with synthetic input and returned valid structured output on the pinned model.
- **MAC-SQL 0/5.** The native Selector lazily loads the database description once per database, including column examples that inform its initial pruning. The BigQuery port therefore retains all 225 sample queries. The ledger contains 204 exact current SQL hashes and 21 matching original SQL hashes covering all 225 inputs. The runner verifies hash, case scope, job metadata and billed bytes before reading cached rows locally. Diagnostic Procedures Easy/058 recovered all 225 samples and reached Selector after 14.6 minutes. The outbound prompt contained patient-derived samples, so it stopped with `RESTRICTED_EVIDENCE_EGRESS` before the API request. The case created no new BigQuery job and had no final SQL.

The linker validates JSON field shape before checking clinical coverage. A covered type or enum does not substitute for a verbatim source span, a literal, a declared join or a supported catalog link. The existing bounded retry sends the original question, prior output and targeted validation feedback to the same provider. SQL correctness remains a separate downstream check. Targeted regressions passed **109/109**.

## Usage and remaining condition

One new synthetic Responses request used **240 input tokens and 497 output tokens**, including **384 reasoning tokens**. The two clinical cases submitted zero API requests and zero BigQuery query jobs, for zero new billed bytes. The remaining cases were held at the single-case gate. Before this recovery the MAC ledger showed **262 reconciled jobs**, **54,639,198,208 billed bytes**, and **zero outstanding BigQuery reservations**. The historical Qwen Ours ledger retains one local timeout reservation with unknown token usage. The same credit and pricing evidence was verified through **22 November 2026 at 09:00 UTC+7**.

Restricted dictionary rows and patient-derived column samples require verified data-handling controls for the exact OpenAI project and endpoint. The existing attestation covers the experiment scope. OpenAI treats content in abuse-monitoring logs separately from application state controlled by `store=false`. [PhysioNet guidance](https://www.physionet.org/news/post/llm-responsible-use/) · [OpenAI Data Controls](https://developers.openai.com/api/docs/guides/your-data)
