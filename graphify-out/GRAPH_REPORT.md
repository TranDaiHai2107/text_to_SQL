# Graph Report - text_to_SQL  (2026-11-16)

## Corpus Check
- 252 files · ~190,856 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 17 file(s) not represented in the graph (top: .started 11, (none) 2, .zip 2)

## Summary
- 1914 nodes · 5356 edges · 101 communities (85 shown, 16 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 790 edges (avg confidence: 0.91)
- Token cost: 703,309 input · 0 output

## Community Hubs (Navigation)
- Rubric Evaluation & Judges
- SQL Budget Ledger
- Four-Method Pilot Runner
- BigQuery Client & Metadata
- Phase C1 Real CoT Pilot
- Pilot Audit & Diagnostic Scripts
- Full Agentic Pipeline
- Retrieval Manifest & Few-shot
- Result Artifacts & Proposed Pilot
- Legacy RAG & LLM Client
- SDE-SQL Paper
- MAC-SQL Paper
- BigQuery Adapter & Limits
- Multi-provider LLM Runner
- MAC-SQL Port & Schema
- ClinSQL CoT Runner
- ClinSQL Paper
- Public Terminology Recovery
- SDE-SQL Port & Judge
- SDE-SQL Fidelity Tests
- Rubric Scoring & Retention
- Vector DB Builder
- Legacy Evaluation Metrics
- BigQuery Guarded Execution
- Metered Model & Run Log
- Phase C1 Pilot Tests
- Offline Workflow Tests
- BigQuery Preflight Config
- MAC-SQL Value Sampling
- Dataset & Experiment State
- Proposed System (Ours)
- SQL Schema Validator
- Local Model Transport
- Task 8 Evidence Router
- HTTP Gateway & Transport
- SDE Subquery Extraction
- Agentic Stage Contracts
- MAC-SQL Fidelity Tests
- Docker Postgres Setup
- ClinSQL Common Runner
- CTE Lineage Join Check
- Three Papers & Benchmarks
- Baseline Comparison Status
- Four-Method Readiness Docs
- Legacy Chat App
- Phase B Schema Index
- MIMIC Tables & SQL Guard
- GPT-5-mini Pilot Plan
- Phase C1/C2 Data Policy
- Phase A BigQuery Smoke
- MAC-SQL Mock Tests
- Metered Database
- Proposed System Docs
- Ours Catalog & Credit
- Equivalence Selection
- Sequential RAG Retrieval
- Execution Approval
- BigQuery Schema Manifest Docs
- Baseline Fidelity Progress
- Official Scorer & Judge Docs
- Paper Algorithm Audit
- Legacy Dataset Tests
- SDE Refine Policy Port
- OpenAI Model Provider
- Security Rejection Tests
- Experiment Protocol & Data
- Strict Fidelity & Model Pin
- Task 8 Approval & Live Pilot
- Postgres Database
- Guard Refinement Tests
- BigQuery Transport Fakes
- Implementation Status (VI)
- SDE n=9 Error & Fix
- Paper Environment Locks
- Result Multiset Matching
- SQL Validator Tests
- Phase C1 Readiness Docs
- MAC-SQL Fidelity Docs
- Legacy Boundary & Architecture
- App Config & Settings
- Official Evaluator Adapter
- Agentic UI Tests
- Probe Completeness Tests
- Research Validity Regression
- Pipeline Database
- LLM Client Tests
- Pilot SQL Root Cause
- Task 8 Repair Results
- Token Budget
- Remote Preflight Fakes
- Execution Capture Fake
- Validation & Test Splits
- Phase A Case Marker
- Project Requirements
- Runtime Role Script
- Results README

## God Nodes (most connected - your core abstractions)
1. `MockBigQuery` - 53 edges
2. `Execution` - 51 edges
3. `BigQueryConfig` - 43 edges
4. `MockLLM` - 41 edges
5. `IncompleteResultError` - 38 edges
6. `Schema` - 37 edges
7. `main()` - 37 edges
8. `BigQueryAdapter` - 36 edges
9. `BigQueryClient` - 35 edges
10. `run_real_cot_case()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `test_chat_provider_requires_explicit_probe_feedback_scope()` --uses--> `OpenAIChatMultiProvider`  [INFERRED]
  tests/test_sde_sql_fidelity.py → src/ehrqa/clinsql/chat_multi_provider.py
- `execute()` --calls--> `Execution`  [INFERRED]
  tests/test_phase_c1_pilot.py → src/ehrqa/text2sql/interfaces.py
- `audit()` --uses--> `ResultArtifactStore`  [INFERRED]
  scripts/audit_phase_c1_pilot.py → src/ehrqa/clinsql/result_artifacts.py
- `main()` --uses--> `BenchmarkExecutionApproval`  [INFERRED]
  scripts/audit_pilot_dry_run.py → src/ehrqa/clinsql/benchmark_approval.py
- `main()` --uses--> `BigQueryClient`  [INFERRED]
  scripts/audit_pilot_dry_run.py → src/ehrqa/clinsql/bigquery_client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Methods Compared on CLINSQL (CoT, MAC-SQL, SDE-SQL, Ours)** — docs_markdown_baseline_adaptation_clinsql_cot, docs_markdown_baseline_adaptation_mac_sql, docs_markdown_baseline_adaptation_sde_sql, docs_markdown_baseline_adaptation_ours [EXTRACTED 1.00]
- **BigQuery Patient-data Execution Safety Layers** — docs_markdown_controlled_bigquery_execution_report_bigquery_adapter, docs_markdown_controlled_bigquery_execution_report_bigquery_client_execute, docs_markdown_controlled_bigquery_execution_report_sql_budget_ledger, docs_markdown_bigquery_sql_execution_prep_report_result_artifact_store, docs_markdown_bigquery_sql_execution_prep_report_metered_database [EXTRACTED 1.00]
- **MIMIC Data Egress Constraints Blocking Scoring/Methods** — docs_markdown_experiment_protocol_data_policy, docs_markdown_clinsql_official_evaluation_report_no_result_transfer, docs_markdown_clinsql_first_scores_unscored_data_egress, docs_markdown_final_recovery_results_mac_excluded_data_egress, docs_markdown_final_recovery_results_provider_controls [INFERRED 0.85]
- **BigQuery patient-data execution safety controls** — docs_markdown_mimic_sql_execution_gate_report_kltn_sql_reader, docs_markdown_mimic_sql_execution_gate_report_resultartifactstore, docs_markdown_mimic_sql_execution_gate_report_metereddatabase, docs_markdown_phase_b_integration_report_persistent_sql_budget_ledger, docs_markdown_phase_a_execution_approval_checklist_started_marker, docs_markdown_gpt5_mini_live_pilot_results_seven_day_retention [INFERRED 0.85]
- **Four compared methods on CLINSQL/BigQuery** — docs_markdown_paper_algorithm_audit_clinsql_cot_self_refinement, docs_markdown_paper_algorithm_audit_mac_sql, docs_markdown_paper_algorithm_audit_sde_sql, docs_markdown_four_method_live_readiness_ours_dictionary_rag, docs_markdown_phase_b_integration_report_benchmark_backend [EXTRACTED 1.00]
- **Official CLINSQL scoring blocked by result-row transmission** — docs_markdown_pilot_5_accuracy_evaluation_official_score_not_available, docs_markdown_pilot_5_accuracy_evaluation_azure_gpt5_chat_judge, docs_markdown_pilot_5_accuracy_evaluation_rubric_leaf_requests, docs_markdown_paper_systems_clinical_rubric_scorer, docs_markdown_phase_c1_data_handling_policy_no_patient_data_to_llm [EXTRACTED 1.00]
- **Four compared Text-to-SQL methods on CLINSQL** — docs_markdown_project_readme_clinsql_cot_self_refinement, docs_markdown_research_three_text_to_sql_papers_20261111_mac_sql, docs_markdown_research_three_text_to_sql_papers_20261111_sde_sql, docs_markdown_project_readme_proposed_full_agentic_pipeline [EXTRACTED 1.00]
- **SDE-SQL port components (probe, voting, judge, subqueries)** — docs_markdown_sde_sql_fidelity_final_sdesql_class, docs_markdown_sde_sql_fidelity_final_most_consistent, docs_markdown_sde_sql_fidelity_final_native_three_vote_judge, src_ehrqa_clinsql_baselines_sde_subqueries [EXTRACTED 1.00]
- **Per-paper isolated Python 3.12 environment locks** — environment_locks_clinsql_py312_win, environment_locks_mac_sql_py312_win, environment_locks_sde_sql_py312_win, environment_readme_venv_papers [EXTRACTED 1.00]
- **MAC-SQL Selector-Decomposer-Refiner pipeline** — paper_baseline_2025_coling_main_36_selector_agent, paper_baseline_2025_coling_main_36_decomposer_agent, paper_baseline_2025_coling_main_36_refiner_agent, paper_baseline_2025_coling_main_36_algorithm_1 [EXTRACTED 1.00]
- **MAC-SQL agent prompts with shared constraints** — paper_baseline_2025_coling_main_36_selector_prompt, paper_baseline_2025_coling_main_36_decomposer_prompt, paper_baseline_2025_coling_main_36_refiner_prompt, paper_baseline_2025_coling_main_36_sql_generation_constraints [EXTRACTED 1.00]
- **LLM prompting baselines compared against MAC-SQL** — paper_baseline_2025_coling_main_36_din_sql, paper_baseline_2025_coling_main_36_dail_sql, paper_baseline_2025_coling_main_36_c3_sql, paper_baseline_2025_coling_main_36_gpt_4 [EXTRACTED 1.00]
- **Two-phase exploration before zero-shot generation** — paper_baseline_2026_acl_long_116_candidates_exploration, paper_baseline_2026_acl_long_116_combinations_exploration, paper_baseline_2026_acl_long_116_zero_shot_generation, paper_baseline_2026_acl_long_116_sql_probes [EXTRACTED 1.00]
- **Exploration-based refinement for empty-result SQL** — paper_baseline_2026_acl_long_116_error_cause_identification, paper_baseline_2026_acl_long_116_solution_exploration, paper_baseline_2026_acl_long_116_empty_result_error_taxonomy, paper_baseline_2026_acl_long_116_target_checking [EXTRACTED 1.00]
- **ClinSQL rubric-based evaluation protocol** — paper_baseline_2026_eacl_long_64_sql_rubric_tree, paper_baseline_2026_eacl_long_64_results_rubric_tree, paper_baseline_2026_eacl_long_64_critical_first_score_aggregation, paper_baseline_2026_eacl_long_64_gpt5_llm_judge, paper_baseline_2026_eacl_long_64_sql_score, paper_baseline_2026_eacl_long_64_execution_score [EXTRACTED 1.00]
- **ClinSQL inference regimes (Direct, CoT+refinement, Schema-hinted)** — paper_baseline_2026_eacl_long_64_direct_output_prompting, paper_baseline_2026_eacl_long_64_cot_self_refinement, paper_baseline_2026_eacl_long_64_schema_hinted_inference [EXTRACTED 1.00]

## Communities (101 total, 16 thin omitted)

### Community 0 - "Rubric Evaluation & Judges"
Cohesion: 0.06
Nodes (51): CLINSQL Scorer Parity Tests, main(), authorize(), grade_case(), save(), main(), authorize(), approved_sampler() (+43 more)

### Community 1 - "SQL Budget Ledger"
Cohesion: 0.06
Nodes (22): BudgetedDatabase, PersistentSQLBudgetLedger, research_query_cap(), SQLBudgetLedger, ResourceBudgetBlocked, DatabaseInterface, DryRun, EvaluationInterface (+14 more)

### Community 2 - "Four-Method Pilot Runner"
Cohesion: 0.09
Nodes (39): digest(), _approval(), _budgets(), configuration(), _credit(), _database(), _grouped_transport_pin(), _grouped_transport_verified() (+31 more)

### Community 3 - "BigQuery Client & Metadata"
Cohesion: 0.10
Nodes (15): main(), main(), make_benchmark_database(), verify_reader_adc(), verify_reader_credentials(), build_schema_manifest(), _digest(), information_schema_sql() (+7 more)

### Community 4 - "Phase C1 Real CoT Pilot"
Cohesion: 0.11
Nodes (19): execute_batch(), execute_one(), _load_scope(), main(), plan(), _profile_request_settings(), _read_budgets(), _run_root() (+11 more)

### Community 5 - "Pilot Audit & Diagnostic Scripts"
Cohesion: 0.09
Nodes (12): audit(), main(), check(), main(), evaluate(), main(), main(), expand_dataset() (+4 more)

### Community 6 - "Full Agentic Pipeline"
Cohesion: 0.09
Nodes (21): align_span(), build_catalog(), add(), public_catalog(), resolve_ids(), FullAgentic, ask(), execute_proposal() (+13 more)

### Community 7 - "Retrieval Manifest & Few-shot"
Cohesion: 0.09
Nodes (18): main(), checkpoint(), main(), CaseCheckpoint, ExperimentState, verify_pre_freeze_manifest(), ApprovedICDCatalog, FewShotIndex (+10 more)

### Community 8 - "Result Artifacts & Proposed Pilot"
Cohesion: 0.11
Nodes (22): require_scalar_result(), Question, prepare_official_sample(), prepare_saved_run_sample(), BenchmarkExecutionConfig, run_proposed_pilot_case(), _decode(), _encode() (+14 more)

### Community 9 - "Legacy RAG & LLM Client"
Cohesion: 0.08
Nodes (16): run_multiturn_tests(), database_url(), call_llm(), _build_metadata_summary(), build_prompt(), _call_llm(), _clean_sql(), _expected_source_hash() (+8 more)

### Community 10 - "SDE-SQL Paper"
Cohesion: 0.06
Nodes (38): BIRD Benchmark, BIRD dev results: 67.67% EX zero-shot, 68.19% with SFT (Qwen2.5-72B), Candidates Exploration (Base and Condition SQL Probes), Chain-of-Thought Prompting (Wei et al., 2022), CHASE-SQL (Pourreza et al., 2025), CHESS (Talaei et al., 2024), CodeS (Li et al., 2024), Combinations Exploration (+30 more)

### Community 11 - "MAC-SQL Paper"
Cohesion: 0.09
Nodes (34): Ablation Study (w/o Selector/Decomposer/Refiner), Agent-Instruct Dataset, Algorithm 1: MAC-SQL agent collaboration loop, AutoGen, AutoGPT, BIRD Benchmark, MAC-SQL+GPT-4 59.59 EX on BIRD test (SOTA at writing), C3-SQL (+26 more)

### Community 12 - "BigQuery Adapter & Limits"
Cohesion: 0.10
Nodes (14): main(), BigQueryAdapter, Limits, BudgetExceeded, translate_bigquery_exception(), SmokeExecutionConfig, test_bytes_cap_permission_and_no_patient_rows_in_log(), test_guard_accepts_cte_only_with_manifest_tables() (+6 more)

### Community 14 - "Multi-provider LLM Runner"
Cohesion: 0.12
Nodes (14): ModelMismatch, require_benchmark_model(), EvidenceRouter, guard_mac_payload(), RestrictedEvidenceEgress, build_pipeline(), execute_method(), _failure() (+6 more)

### Community 15 - "MAC-SQL Port & Schema"
Cohesion: 0.11
Nodes (16): Schema, qualified_table(), _bigquery_schema_context(), _bird_schema_text(), _chosen_columns(), _fk_text(), _key_columns(), _native_pruning_needed() (+8 more)

### Community 16 - "ClinSQL CoT Runner"
Cohesion: 0.11
Nodes (13): _bind_bigquery_datasets(), extract_sql(), generation_prompt(), refinement_prompt(), Attempt, Prediction, _source_function(), RunRecorder (+5 more)

### Community 17 - "ClinSQL Paper"
Cohesion: 0.08
Nodes (29): BIRD (Li et al., 2023), CLINSQL Benchmark (633 expert-annotated tasks), Patient-Similarity Cohort Reasoning in Clinical Text-to-SQL (ClinSQL, EACL 2026), CLINSQL Construction Pipeline (query, SQL, guideline annotation, validation), Chain-of-Thought prompting with up to two self-refinement rounds, Difficulty Stratification (Easy 30% / Medium 40% / Hard 30%), Direct Output prompting regime, EHR-SeqSQL (Ryu et al., 2024) and EHRSQL-ST (Lee et al., 2024) (+21 more)

### Community 18 - "Public Terminology Recovery"
Cohesion: 0.11
Nodes (11): compare_saved_linker(), main(), pin_profile(), anchored_link_format(), _object(), question_anchors(), resolve_link_anchors(), compare_local_records() (+3 more)

### Community 19 - "SDE-SQL Port & Judge"
Cohesion: 0.14
Nodes (13): native_three_vote_judge(), _parse_vote(), _dialect_template(), _freeze(), _generation_sql(), _json_object(), _most_consistent(), _nonempty_sql() (+5 more)

### Community 20 - "SDE-SQL Fidelity Tests"
Cohesion: 0.14
Nodes (21): MockBigQuery, result(), source(), test_chat_provider_rejects_synthetic_database(), test_chat_provider_requires_explicit_probe_feedback_scope(), test_consistency_counts_each_occurrence_and_preserves_nested_types(), test_decomposition_error_routes_search_diagnosis_fix_and_final_sql(), test_empty_diagnosis_success_without_subqueries_does_not_call_search() (+13 more)

### Community 21 - "Rubric Scoring & Retention"
Cohesion: 0.12
Nodes (13): ledger_usage(), saved_cohort(), build_cohort(), stage(), file_hash(), load_json(), private_sample_directory(), require_private() (+5 more)

### Community 22 - "Vector DB Builder"
Cohesion: 0.14
Nodes (14): _atomic_build(), build_examples_collection(), build_icd_collection(), populate(), build_schema_collection(), _canonical_sql(), _delete_if_exists(), _file_signature() (+6 more)

### Community 23 - "Legacy Evaluation Metrics"
Cohesion: 0.14
Nodes (10): compute_metrics(), evaluate_one(), load_test_dataset(), metrics_by_difficulty(), normalize_df(), _normalize_value(), preflight_gold(), print_summary() (+2 more)

### Community 24 - "BigQuery Guarded Execution"
Cohesion: 0.13
Nodes (6): BigQueryClient, ProbePresence, test_constant_smoke_is_exact_and_does_not_enable_general_execution(), result(), test_real_transport_consumes_all_result_pages(), test_bigquery_transport_blocks_writes_and_requires_explicit_execution()

### Community 25 - "Metered Model & Run Log"
Cohesion: 0.15
Nodes (12): OpenAIChatMultiProvider, MeteredModel, RunLog, FakeChatClient, _ledger(), test_grouped_nine_uses_three_requests_and_preserves_choice_order(), create(), test_incomplete_choices_fail_after_accounting_for_usage() (+4 more)

### Community 26 - "Phase C1 Pilot Tests"
Cohesion: 0.11
Nodes (11): git(), verify_sources(), load_research_env(), main(), _approval(), _budget(), test_api_budget_persists_and_stops_before_second_call(), test_dotenv_loader_preserves_process_precedence_and_ignores_legacy() (+3 more)

### Community 27 - "Offline Workflow Tests"
Cohesion: 0.16
Nodes (18): mock_schema_records(), records(), test_bigquery_adapter_redacts_query_errors_and_blocks_unlisted_tables(), test_clinsql_cot_stops_on_empty_generation_without_sql_probe(), test_common_runner_persists_prediction_and_blocks_repeat_and_test(), test_location_discovery_rejects_cross_region_datasets(), test_logging_captures_usage_cost_and_prevents_overwrite(), test_mac_sql_runs_selector_decomposer_and_refiner_with_mocks() (+10 more)

### Community 28 - "BigQuery Preflight Config"
Cohesion: 0.15
Nodes (14): main(), inspect_remote(), main(), plan(), main(), prepare(), smoke_cases(), discover_dataset_location() (+6 more)

### Community 29 - "MAC-SQL Value Sampling"
Cohesion: 0.14
Nodes (15): _prepare_mac_samples(), column_sample_queries(), format_examples(), missing_sample_columns(), _native_formatter(), utility(), native_selector_method(), recover_examples() (+7 more)

### Community 30 - "Dataset & Experiment State"
Cohesion: 0.13
Nodes (11): load_questions(), _rows(), validation_partition(), build_pre_freeze_manifest(), _digest(), select_pilot_cases(), verify_pilot_cases(), test_question_loader_exposes_only_input_fields_and_locks_test() (+3 more)

### Community 31 - "Proposed System (Ours)"
Cohesion: 0.14
Nodes (16): build_pipeline(), ProposedFlags, _schema_context(), ungrounded_clinical_literals(), ungrounded_join_keys(), model_for(), test_authoritative_schema_ranks_columns_and_grounds_joins(), test_base_ablation_uses_one_prompt_and_live_scope_rejects_unapproved_case() (+8 more)

### Community 32 - "SQL Schema Validator"
Cohesion: 0.11
Nodes (8): run_query(), _column_pair(), _format_error(), _function_name(), get_validator_prompt_hint(), _load_schema(), _missing_join_key(), validate_sql_schema()

### Community 33 - "Local Model Transport"
Cohesion: 0.14
Nodes (8): _array(), LocalModel, NoRedirect, _object(), _stage_schema(), _structured_instruction(), test_local_grammar_keeps_grounding_and_review_interfaces(), test_local_transport_only_uses_loopback_and_preserves_prompt()

### Community 34 - "Task 8 Evidence Router"
Cohesion: 0.12
Nodes (10): MACSQLChatProvider, classify_ours_catalog(), guard_ours_payload(), ProposedModelProvider, test_benchmark_provider_rejects_fallback_before_inference(), test_mac_source_chat_retains_native_single_user_message(), create(), test_ours_classifies_static_dictionary_separately_from_observations() (+2 more)

### Community 35 - "HTTP Gateway & Transport"
Cohesion: 0.17
Nodes (8): Gateway, ModelError, post_json(), bounded(), request(), test_gateway_keeps_unknown_cost_and_does_not_retry_after_deadline(), test_total_deadline_cancels_an_unfinished_request(), slow()

### Community 36 - "SDE Subquery Extraction"
Cohesion: 0.15
Nodes (8): bigquery_get_subsqls(), _native_generate_result(), native_get_subsqls(), timed_bigquery_get_subsqls(), test_bigquery_boundary_produces_single_select_probes(), test_get_subsqls_matches_locked_native_function(), test_native_diagnosis_timeout_uses_source_deadline(), test_qualified_join_and_dates_survive_native_decomposition()

### Community 37 - "Agentic Stage Contracts"
Cohesion: 0.16
Nodes (14): decomposition(), visit(), json_object(), pairs(), linking(), quoted_literals(), selection(), sql_evidence() (+6 more)

### Community 38 - "MAC-SQL Fidelity Tests"
Cohesion: 0.16
Nodes (9): source_methods(), source_utility(), test_port_sample_filters_match_source(), test_sampler_with_real_sql_guard_and_synthetic_client(), test_saved_sample_recovery_preserves_null_and_first_temporal_value(), test_selector_and_decomposer_render_same_source_prompts_for_matching_context(), test_selector_parser_uses_native_first_fence_and_whole_response_validation(), test_selector_source_drop_order_completion_and_descriptions() (+1 more)

### Community 39 - "Docker Postgres Setup"
Cohesion: 0.11
Nodes (17): MIMIC_READER_PASSWORD, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, interval, retries, test, timeout (+9 more)

### Community 40 - "ClinSQL Common Runner"
Cohesion: 0.15
Nodes (6): ExperimentConfig, ClinSQLCoT, load_validation_checkpoint(), run_validation_one(), test_common_runner_accepts_mac_and_sde_with_same_mock_database(), test_successful_extra_projection_does_not_trigger_baseline_refinement()

### Community 41 - "CTE Lineage Join Check"
Cohesion: 0.14
Nodes (7): _direct_column_origin(), _join_conjuncts(), _missing_join_key(), _scope_tables(), schema(), test_accepts_same_join_with_both_grounded_keys(), test_rejects_missing_or_unproven_composite_key()

### Community 42 - "Three Papers & Benchmarks"
Cohesion: 0.15
Nodes (17): Project README (MIMIC-IV & CLINSQL), bigquery-preflight command, MIMIC-IV v3.1 on BigQuery Target, CLINSQL CoT + Self-Refinement Baseline, clinsql-inspect command, MIMIC Mini/PostgreSQL Deprecated, Research: Three Text-to-SQL Papers, BIRD Benchmark (+9 more)

### Community 43 - "Baseline Comparison Status"
Cohesion: 0.16
Nodes (12): find_most_consistent_sql Result-set Majority Selection, MAC-SQL Baseline, clinsql.runner Mock-only Gate, SDE-SQL Three-vote judge_target Route, SDE-SQL Baseline, MAC Selector _is_need_prune Threshold, sde_judge.py Three-vote Decision Component, UNSCORED_DATA_EGRESS Execution Score Status (+4 more)

### Community 44 - "Four-Method Readiness Docs"
Cohesion: 0.16
Nodes (15): Four-method CLINSQL pilot readiness, Verified credit envelope (credit_sha256), four-method-pilot CLI, Ours dictionary_rag variant, SDE-SQL grouped_3x3 variant, Task 8 combined approval decision, Ours Easy/058 end-to-end run, MIMIC-IV v3.1 clinical dictionary catalog (204,275 entries) (+7 more)

### Community 45 - "Legacy Chat App"
Cohesion: 0.16
Nodes (7): legacy_result(), _build_chat_history_for_rewrite(), process_question(), _try_auto_chart(), ask_medical_question(), generate_sql(), generate_sql_with_correction()

### Community 46 - "Phase B Schema Index"
Cohesion: 0.18
Nodes (8): main(), SchemaIndex, _model(), scope(), test_four_methods_end_to_end_on_two_official_validation_questions(), test_schema_index_pins_all_31_real_metadata_tables(), test_sde_native_consistency_ignores_duplicates_empty_results_and_keeps_first_tie(), test_shared_benchmark_backend_is_manifest_pinned_and_execution_closed()

### Community 47 - "MIMIC Tables & SQL Guard"
Cohesion: 0.17
Nodes (14): SQL Guard, Phase A Four MIMIC Smoke SQLs (incl. validation 043), Clinical Catalog Export Report, catalog_export.py Dictionary Exporter, four-method-pilot CLI (plan / export-catalog), bigquery-approved-smoke CLI, admissions table, chartevents table (+6 more)

### Community 48 - "GPT-5-mini Pilot Plan"
Cohesion: 0.15
Nodes (13): CLINSQL BigQuery benchmark execution plan, MIMIC-IV v3.1 BigQuery manifest (SHA 46a816c2...), Phase C validation pilot, UNLIMITED_RESEARCH_NOV_2026 API policy, GPT-5-mini access check and Phase C.1 state, Pre-freeze master experiment manifest (5/152/38), Nonclinical Responses access probe, CLINSQL GPT-5-mini live validation pilot results (+5 more)

### Community 49 - "Phase C1/C2 Data Policy"
Cohesion: 0.18
Nodes (14): Phase D: 190 validation then 443 test, Phase C.1 technical pilot PASS 5/5, CLINSQL clinical_rubric_scorer.py (official scorer), Phase C.1 data handling decision, Phase C.1 limits (256 MiB/SQL, 3.75 GiB aggregate), Phase C.1 extended BigQuery budget (v5), v5 budget 16 GiB/SQL, 160 GiB aggregate, Five pinned pilot cases (pilot_5_validation_development_v1) (+6 more)

### Community 50 - "Phase A BigQuery Smoke"
Cohesion: 0.20
Nodes (12): Gate before MIMIC-IV SQL smoke, kltn-sql-reader service account (ADC impersonation), MeteredDatabase (no raw-row capture on real DB), READ_ONLY_LIKELY IAM status, Phase A MIMIC-IV SQL smoke approval checklist, BigQuery temporary result tables (~24h), Four Phase A smoke SQLs (63 MiB total cap), PhysioNet DUA 1.5.0 (+4 more)

### Community 51 - "MAC-SQL Mock Tests"
Cohesion: 0.20
Nodes (7): MACSQL, MockLLM, test_ours_runner_uses_pinned_catalog_without_reference_inputs(), test_chat_manager_source_rounds_and_refiner_state(), test_refiner_adapts_only_static_dialect_text_and_keeps_input_evidence(), test_selector_response_routing(), test_synthetic_samples_are_available_to_the_agent()

### Community 52 - "Metered Database"
Cohesion: 0.22
Nodes (3): _StopOnSecurityViolation, MeteredDatabase, test_dry_run_budget_error_carries_estimate_without_patient_rows()

### Community 53 - "Proposed System Docs"
Cohesion: 0.22
Nodes (11): Proposed Full Agentic Pipeline (Ours), Proposed System Final Status, ApprovedICDCatalog, PipelineDatabase.catalog_search, Frozen Few-shot Development Corpus v1 (145 examples), Schema RAG (31-table manifest), Proposed System Readiness, Clinical Knowledge Catalog Loader (+3 more)

### Community 54 - "Ours Catalog & Credit"
Cohesion: 0.18
Nodes (11): Ours (Proposed Full Agentic System), Benchmark Execution Budget Plan, Five-case Pilot Capacity Bounds per Method, Dry-run Query Cap Headroom Rule, Research Credit Envelope (VND, RESEARCH_CREDIT_AWARE), Shared SQL Budget Ledger (reserve/reconcile), Clinical Catalog Export Final Status, MIMIC-IV Clinical Dictionary Catalog (204,275 rows) (+3 more)

### Community 55 - "Equivalence Selection"
Cohesion: 0.30
Nodes (7): resolve(), pair(), test_equivalent_candidates_have_a_canonical_representative(), test_equivalent_class_must_consistently_beat_other_candidates(), test_evidence_alignment_preserves_literals_and_actual_source_spans(), test_nontransitive_equivalence_claims_are_rejected(), test_unknown_is_not_equivalent_and_cycles_do_not_select()

### Community 56 - "Sequential RAG Retrieval"
Cohesion: 0.23
Nodes (4): catalog_search(), schema_first(), SequentialRAG, terms()

### Community 57 - "Execution Approval"
Cohesion: 0.20
Nodes (3): ExecutionApproval, test_transport_timeout_cancels_job_and_permission_error_propagates(), test_phase_a_cli_is_offline_until_completed_approval()

### Community 58 - "BigQuery Schema Manifest Docs"
Cohesion: 0.27
Nodes (10): Baseline Adaptation Log, BigQuery Metadata Integration Report, INFORMATION_SCHEMA Metadata Preflight, MIMIC-IV v3.1 31-table BigQuery Schema Manifest, BigQuery Readiness Audit, Legacy PostgreSQL/Mini Test Collection Failures, schema_records_from_manifest (Schema RAG input), CLINSQL Result Comparison Policy (+2 more)

### Community 59 - "Baseline Fidelity Progress"
Cohesion: 0.20
Nodes (9): CLINSQL CoT + Self-Refinement Baseline, GPT-5-mini (gpt-5-mini-2025-08-07), Ours 145-example Development Few-shot Corpus, SDE GPT-5-mini Chat Completions Transport, Baseline Fidelity Progress (Phase C.1), PAPER_SOURCE_LOCK.json / paper_sources.py, Experiment Reproducibility Manifest (PRE_FREEZE), Master Question-only Validation Split Manifest (152 dev / 38 internal-check) (+1 more)

### Community 60 - "Official Scorer & Judge Docs"
Cohesion: 0.22
Nodes (11): BigQuery SQL Execution Preparation Report, Constant SELECT 1 Smoke Execution, kltn-sql-reader Service Account (ADC impersonation), MeteredDatabase (no raw rows logging), READ_ONLY_LIKELY IAM Status, ResultArtifactStore (restricted results), Controlled BigQuery Execution Report (Phase A), BigQueryAdapter (SQLGlot single SELECT/CTE guard) (+3 more)

### Community 61 - "Paper Algorithm Audit"
Cohesion: 0.24
Nodes (10): ADAPTED_JUDGE_GPT5MINI_2025_08_07, Pilot SQL Scores (CoT 0.293030, SDE-SQL 0.213030), CLINSQL Judge Backend Status, clinsql-rubric CLI (pilot-manifest / config-hash / run), CLINSQL_NATIVE_AZURE_JUDGE (gpt-5-chat), Official CLINSQL Evaluator Status, clinical_rubric_scorer.py (Official CLINSQL Scorer), CLINSQL Scorer Reproduction Report (+2 more)

### Community 62 - "Legacy Dataset Tests"
Cohesion: 0.29
Nodes (9): CLINSQL research branch (src/ehrqa/clinsql), Paper algorithm audit of three baselines, CLINSQL CoT + Self-Refinement, MAC-SQL (Selector -> Decomposer -> Refiner), SDE-SQL (exploration -> generation -> refinement), Original source of three paper systems, PAPER_SOURCE_LOCK.json / paper_sources.py verification, Phase B CLINSQL/BigQuery offline integration report (+1 more)

### Community 65 - "Security Rejection Tests"
Cohesion: 0.31
Nodes (3): AmbiguousModelRequest, OpenAIModelProvider, test_openai_transport_serialization_usage_and_ambiguous_failure()

### Community 66 - "Experiment Protocol & Data"
Cohesion: 0.22
Nodes (9): Data README, src/ehrqa/clinsql/dataset.py Question-only Loader, Legacy PostgreSQL/Vietnamese App Data (mimic_examples, test_dataset), MIMIC-IV Dataset Documentation, MIMIC-IV v3.1, Documentation Index README, CLINSQL 2026 Experiment Protocol, CLINSQL 2026 Benchmark (190 validation / 443 test) (+1 more)

### Community 67 - "Strict Fidelity & Model Pin"
Cohesion: 0.24
Nodes (9): gpt-5-mini-2025-08-07 Pinned Model, clinical_rubric_scorer (official CLINSQL judge), Strict Source Fidelity and Pilot Status, BENCHMARK_LLM Model Pin, Official Evaluator Adapter (SQL Score / Execution Score), RESTRICTED_EVIDENCE_EGRESS Gate, Task 8 GPT-5-mini Recovery and Live Results, EvidenceRouter (Qwen loopback routing) (+1 more)

### Community 68 - "Task 8 Approval & Live Pilot"
Cohesion: 0.24
Nodes (9): Task 8 Combined Approval, MAC-SQL column_samples Variant, Final User Attestation, Five Locked Pilot Cases, Local Catalog Export (d_icd_*, d_labitems, d_items), MAC-SQL metadata_only (MAC_SQL_RESTRICTED_ADAPTATION), Three-Method Live Pilot Results, BigQuery-side Column Sampling (+1 more)

### Community 70 - "Guard Refinement Tests"
Cohesion: 0.29
Nodes (7): SecurityRejected, test_cot_refines_guard_rejected_catalog_without_executing_it(), complete(), dry_run(), execute(), test_source_aligned_cot_does_not_refine_a_guard_rejection(), dry_run()

### Community 71 - "BigQuery Transport Fakes"
Cohesion: 0.20
Nodes (3): FakeClient, test_bigquery_real_transport_contract_marks_result_byte_cap_incomplete(), result()

### Community 72 - "Implementation Status (VI)"
Cohesion: 0.31
Nodes (7): Huong dan cai dat va van hanh (legacy PostgreSQL), ChromaDB collections (icd_dictionary, schema_dictionary, sql_examples, sql_examples_eval), SEND_RESULTS_TO_LLM flag, Trang thai trien khai CLINSQL (Implementation status), FewShotIndex (validation-development only), Phase C.2 offline continuation, OFFICIAL_SCORE_NOT_AVAILABLE status

### Community 73 - "SDE n=9 Error & Fix"
Cohesion: 0.36
Nodes (9): SDE Multichoice Compatibility, OpenAI Chat Completions API, SDE n=9 Error Root Cause, grouped_3x3 (SDE_GROUPED_3X3_REQUEST_ADAPTATION), n=9 integer_above_max_value Error, SDE-SQL Fidelity Final, _most_consistent self-consistency voting, native_three_vote_judge (+1 more)

### Community 74 - "Paper Environment Locks"
Cohesion: 0.25
Nodes (9): CLINSQL Py3.12 Windows Lock, MAC-SQL Py3.12 Windows Lock, openai==0.28.1 (MAC-SQL legacy SDK), SDE-SQL Py3.12 Windows Lock, sqlglot==25.6.1 (SDE-SQL), Paper Environments README, .venv_papers Isolated Environments, CLINSQL Proprietary Requirements (+1 more)

### Community 75 - "Result Multiset Matching"
Cohesion: 0.31
Nodes (6): _same_cell(), _same_row(), _unordered_multiset_equal(), assign(), test_float_tolerance_and_null_distinction(), test_unordered_multiset_keeps_duplicates()

### Community 77 - "Phase C1 Readiness Docs"
Cohesion: 0.29
Nodes (8): FourMethodApproval (phase=four_method_validation_pilot), ResultArtifactStore with restricted ACL, PersistentSQLBudgetLedger, Phase C.1 GPT-5-mini + CLINSQL pilot readiness, benchmark_approval.py (BenchmarkExecutionApproval), phase-c1-pilot CLI (plan/execute/resume/stage/retention), pilot_api_budget.py token/cost reservation ledger, Phase C.1 regression report

### Community 78 - "MAC-SQL Fidelity Docs"
Cohesion: 0.32
Nodes (8): MAC-SQL metadata_only variant, gpt-5-mini-2025-08-07 snapshot, MAC-SQL fidelity for CLINSQL and MIMIC-IV v3.1, Guarded BigQuery column-value sampler, MAC-SQL Decomposer, MAC-SQL Refiner / ChatManager, MAC-SQL Selector (pruning and value sampling), openai_provider.py Responses transport

### Community 79 - "Legacy Boundary & Architecture"
Cohesion: 0.29
Nodes (8): Kien truc va trang thai (Full agentic architecture), ehrqa.agentic core pipeline, Legacy PostgreSQL/MIMIC Mini path, Legacy EHRSQL/PostgreSQL/MIMIC Mini boundary audit, datetimesevents vs datetimeevents naming discrepancy, ehrqa.text2sql neutral contracts/security/logging, SQLGlot CTE lineage validator, _missing_join_key composite icd_version JOIN check

### Community 80 - "App Config & Settings"
Cohesion: 0.29
Nodes (3): application_pipeline(), ModelSettings, Config

### Community 81 - "Official Evaluator Adapter"
Cohesion: 0.32
Nodes (4): OfficialClinSQLEvaluator, test_evaluation_staging_and_saved_prediction_scoring_are_separate(), test_native_scorer_injection_uses_source_logic_without_api(), factory()

### Community 83 - "Probe Completeness Tests"
Cohesion: 0.25
Nodes (3): test_final_result_completeness_checks_total_after_all_pages(), test_probe_summary_uses_completed_row_count_without_iterating(), execute()

### Community 84 - "Research Validity Regression"
Cohesion: 0.33
Nodes (7): Research Validity Regression Report, BigQueryAdapter, execution_errors.py Failure Taxonomy, paper_sources.py Source Lock Verifier, READ_ONLY_LIKELY_WITH_APPROVED_RISK Execution Gate, SQL Guard (BigQuery SELECT allowlist), PAPER_SOURCE_LOCK.json

### Community 85 - "Pipeline Database"
Cohesion: 0.33
Nodes (3): PipelineDatabase, test_pipeline_keeps_column_names_and_types_from_executor(), execute()

### Community 86 - "LLM Client Tests"
Cohesion: 0.33
Nodes (3): test_auth_failure_not_retried_or_leaked(), test_provider_request_without_network(), handler()

### Community 87 - "Pilot SQL Root Cause"
Cohesion: 0.40
Nodes (5): CLINSQL Pilot SQL Root Cause Analysis, Semantic / Time-window SQL Errors, Strict Result Shape Diagnostic, test_prompt_project_adaptation_changes_only_two_dataset_references, test_successful_extra_projection_does_not_trigger_baseline_refinement

### Community 88 - "Task 8 Repair Results"
Cohesion: 0.33
Nodes (6): MAC-SQL Selector Agent, Task 8 Repair and Execution Results, DATABASE_PREPROCESSING_BUDGET / CASE_EXECUTION_BUDGET Scopes, HISTORICAL_PILOT Profile, MODEL_PARAMETER_COMPATIBILITY_ADAPTATION, Selector._get_value_examples_str (source formatter)

### Community 92 - "Validation & Test Splits"
Cohesion: 0.67
Nodes (4): CLINSQL Test 443 Results, Sealed 443-case Test Split, Validation 190 Results, master_experiment_pre_freeze_v1.json (152/38 split)

### Community 94 - "Project Requirements"
Cohesion: 0.67
Nodes (3): Project Requirements, Dev Requirements, sqlglot>=30,<31 (main project)

## Knowledge Gaps
- **93 isolated node(s):** `find_most_consistent_sql Result-set Majority Selection`, `MAC Selector _is_need_prune Threshold`, `Benchmark Execution Budget Plan`, `Dry-run Query Cap Headroom Rule`, `INFORMATION_SCHEMA Metadata Preflight` (+88 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 551 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SDE-SQL Fidelity Final` connect `SDE n=9 Error & Fix` to `SDE Subquery Extraction`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **What connects `find_most_consistent_sql Result-set Majority Selection`, `MAC Selector _is_need_prune Threshold`, `Benchmark Execution Budget Plan` to the rest of the system?**
  _93 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Rubric Evaluation & Judges` be split into smaller, more focused modules?**
  _Cohesion score 0.057946069994262765 - nodes in this community are weakly interconnected._
- **Why does `Critical-first Sequential Weighted Rubric Aggregation (Algorithm 1)` connect `Paper Algorithm Audit` to `Rubric Evaluation & Judges`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Should `SQL Budget Ledger` be split into smaller, more focused modules?**
  _Cohesion score 0.058173076923076925 - nodes in this community are weakly interconnected._
- **Why does `ADAPTED_JUDGE_GPT5MINI_2025_08_07` connect `Paper Algorithm Audit` to `Baseline Fidelity Progress`, `Ours Catalog & Credit`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Should `Four-Method Pilot Runner` be split into smaller, more focused modules?**
  _Cohesion score 0.08672659968270756 - nodes in this community are weakly interconnected._