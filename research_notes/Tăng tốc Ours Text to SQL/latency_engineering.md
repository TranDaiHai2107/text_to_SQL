# Latency and cost engineering for a gpt-5-mini multi-call pipeline (keeping the method fixed)

Note: the OpenAI model page now marks `gpt-5-mini` as **deprecated** and points new workloads to GPT-5.6 Terra ([model page](https://developers.openai.com/api/docs/models/gpt-5-mini)). Old platform.openai.com doc URLs now 301-redirect to developers.openai.com/api/docs/... Check the snapshot's shutdown date before the 443-question run.

## 1. Prompt caching

### Takeaway
Caching is on by default, needs no code changes, and costs nothing extra on older models such as gpt-5-mini. It only works when the leading part of the prompt (the prefix) is byte-identical across calls. For gpt-5-mini, cached input costs $0.025/M instead of $0.25/M, so it is 90% cheaper. It also shortens time-to-first-token (TTFT). It does not touch output or reasoning time, and that is where most of the 20-65 s per call goes.

### Cited Findings
- Caching is enabled by default. It reuses processed prefixes, which lowers input cost and TTFT. The prefix must reach a minimum length: 1,024 tokens for GPT-5.6+. "For earlier models, the minimum varies with settings such as tools, images, output schemas, reasoning effort, and verbosity." — [Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- The whole rendered prefix must match. Changing any of `model`, `tools`, `parallel_tool_calls`, `text.format`, `reasoning.effort`, `text.verbosity` or `context_management` changes the prefix. Advice: put stable content first and dynamic content last, and append to history rather than rewrite it. — [same](https://developers.openai.com/api/docs/guides/prompt-caching)
- Retention for pre-5.6 models is set with `prompt_cache_retention`. `in_memory` lasts about 5-10 minutes of inactivity, up to 1 hour. `24h` is typically about 30 minutes, up to 24 hours. Organizations without Zero Data Retention (ZDR) default to `24h`; ZDR organizations default to `in_memory`. Extended retention is listed for gpt-5, gpt-5.1, 5.2, 5.4 and gpt-4.1. gpt-5-mini is not named explicitly, so treat that as unverified. — [same](https://developers.openai.com/api/docs/guides/prompt-caching)
- `prompt_cache_key` (pre-5.6): a stable key helps route related requests to the same cache. Keep traffic under about 15 requests/min per key and split heavier traffic across several keys. A key does not guarantee a hit. — [same](https://developers.openai.com/api/docs/guides/prompt-caching)
- The cache works under ZDR. It stores encrypted key/value tensors (not prompt text) for at most 24 hours, and is never shared across organizations. — [same](https://developers.openai.com/api/docs/guides/prompt-caching)
- Check hits with `usage.input_tokens_details.cached_tokens`. Cached tokens still count toward tokens-per-minute (TPM) limits. — [same](https://developers.openai.com/api/docs/guides/prompt-caching)
- gpt-5-mini prices: input $0.25/M, cached input $0.025/M, output $2/M. — [Pricing](https://developers.openai.com/api/docs/pricing)
- Keep the same top-level `text.format` on every request so the prefix stays cacheable. — [Structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)

### Inferences
- Order each prompt as: (1) a fixed system prompt, (2) the full 31-table DDL, (3) the dictionary, (4) few-shot examples, then the stage-specific instructions, the question and earlier outputs last. Use one byte-identical "shared prefix" block across all 15 call types, and put stage-specific text after it. That makes about 10k+ of the 12-14k input tokens cacheable across stages and questions.
- Don't write anything per-question (timestamps, question IDs, shuffled examples) into the prefix. Sort table and dictionary order deterministically.
- Stages that use different `text.format` schemas create different prefixes. The common part may still be shared up to the first difference, depending on where the schema is rendered; this isn't documented. Measure `cached_tokens` per stage.
- Use one `prompt_cache_key`, such as "ehrqa-schema-v1". If you run more than about 15 requests/min concurrently, split across a few keys (for example by worker ID).
- `store=false`: the docs tie caching to ZDR compatibility, not to `store`. I found no statement that `store=false` disables caching. Confirm empirically with `cached_tokens`.
- Rough cost: about 15 calls × 13k input tokens is about 195k input tokens per question, roughly $0.049 uncached. At about 80% cached that drops to roughly $0.014. Output at 15 × 4k = 60k tokens is about $0.12, so output dominates cost.

### Gaps
- No official TTFT reduction figure for gpt-5-mini was found.
- The exact minimum cacheable length for gpt-5-mini with reasoning and a schema was not found.

## 2. Parallelism and rate limits

### Takeaway
Running independent calls concurrently changes no semantics, and it is the biggest wall-clock lever. Rate limits for gpt-5-mini are far above what this workload needs.

### Cited Findings
- OpenAI's latency guide recommends: "Parallelize. Run independent lookups concurrently". It also says every sequential call adds wait time, and to measure p50/p95 TTFT and end-to-end latency. — [Latency optimization guide](https://developers.openai.com/api/docs/guides/latency-optimization)
- gpt-5-mini limits: Build tier is 5,000 RPM and 2M TPM; Launch is 10,000 RPM and 10M TPM; Grow is 30,000 RPM and 180M TPM. — [Model page](https://developers.openai.com/api/docs/models/gpt-5-mini)

### Inferences
- Run the 3 generation branches (each with its own verify/repair chain) concurrently, for example with `asyncio.gather` and `AsyncOpenAI`. That turns the critical path from about 15 calls into about 2 + 1 + 4 calls.
- Also run several questions at once. Even 2M TPM at about 20k tokens per call allows about 100 calls per minute. Cap concurrency at about 8-16 with a semaphore, and back off on 429 errors.
- Concurrent branches no longer have a defined completion order, so make anything order-dependent (logs, seeds) deterministic per question.
- SQLite ledger: this is standard SQLite behaviour, not from the sources above. Use one writer, or enable WAL mode with `busy_timeout`, and write each record in one short transaction. For simplicity, collect results in memory or a queue and let a single writer task commit them. With multiple processes, give each question its own run or row to avoid lock contention.
- Parallel calls warm the cache at the same moment, so the first concurrent wave may miss. Warm up with one sequential call per prefix first.

### Gaps
- No official guidance was found on SQLite in this context.

## 3. Output and reasoning token levers (reasoning effort unchanged)

### Takeaway
Output and reasoning tokens drive latency. Without changing effort, the safe levers are smaller requested outputs, possibly lower `verbosity`, and warming schemas. A tight `max_output_tokens` cap is risky because it can return incomplete responses, and truncated answers would bias results.

### Cited Findings
- "Generate fewer tokens" is the most direct lever. Ask only for the fields you need and lower `text.verbosity` where it is supported. `max_output_tokens` caps reasoning and visible output combined, and a low cap can return `incomplete`. — [Latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)
- Verbosity (low/medium/high) is set with `text={"verbosity":...}`, and the cookbook demonstrates it on gpt-5-mini. Its guidance: keep prompts stable and adjust the parameter instead. — [GPT-5 new params cookbook](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools)
- Structured outputs: "the first request you make with any schema will have additional latency as our API processes the schema"; later requests don't pay it. Truncation shows as `status: incomplete` with reason `max_output_tokens`. — [Structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)

### Inferences
- `verbosity` arguably changes the generation configuration. Baselines presumably use the default (medium), so changing it could be challenged on fairness grounds. If you do change it, apply it to baselines too or report it. Verbosity also changes the cache prefix.
- Trimming JSON fields (dropping "explanation" or "rationale" fields that are never consumed) is method-preserving and cuts visible output.
- Use `max_output_tokens` only as a generous safety cap (for example 16-25k) to stop runaway responses, and log every `incomplete`.
- Warm each structured-output schema with one call before timing anything.

### Gaps
- No source quantifies how verbosity affects reasoning tokens.

## 4. Batch API and Flex processing

### Takeaway
Both halve the price of gpt-5-mini ($0.125/M input, $1.00/M output). Batch can take up to 24 hours, which fits multi-stage sequential pipelines badly. Flex is synchronous and cheaper but slower, and sometimes returns 429 when capacity is unavailable. Flex is the better fit for offline benchmark runs.

### Cited Findings
- gpt-5-mini Batch and Flex prices: $0.125 input, $0.0125 cached input, $1.00 output per 1M tokens. Priority, renamed "Fast" on 2026-07-30, costs $0.45, $0.045 and $3.60. — [Pricing](https://developers.openai.com/api/docs/pricing)
- Batch: 50% discount, `completion_window` must be 24h, supports `/v1/responses`, up to 50k requests and 200 MB per file. It uses a separate rate-limit pool. The docs don't say whether caching applies. — [Batch guide](https://developers.openai.com/api/docs/guides/batch)
- Flex is billed at batch rates and caching still applies. It is slower, can return 429 "Resource Unavailable" (not charged) when capacity is short, and you should retry with backoff or fall back to `service_tier="auto"`. Raise the SDK timeout, since the default is 10 minutes. — [Flex processing guide](https://developers.openai.com/api/docs/guides/flex-processing)
- Fast mode (formerly Priority) gives lower latency for the same model at a higher price. Log `service_tier` with each call. — [Latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)

### Inferences
- Batch would need one batch per pipeline stage, each taking up to 24 hours, so about 7 stage-waves could take days. It only suits single-shot stages.
- Flex with fallback to standard keeps the same model and outputs, so the method is unchanged; only the serving tier differs. Report the tier.
- Wall-clock latency measured under Flex is not comparable with baseline latency, so time only standard-tier runs if you report latency.
- Fast mode cuts latency at about 1.8× the cost. Use it if wall-clock matters more than cost.

### Gaps
- The docs don't say whether gpt-5-mini is on the Flex beta model list. The pricing page lists Flex rates for it, which suggests yes.

## 5. Schema pruning evidence

### Takeaway
The evidence is mixed. Strong models often do fine with the full schema. Pruning with high-recall linking keeps accuracy and cuts tokens. But pruning the schema changes the method's inputs, so it isn't strictly method-preserving.

### Cited Findings
- "The Death of Schema Linking?": newer models find the relevant schema elements during generation, so when the schema fits in context you can skip linking. The authors report 71.83% execution accuracy on BIRD. Linking still helps smaller or older models. — [arXiv 2408.07702](https://arxiv.org/abs/2408.07702)
- RSL-SQL: bidirectional linking reaches 94% strict recall with 83% fewer columns (v2). It reports 67.21% execution accuracy on BIRD dev with GPT-4o, and votes between full-schema and simplified-schema runs. The authors warn that pruning risks dropping needed columns. — [arXiv 2411.00073v2](https://arxiv.org/html/2411.00073v2)
- CHESS: adaptive schema pruning (column filtering, table selection, column selection). The v3 abstract reports about 2% higher accuracy and about 5× fewer tokens. — [arXiv 2405.16755](https://arxiv.org/abs/2405.16755)

### Inferences
- At 31 tables (about 10k tokens) the schema fits comfortably, and with caching the full schema costs only about $0.0003 per call. Pruning would save little money but would change the method and break prefix sharing across questions. Prefer full schema + caching.
- If you prune, prune only in later stages (verify/repair), using the tables the link stage already selected, and report it as an ablation.

### Gaps
- LinkAlign was not researched within the tool budget.

## 6. gpt-5-mini speed figures

### Takeaway
I found no official tokens/sec or TTFT figures. Measure them yourself.

### Cited Findings
- The model page says gpt-5-mini is "faster and more cost-efficient than GPT-5" but gives no throughput numbers. — [Model page](https://developers.openai.com/api/docs/models/gpt-5-mini)
- To measure visible output speed: count the text tokens after the first text event and divide by the time from first to last text event. Record cached and output tokens with each timing. — [Latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)

### Inferences
- From the pilot's own numbers: 2-6k output tokens in 20-65 s works out to roughly 90-100 output tokens/s. That suggests output and reasoning generation dominates, and TTFT savings from caching are second-order.

### Gaps
- No primary-source TTFT or throughput figures were found. Third-party benchmarks such as Artificial Analysis were not checked.
