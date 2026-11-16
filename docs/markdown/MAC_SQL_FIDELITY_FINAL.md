# MAC-SQL fidelity for CLINSQL and MIMIC-IV v3.1

**Live pilot status: BLOCKED.** The offline BIRD workflow and BigQuery sampler
have passed synthetic tests. The full baseline requires authorization for
column value evidence and a MAC-SQL live execution scope.

Targeted regression: **59 passed** across `test_mac_sql_fidelity.py`,
`test_phase_c1_pilot.py`, `test_clinsql_offline_workflows.py` and
`test_phase_b_integration.py`. No paid API or patient queries were used.

| Source function | Port and verification |
| --- | --- |
| Selector.`_is_need_prune`, `_prune`, `talk` | Preserves the native thresholds, bypass for small schemas, fenced/plain JSON, and full-schema fallback on malformed JSON. Transport failures surface to the runner for accounting. |
| Selector.`_get_db_desc_str`, `_build_bird_table_schema_list_str` | Preserves schema order, unmentioned tables, first-six `drop_all`, key retention for selected lists, and six-column completion. Native rendering parity is tested with synthetic column descriptions and explicit primary keys. |
| Selector.`_get_unique_column_values_str`, `_get_value_examples_str` | Read-only, qualified BigQuery GROUP BY with frequency order, identifier/key exclusions, numeric cardinality gate, up to six examples, NULL and text filtering. Tested through the real SQL guard and a synthetic BigQuery client. Prompt integration requires both a mock model and mock database. |
| Decomposer.`talk` | Loads the native BIRD prompt, preserves the response as `qa_pairs`, parses the final SQL fence and routes to Refiner. Parser failure terminates without executing SQL. The port passes a single prompt per turn, as the agents do. |
| ChatManager.`start`, `_chat_single_round` and Refiner.`talk`, `_is_need_refine` | Native source methods exercised offline for early success, parser failure, and exhaustion. The first round can invoke all three agents. Subsequent rounds can execute corrections. The third Refiner turn may emit a final unexecuted correction. Empty or NULL in the first five rows triggers correction. |

BigQuery adaptation uses the existing guarded dry run, allowlist, caps and
timeout. SQL errors and guard rejections receive sanitized feedback.
Infrastructure failures and incomplete results propagate for separate
accounting. Prompt templates remain sourced from MAC-SQL. Schema context
includes qualified BigQuery table identifiers and the Refiner prompt names
BigQuery. Join hints come from the project's declared MIMIC relationships,
including both ICD join columns. These relationships are domain metadata,
not a verified database foreign-key inventory. The current manifest lacks
BIRD-style per-column descriptions and explicit primary keys. Labels fall
back to humanized column names. No oracle schema or gold inputs enter the
agent message.

Sampling adds a deterministic tie break and maps BigQuery scalar types.
Temporal examples use ISO strings and unsupported types are skipped.
Text columns require the full distinct result to apply the source filter.
The configured probe cap can prevent completion on high-cardinality columns.
Native parser utility edge cases and SQLite exception strings do not have
exact parity. Synthetic tests do not establish live prompt or execution
quality.

Before the live pilot, approve the data evidence permitted in GPT-5-mini
prompts, connect the sampler through the approved execution path, and set a
method-specific budget for sampling, three Refiner turns and any separate
execution of the final correction. A run with values omitted must be
reported as a restricted adaptation. Wire the existing GPT-5-mini provider
and checkpointed runner with that scope. The MAC-SQL port accepts the
existing provider's `generate(..., n=1)` interface.
