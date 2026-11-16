# SDE-SQL fidelity on CLINSQL and MIMIC-IV v3.1

**Live pilot status: BLOCKED.** The SDE workflow has offline source and
transport coverage. Live model access, GoogleSQL behavior on MIMIC and
permission to send probe feedback still require verification.

**Offline regression: 38 passed, 40 deselected.** Coverage includes source
probe formatting and ordering, JSON retry exhaustion, locked subquery
decomposition, search fallback, candidate consistency, first-five-row
refinement, the `n=9` and `n=3` request contract, result attribution and
separation of SQL failures from infrastructure failures.

## Source mapping

- `explore_new.probe_before_generation`, `first_stages_probe_sqls` and
  `second_stages_probe_sqls` map to `SDESQL.probe_before_generation`.
  Base and condition groups retain response order, SQL cleanup and group
  headers. Stage two receives stage-one feedback. Generation receives both
  stages. A nonempty result containing SQL NULL still yields `Not NULL`.
- `gpt_request.collect_response_from_gpt` and
  `uils.find_most_consistent_sql` map to the zero-shot probe path and
  `_most_consistent`. A single request generates nine choices. Each
  occurrence is executed and contributes its own vote. Votes compare full
  unordered row sets, ignore duplicate rows and skip empty/error results.
  Ties and the all-empty fallback retain the first eligible choice in source
  order. Nested BigQuery values preserve ARRAY order, STRUCT field identities
  and NULL. The CLINSQL entry point always uses exploration with an empty
  hint when no approved hint is supplied.
- `refine_new.refine_sql`, `is_need_refine` and `judge_target` map to
  `SDESQL.run`, `native_refinement_reason` and `native_three_vote_judge`.
  The winning candidate is executed again. The refinement decision uses the
  first five rows, while the final result retains the complete execution.
  The judge runs only when that initial execution needs no refinement, with
  three choices in one request. At least two modification votes select the
  last modified SQL. It returns `judge_modified_unexecuted` with no result
  attached. There are at most three corrections and one outer generation
  pass, following `use_check=False`.
- `refine_new.get_subsqls`, `reader.core_function.generate_result` and
  `probe_refine_sql` map to `sde_subqueries.py` and the empty-result path.
  The port calls the locked native AST implementation with a 60-second
  deadline. Failure routes to search-generated diagnosis probes. Successful
  decomposition returning zero probes continues directly to fix-probe
  generation. Diagnosis probes, fix probes and final refinement follow
  source order and preserve numbered feedback.

## Adaptations and remaining gaps

GoogleSQL prompt instructions and qualified schema identifiers replace
SQLite dialect guidance. The native description slot uses verified schema
DDL in the CLINSQL runner. BIRD column descriptions, matching content and
value retrieval are unavailable on the approved path. The inference entry
point has no gold or reference inputs. Probe labels and judge column names
are the database feedback the model needs. Patient result cells stay local.
The Chat Completions path rejects mock database evidence and requires explicit
probe feedback authorization.

The exploration source omits the retry-counter increment. The port implements
the written `<= 5` condition as six retries after the initial request per stage.
SQL guard and SQL errors are handled with sanitized feedback. Permission,
timeout, budget, service and incomplete-result failures propagate for
separate accounting. Probes are submitted sequentially to honor the shared
ledger. BigQuery uses the shared configured timeout rather than SQLite's
3- and 30-second execution timeouts. SQLGlot round trips can reject unsupported
dialect constructs. The diagnosis path then uses the source search fallback.
Model response parsers accept fenced and plain formats. Exact parity for
every malformed response and BigQuery AST shape remains unverified.

The transport pins `gpt-5-mini-2025-08-07`, uses Chat Completions with
`max_completion_tokens`, omits `temperature` and `top_p`, and accounts for
all choices in one API reservation. OpenAI lists the snapshot as deprecated.
Account access and support for `n=9` and `n=3` on the pinned endpoint remain
unverified live. See [model documentation](https://developers.openai.com/api/docs/models/gpt-5-mini),
[Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [parameter compatibility](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.4#parameter-compatibility).

## Pilot prerequisites

Bind a method-scoped approval to the reader Service Account, pinned schema,
validation cases, evidence policy and restricted result retention. Wire the
approved shared BigQuery adapter and persistent SQL/API ledgers into an SDE
live entry point. Budget both stages and every diagnosis/fix probe, nine
candidate executions, one winning SQL rerun, up to three correction
executions and separate final evaluation if the judge changed the SQL.
Set per-query bytes, row and result-byte limits and per-case and total caps.
An incomplete result invalidates consistency selection. Verify pinned model
access and multi-choice requests with synthetic inputs before MIMIC execution.
