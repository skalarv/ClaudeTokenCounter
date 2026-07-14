# TokenFollow Feature Matrix

Each row is a behavior backed by at least one pytest test. The matrix is
two-way enforced by `scripts/check_matrix.py`:

1. Every test id listed here must be collected by pytest.
2. Every test id collected by pytest must appear in this matrix, **or**
   carry the `@pytest.mark.matrix_exempt` marker.

| #   | Feature                                              | Test id                                                              |
|-----|------------------------------------------------------|----------------------------------------------------------------------|
| F01 | Parse valid usage block from JSONL                   | tests/test_parser.py::test_parse_valid_line                          |
| F02 | Skip malformed JSONL line                            | tests/test_parser.py::test_skip_malformed                            |
| F03 | Naive timestamp interpreted as UTC                   | tests/test_parser.py::test_naive_timestamp_parsed_as_utc             |
| F04 | Incremental byte-offset re-read across calls         | tests/test_parser.py::test_incremental_reread                        |
| F05 | Unchanged file is skipped on subsequent scan         | tests/test_parser.py::test_unchanged_file_skipped                    |
| F06 | File truncation / rotation resets offset             | tests/test_parser.py::test_truncation_resets_offset                  |
| F07 | Empty / malformed lines mixed with valid are skipped | tests/test_parser.py::test_empty_lines_and_bad_lines_skipped         |
| F08 | Missing projects root tolerated (no crash)           | tests/test_parser.py::test_missing_projects_dir_is_ok                |
| F09 | Empty projects root yields empty list                | tests/test_parser.py::test_empty_projects_dir                        |
| F10 | save_cache writes offsets diagnostic file            | tests/test_parser.py::test_save_cache_writes_offsets                 |
| F11 | Aggregator with no records returns zero snapshot     | tests/test_aggregator.py::test_empty_records                         |
| F12 | 5h window anchored after gap >=5h                    | tests/test_aggregator.py::test_window_anchor_after_gap               |
| F13 | Exactly-5h gap starts a new window                   | tests/test_aggregator.py::test_exactly_5h_gap_starts_new_window      |
| F14 | No active 5h window when idle >=5h                   | tests/test_aggregator.py::test_no_active_window_when_idle            |
| F15 | Weekly rolling 7-day cutoff splits opus / sonnet+haiku | tests/test_aggregator.py::test_weekly_split_by_family              |
| F16 | Cache-read tokens weighted (default 0.1)             | tests/test_aggregator.py::test_cache_read_weight                     |
| F17 | Weekly reset = oldest record + 7d                    | tests/test_aggregator.py::test_weekly_resets_at_oldest_plus_7d       |
| F18 | Unknown model family ignored in weekly buckets       | tests/test_aggregator.py::test_unknown_model_ignored_in_weekly       |
| F19 | First run creates default config.json                | tests/test_budget.py::test_first_run_creates_config                  |
| F20 | Corrupted config moves to .bak and regenerates       | tests/test_budget.py::test_corrupted_config_moves_to_bak             |
| F21 | Hybrid budget bumps observed_max on exceed           | tests/test_budget.py::test_observed_bump_on_exceed                   |
| F22 | observed_max never decreases                         | tests/test_budget.py::test_observed_never_decreases                  |
| F23 | budgets / observed / weights properties exposed      | tests/test_budget.py::test_budgets_and_weights_exposed               |
| F24 | Window position round-trips across instances         | tests/test_budget.py::test_position_roundtrip                        |
| F25 | Partial config merged with defaults                  | tests/test_budget.py::test_partial_config_merged_with_defaults       |
| F26 | save() persists current state                        | tests/test_budget.py::test_save_persists                             |
| F27 | Config merge handles non-dict default value          | tests/test_budget.py::test_merge_with_non_dict_default_value         |
| F28 | Config merge handles non-dict data when defaults dict | tests/test_budget.py::test_merge_data_not_dict_when_defaults_is_dict |
| F29 | GPU source picks nvidia-smi when available           | tests/test_gpu.py::test_picks_nvidia_when_available                  |
| F30 | GPU source falls back to perfcounter                 | tests/test_gpu.py::test_falls_back_to_perfcounter_when_nvidia_missing |
| F31 | GPU source = "none" when both probes fail            | tests/test_gpu.py::test_source_none_when_both_fail                   |
| F32 | nvidia-smi single GPU parsed as int                  | tests/test_gpu.py::test_nvidia_parse_single_gpu                      |
| F33 | nvidia-smi multi-GPU takes max                       | tests/test_gpu.py::test_nvidia_parse_multi_gpu_takes_max             |
| F34 | nvidia-smi garbled output -> None                    | tests/test_gpu.py::test_nvidia_read_returns_none_on_garbled_output   |
| F35 | Non-zero subprocess returncode -> source none        | tests/test_gpu.py::test_nvidia_nonzero_returncode_returns_none       |
| F36 | _parse skips empty lines in stdout                   | tests/test_gpu.py::test_parse_skips_empty_lines                      |
| F37 | _parse returns None on empty stdout                  | tests/test_gpu.py::test_parse_returns_none_on_empty_stdout           |
| F38 | Perfcounter > 100 clamped to 100                     | tests/test_gpu.py::test_perfcounter_clamp_upper                      |
| F39 | Perfcounter < 0 clamped to 0                         | tests/test_gpu.py::test_perfcounter_clamp_lower                      |
| F40 | Subprocess timeout falls back to last-good           | tests/test_gpu.py::test_timeout_returns_last_good                    |
| F41 | source="none" -> read() returns None                 | tests/test_gpu.py::test_none_source_read_is_none                     |
| F42 | Color band thresholds (green / amber / red)          | tests/test_ui_smoke.py::test_band_color_thresholds                   |
| F43 | Window constructs and renders all rows               | tests/test_ui_smoke.py::test_window_constructs_and_renders           |
| F44 | GPU row shows N/A when percent is None               | tests/test_ui_smoke.py::test_gpu_row_shows_na_when_none              |
| F45 | Close callback fires on user close                   | tests/test_ui_smoke.py::test_close_callback_fires                    |
| F46 | Always-on-top reasserted on restore                  | tests/test_ui_smoke.py::test_topmost_reasserted_on_restore           |
| F47 | _fmt_tokens picks correct unit for small / K / M     | tests/test_ui_smoke.py::test_fmt_tokens_branches                     |
| F48 | _fmt_delta returns "idle" when target is None        | tests/test_ui_smoke.py::test_fmt_delta_idle_when_target_none         |
| F49 | _fmt_delta returns "resetting" when past             | tests/test_ui_smoke.py::test_fmt_delta_resetting_when_past           |
| F50 | _fmt_delta minutes-only branch                       | tests/test_ui_smoke.py::test_fmt_delta_minutes_only                  |
| F51 | restore_position applies geometry                    | tests/test_ui_smoke.py::test_restore_position_applies_geometry       |
| F52 | restore_position with None coords is a no-op         | tests/test_ui_smoke.py::test_restore_position_none_coords_is_noop    |
| F53 | current_position reads back placed coords            | tests/test_ui_smoke.py::test_current_position_after_restore          |
| F54 | current_position returns (None, None) on bad geometry | tests/test_ui_smoke.py::test_current_position_returns_none_on_bad_geometry |
| F55 | End-to-end fresh account snapshot                    | tests/test_integration.py::test_golden_fresh                         |
| F56 | End-to-end mid-5h-window snapshot                    | tests/test_integration.py::test_golden_mid_window                    |
| F57 | End-to-end Opus-near-weekly-cap snapshot             | tests/test_integration.py::test_golden_opus_near_cap                 |
| F58 | End-to-end after-idle snapshot (no active window)    | tests/test_integration.py::test_golden_after_idle                    |
| F59 | Projections exist and are idle on empty input        | tests/test_aggregator.py::test_projections_exist_and_are_idle_on_empty |
| F60 | Opus 5h projection basic burn-rate math              | tests/test_aggregator.py::test_opus_5h_projection_basic              |
| F61 | Trailing rate window excludes older records          | tests/test_aggregator.py::test_opus_5h_trailing_window_excludes_older_records |
| F62 | Rate is zero with no recent activity                 | tests/test_aggregator.py::test_opus_5h_rate_zero_when_no_recent_activity |
| F63 | Trailing rate window clamped to in-window elapsed    | tests/test_aggregator.py::test_opus_5h_trailing_window_clamped_to_window_elapsed |
| F64 | seconds_until_zero derived from remaining budget     | tests/test_aggregator.py::test_opus_5h_seconds_until_zero            |
| F65 | Projection may honestly exceed budget (overrun)      | tests/test_aggregator.py::test_opus_5h_projection_can_exceed_budget  |
| F66 | Budget stays at default when projection below it     | tests/test_aggregator.py::test_opus_5h_projection_respects_default_when_below |
| F67 | Opus 5h projection counts only opus records          | tests/test_aggregator.py::test_opus_5h_only_counts_opus_records      |
| F68 | Opus weekly projection basic burn-rate math          | tests/test_aggregator.py::test_opus_week_projection_basic            |
| F69 | Opus weekly projection idle without opus records     | tests/test_aggregator.py::test_opus_week_idle_when_no_opus_records   |
| F70 | aggregate() works without explicit rate_windows      | tests/test_aggregator.py::test_aggregate_default_rate_windows        |
| F71 | Aggregator tolerates missing 5h_opus budget key      | tests/test_aggregator.py::test_aggregate_tolerates_missing_5h_opus_key |
| F72 | First run writes 5h_opus defaults                    | tests/test_budget.py::test_first_run_has_5h_opus_defaults            |
| F73 | First run writes projection rate-window defaults     | tests/test_budget.py::test_first_run_has_rate_window_defaults        |
| F74 | budgets/observed expose 5h_opus keys                 | tests/test_budget.py::test_budgets_includes_5h_opus                  |
| F75 | maybe_bump learns 5h_opus peak from projection       | tests/test_budget.py::test_maybe_bump_5h_opus_from_projection        |
| F76 | Projection label shows proj / budget                 | tests/test_ui_smoke.py::test_projection_label_shows_proj_and_budget  |
| F77 | Projection label switches to overrun wording         | tests/test_ui_smoke.py::test_projection_overrun_label                |
| F78 | Projection label shows idle when no window           | tests/test_ui_smoke.py::test_projection_idle_label                   |
| F79 | Projection bar fill driven by projected_used         | tests/test_ui_smoke.py::test_projection_bar_fill_uses_projected_used |
| F80 | Projection bar pinned at 100% on overrun             | tests/test_ui_smoke.py::test_projection_pinned_at_100_on_overrun     |
| F81 | All ten overlay rows present                         | tests/test_ui_smoke.py::test_all_ten_rows_present                    |
| F82 | Continuous usage rolls into a new 5h window at +5h   | tests/test_aggregator.py::test_continuous_usage_starts_new_window_at_5h |
| F83 | Fable / Mythos models bucketed into week_fable       | tests/test_aggregator.py::test_fable_weekly_bucket                   |
| F84 | Fable records count toward the 5h total              | tests/test_aggregator.py::test_fable_counts_in_5h_total              |
| F85 | Fable 5h projection basic burn-rate math             | tests/test_aggregator.py::test_fable_5h_projection_basic             |
| F86 | Fable 5h projection excludes other families          | tests/test_aggregator.py::test_fable_5h_projection_excludes_other_families |
| F87 | Fable weekly projection basic burn-rate math         | tests/test_aggregator.py::test_fable_week_projection_basic           |
| F88 | Fable weekly projection idle without fable records   | tests/test_aggregator.py::test_fable_week_idle_when_no_fable_records |
| F89 | Aggregator tolerates pre-Fable budget dicts          | tests/test_aggregator.py::test_aggregate_tolerates_missing_fable_keys |
| F90 | First run writes Fable defaults                      | tests/test_budget.py::test_first_run_has_fable_defaults              |
| F91 | Pre-Fable config transparently gains fable keys      | tests/test_budget.py::test_pre_fable_config_gains_fable_keys         |
| F92 | maybe_bump learns Fable weekly and 5h peaks          | tests/test_budget.py::test_maybe_bump_fable                          |
| F93 | Fable projection rows render with labels             | tests/test_ui_smoke.py::test_fable_projection_rows_render            |
| F94 | UI tolerates snapshots missing Fable fields          | tests/test_ui_smoke.py::test_render_tolerates_missing_fable_fields   |
| F95 | End-to-end Fable + Sonnet mixed snapshot             | tests/test_integration.py::test_golden_fable_mixed                   |
| F96 | OAuth token read from top-level credentials          | tests/test_account.py::test_token_top_level                          |
| F97 | OAuth token read from nested credentials             | tests/test_account.py::test_token_nested_one_level                   |
| F98 | Missing credentials file -> no token                 | tests/test_account.py::test_token_missing_file                       |
| F99 | Corrupt credentials JSON -> no token                 | tests/test_account.py::test_token_bad_json                           |
| F100 | Credentials without accessToken -> no token         | tests/test_account.py::test_token_absent_in_json                     |
| F101 | Non-dict credentials JSON -> no token               | tests/test_account.py::test_token_json_not_dict                      |
| F102 | Live /usage payload shape parsed (limits array)     | tests/test_account.py::test_parse_real_shape                         |
| F103 | Fallback to five_hour/seven_day fields              | tests/test_account.py::test_parse_fallback_five_hour_seven_day       |
| F104 | Malformed limit entries skipped                     | tests/test_account.py::test_parse_skips_malformed_limit_entries      |
| F105 | Naive reset timestamp treated as UTC                | tests/test_account.py::test_parse_naive_timestamp_treated_as_utc     |
| F106 | Empty / garbage payload -> None                     | tests/test_account.py::test_parse_empty_or_bad_payload               |
| F107 | Monitor fetch success; token via env not argv       | tests/test_account.py::test_monitor_fetch_success                    |
| F108 | Monitor caches within refresh window                | tests/test_account.py::test_monitor_caches_within_refresh_window     |
| F109 | Monitor keeps last-good on fetch failure            | tests/test_account.py::test_monitor_keeps_last_good_on_failure       |
| F110 | Monitor tolerates subprocess exception              | tests/test_account.py::test_monitor_runner_exception_returns_none    |
| F111 | Monitor skips fetch when credentials missing        | tests/test_account.py::test_monitor_missing_credentials              |
| F112 | Monitor tolerates garbage stdout (proxy page)       | tests/test_account.py::test_monitor_garbage_stdout                   |
| F113 | Default spawner runs thunk on a thread              | tests/test_account.py::test_monitor_default_spawner_runs_on_thread   |
| F114 | No duplicate fetch while one is in flight           | tests/test_account.py::test_monitor_no_refetch_while_in_flight       |
| F115 | Account severity overrides colour thresholds        | tests/test_ui_smoke.py::test_account_color_severity_wins              |
| F116 | Account session percent drives 5h row               | tests/test_ui_smoke.py::test_account_drives_five_hour_row             |
| F117 | Week · All row shows account weekly percent         | tests/test_ui_smoke.py::test_week_all_row_shows_account_percent       |
| F118 | Week · All row shows N/A without account data       | tests/test_ui_smoke.py::test_week_all_row_na_without_account          |
| F119 | Scoped Fable account limit drives Week · Fable row  | tests/test_ui_smoke.py::test_scoped_fable_limit_drives_week_fable_row |
| F120 | Rows fall back to local estimates without account   | tests/test_ui_smoke.py::test_rows_fall_back_to_estimates_without_account |
| F121 | Account config defaults written on first run        | tests/test_budget.py::test_account_config_defaults                    |
| F122 | Account polling can be disabled in config           | tests/test_budget.py::test_account_config_can_be_disabled             |
