# V5 — metadata-backed SQL canonicalization

Giữ nguyên toàn bộ output model DeepSeek Flash của V3, không fine-tune và không gọi lại model trên test. V5 thêm các đề xuất SQL bằng compiler metadata; SQL cuối có thể khác SQL model ở literal được chuẩn hóa, với đầy đủ nguồn/evidence. Không thay gold, database hay official scorer.

## Kết quả đã xác minh

Đủ1.167câu test; primary được chấm bằng Docker official scorer và khớp từng câu với host. [Báo cáo cuối](runs/deepseek_flash_v5_20261029_r1/FINAL_REPORT.md), [số liệu JSON](runs/deepseek_flash_v5_20261029_r1/FINAL_RESULTS.json).

- **RS10=74,89**, nhỉnh hơn mốc công bố ProbGate74,21. EX=92,29%, VSR/coverage=75,66%, precision trong883câu được trả lời=97,62%.
- 862SQL đúng;222từ chối đúng;21trả lời sai;62từ chối nhầm. Paper có9câu sai, nên không khẳng định mọi khía cạnh reliability đều tốt hơn.
- SoV3 cùng outputmodel:43câu từ chối nhầm thành đúng,0câu xấu đi; RS10+3,68điểm. SoV4:21câu tốt hơn,0xấu đi.
- ChênhRS10 so paper từ số chưa làm tròn=+0,6855điểm; pairedbootstrap95%[-9,08;10,20] chứa0. Chưa có bằng chứng vượt trội thống kê so paper.
- TuneRS10=96,33; audit100câu mớiRS10=96,00. Test được replay từSQLcache,0modelcallmới trong bước testV5; compute generationnguồn vẫn được tính.

Mỗi policy chọn từdev, nhưng phiên bản cuối được chốt sau khi đã quan sát điểm test nhiều vòng. Vì vậy đây là exploratory/test-informed development; cần dữ liệu đánh giá mới để có kết luận xác nhận độc lập.

## Quy tắc compiler

- Chỉ khôi phục prefix ICD khi suffix khớp **đúng một code đầy đủ trong cùng dictionary**. Không đoán khi không có hoặc có nhiều ánh xạ; code đầy đủ được giữ nguyên.
- Chỉ đổi title gần giống dấu câu khi câu hỏi chứa đúng một surface thật trong cùng nhóm collision và metadata chứng minh các code khác nhau. Đây là binding theo literal đã có trong câu hỏi, không thêm bệnh/thực thể mới.
- Chỉ xem lại SQL từng bị GEF vì kết quả rỗng nếu SQL ban đầu valid, generation kết thúc, không có hard issue và compiler thực sự có phép thay đổi đã chứng minh. Model trả `null`, câu bị cắt hoặc SQL lỗi cú pháp không được hồi sinh.
- Giữ `v5_original_record` bất biến. `namespace_repair` ghi source SQL, proposal SQL, từng literal đổi và bằng chứng dictionary. Proposal chạy read-only và xây lại fingerprint theo numeric3precision, toàn bộ dòng/shape/duplicate, không cap100 khi bỏ phiếu.

12kiểm tra mới đã qua, gồm uniqueness/ambiguity, giữ nguyên source, scope của literal, không đổi literal ngoài ICD, không hồi sinh model-null/truncation, rawbaseline scoring và audit disjointness. Generation V3 đã có42kiểm tra trước đó.

## Chọn policy và audit

5policy khai báo trước gồm raw strict3 và các canonical variants. Chọn theo RS10 trên300tune, coverage≥35%. PolicyV5 chọn `strict3_canonical`: tuneRS10=96,33; coverage76,33%. Tuning dùng lại câu hỏi phát triển nhưng contextRAG được tạo lại vì nhóm holdout đổi.

100auditV5 là nhóm mới, không trùng những câu đã chấm trongV2/V3/V4 hoặc rule evidence. Toàn bộ400tune+audit bị loại khỏi các ví dụRAG khi phát triển. Sau audit giữ nguyên policy rồi mới replay testSQLV3.

Finalgeneration vẫn là train+dev6.287câu củaV3. Không có model call mới trên test ởV4/V5, nhưng phải tính compute generationV3 đã tạo candidate. Báo cáo tách API incremental và effective bao gồm cache; không cộng hai lần các response tái sử dụng.

## Lịch sử được giữ nguyên

- [V2 đầy đủ](../ours_improved_v2/runs/deepseek_flash_v2b_20261028/FINAL_REPORT.md): RS10=0,00.
- [V3](../ours_improved_v3/runs/deepseek_flash_v3_20261029_r2/FINAL_REPORT.md): RS10=71,21.
- [V4](../ours_improved_v4/runs/deepseek_flash_v4_20261029_r1/FINAL_REPORT.md): RS10=73,09.

V5 được phát triển từ lỗi tuning về code prefix/title và numeric precision. Đã biết điểm test tổng thể các vòng trước, nên đây là exploratory, không gọi test cũ là holdout độc lập. Không đọc lỗi test từng câu để lập rule hoặc chọn policy. Không chỉ giữ phiên bản điểm cao.

## Chạy

Dùng Python`.venv` từ projectroot, chạy `experiments/ours_improved_v5/run_v5.py --run-name deepseek_flash_v5_20261029_r1 --phase tune --workers 8`, sau đó cùngrun-name với phase`audit`, rồi`test`. Phase test chỉ chuẩn hóa/chạySQLcache và chấm; không gọiLLM. `report_v5.py --run-name deepseek_flash_v5_20261029_r1 --docker-primary-only` đối soát đủ primary với Docker; secondary routes ghi rõ official scorer trên host. Dùng`--docker` nếu cần đối soát cả4nhánh.

Key đọc từ`.env`, không truyền quaCLI. Không tự mua thêm credit/chuyển model. Cache chỉ dùng lại khi hashrequest giống hệt. LỗiAPI dừng có checkpoint, không padding câu thiếu thànhnull.

[ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/): RS10=74,21 là số công bố đã replaycache; EX77,73% tính bổ sung từcache. Khác model/fine-tuning, knowledge và inference budget, nên vượt điểm paper không tự chứng minh ưu thế phương pháp trong điều kiện đồng nhất. Phạm vi hiện tại là English→SQL benchmark, không xác nhận ASR/SQL→text hoặc triển khai lâm sàng.
