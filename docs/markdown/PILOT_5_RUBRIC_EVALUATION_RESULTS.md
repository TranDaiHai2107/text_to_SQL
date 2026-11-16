# CLINSQL CoT pilot rubric evaluation

5/5 predictions và complete result artifacts đã qua restricted staging thực tế. Native pandas đọc được số hàng khớp audit. Không có gold file trong staged samples. Các CSV tạm đã được xóa. [Staging audit](../../results/task9_pilot_staging_check.json)

- Diagnostic Procedures Easy/058 · staging PASS, 9 SQL + 5 Results leaves, chưa chấm.
- Vital Signs Monitoring Easy/044 · staging PASS, 9 SQL + 5 Results leaves, chưa chấm.
- Laboratory Results Analysis Medium/079 · staging PASS, 11 SQL + 17 Results leaves, chưa chấm.
- Medication Management Medium/012 · staging PASS, 14 SQL + 11 Results leaves, chưa chấm.
- Patient Demographics and Admissions Hard/058 · staging PASS, 15 SQL + 14 Results leaves, chưa chấm.

**0/5 rubric scores.** Cần cấu hình deployment/snapshot có thể xác minh, phạm vi truyền đầy đủ result rows và budget cho 110 leaf requests trước retry, cộng preflight. Hạn artifact hiện tại nằm trong khoảng 20/11/2026 18:52 đến 21/11/2026 00:56 UTC. Không phát sinh inference, BigQuery hoặc judge calls cho lần kiểm tra này.
