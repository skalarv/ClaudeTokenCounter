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
| F43 | Window constructs and renders four rows              | tests/test_ui_smoke.py::test_window_constructs_and_renders           |
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
