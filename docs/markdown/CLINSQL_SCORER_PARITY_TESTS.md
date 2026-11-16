# CLINSQL scorer parity tests

**Kết quả offline: 46 PASS** trong sáu nhóm kiểm thử. Cấu trúc và ID của cả hai rubric tree hợp lệ cho 190/190 validation và 443/443 test cases. Không chấm tập test.

`tests/test_rubric_evaluation.py` chạy scorer gốc đã khóa và adapter với cùng cây, cùng prompt và mock binary grades. So sánh case scores, leaf details, thứ tự và nội dung prompt. Coverage gồm all-pass, critical fail, noncritical weighted fail, sequential fail, nested weights, difficulty/domain/split aggregation, resume, response rỗng/sai, API failure, thiếu SQL/CSV, retry 429, call budget, hai backend giả lập và CSV types.

Lỗi parse/API và thiếu file được kiểm tra theo fail-closed contract. Grade thực sự bằng 0 vẫn được lưu và tính theo source.

Lệnh kiểm thử từ thư mục repo trong PowerShell:

```powershell
$env:PYTHONPATH='src;.'
python -m pytest -q --basetemp .pytest_task9_release tests/test_rubric_evaluation.py tests/test_official_scorer_source.py tests/test_four_method_live.py tests/test_clinsql_foundation.py tests/test_pilot5_diagnostic.py tests/test_phase_b_integration.py
```
