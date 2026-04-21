# TokenFollow Feature Matrix

Each row is a user-visible behavior backed by at least one pytest test.
`scripts/check_matrix.py` enforces that every test id listed here is
collected by pytest.

| #   | Feature                                        | Test id                                             |
|-----|------------------------------------------------|-----------------------------------------------------|
| F01 | Parse usage block from JSONL                   | tests/test_parser.py::test_parse_valid_line         |
| F02 | Skip malformed JSONL line                      | tests/test_parser.py::test_skip_malformed           |
| F03 | Incremental byte-offset re-read                | tests/test_parser.py::test_incremental_reread       |
| F04 | 5h window anchored after gap                   | tests/test_aggregator.py::test_window_anchor_after_gap |
| F05 | Weekly rolling 7-day cutoff                    | tests/test_aggregator.py::test_weekly_split_by_family |
| F06 | Model family classification                    | tests/test_aggregator.py::test_unknown_model_ignored_in_weekly |
| F07 | Cache-read weighting                           | tests/test_aggregator.py::test_cache_read_weight    |
| F08 | Hybrid budget (defaults + observed max)        | tests/test_budget.py::test_observed_bump_on_exceed  |
| F09 | Observed never decreases                       | tests/test_budget.py::test_observed_never_decreases |
| F10 | Config persistence round-trip                  | tests/test_budget.py::test_position_roundtrip       |
| F11 | 3-bar + GPU UI renders                         | tests/test_ui_smoke.py::test_window_constructs_and_renders |
| F12 | Color banding thresholds                       | tests/test_ui_smoke.py::test_band_color_thresholds  |
| F13 | Always-on-top preserved on restore             | tests/test_ui_smoke.py::test_topmost_reasserted_on_restore |
| F14 | GPU source auto-detection                      | tests/test_gpu.py::test_picks_nvidia_when_available |
| F15 | GPU perfcounter clamp                          | tests/test_gpu.py::test_perfcounter_clamp_upper     |
| F16 | GPU timeout → last-good                        | tests/test_gpu.py::test_timeout_returns_last_good   |
| F17 | GPU unavailable → N/A in UI                    | tests/test_ui_smoke.py::test_gpu_row_shows_na_when_none |
| F18 | End-to-end fresh account                       | tests/test_integration.py::test_golden_fresh        |
| F19 | End-to-end mid-5h window                       | tests/test_integration.py::test_golden_mid_window   |
| F20 | End-to-end Opus near weekly cap                | tests/test_integration.py::test_golden_opus_near_cap |
| F21 | End-to-end after idle (no active window)       | tests/test_integration.py::test_golden_after_idle   |
