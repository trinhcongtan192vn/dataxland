# Tasks: Lớp chỉ số

- [x] T001 Schema YAML, `dimensions.yml`, `sources.yml`; 54 chỉ số giai đoạn 1 (03 §3)
- [x] T002 `semantic/build.py`: kiểm tra (03 §2.1), sinh model Cube, `metrics.json`, `handbook.json`, `ai_context.md`
- [x] T003 `cube/cube.js`: checkAuth, queryRewrite, đa khách, refresh theo danh sách khách, pre-aggregation; `local_duckdb.js`, `run.js`
- [x] T004 Bộ máy truy vấn: registry, periods, cube_client, expr, engine; cảnh báo dữ liệu; nhật ký truy vấn
- [x] T005 Router `/v1/metrics` (query, list, key-numbers, flags, chi tiết chỉ số)
- [x] T006 Ba số chính (03 §5), cờ cần chú ý (03 §7), phát hiện bất thường + `/v1/internal/anomalies/run` (03 §8)
- [x] T007 `semantic/check_versions.py` trong CI; `ops/release_metrics.py` trong deploy (03 §6)
- [x] T008 Test 03 §11: `semantic/tests/test_semantic.py`, `services/api/tests/test_metrics.py`, `test_metric_rules.py`, `test_cube_live.py` (đánh dấu `cube`), giá trị kỳ vọng ở `semantic/tests/expected/`
- [x] T009 ADR 0002 #19–#22
