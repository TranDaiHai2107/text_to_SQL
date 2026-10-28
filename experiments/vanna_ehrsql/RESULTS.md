# Kết quả Vanna — chỉ đánh giá test

Train: 5.124 ví dụ trong knowledge base; không chấm điểm train. Không sử dụng dev.
Model: `qwen/qwen3.8-27b` qua Groq. Primary cố định: `vanna`.

Đã hoàn tất 70/1.167 câu test.

Trạng thái: **PARTIAL — không phải kết quả cuối và chưa được so với full paper.**

- `vanna`: RS0=84.2857, RS5=48.5714, RS10=12.8571, RSN=-415.7143; EX=81.8182; VSR=70.0000.
- `vanna_gef`: RS0=84.2857, RS5=62.8571, RS10=41.4286, RSN=-215.7143; EX=81.8182; VSR=68.5714.

RSN dùng N của số câu đã chấm; khi PARTIAL, không đối chiếu trực tiếp RSN với paper.
Chi tiết: `runs/vanna_qwen_20261027_v1_test/evaluation.json`.

## API/quota

Daily/account quota exhausted; checkpoints retained. Error code: 429 - {'error': {'message': 'Rate limit reached for model `qwen/qwen3.8-27b` in organization `org_01knkgwpr8eg8vjh320a0mvsfb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198210, Requested 2900. Please try again in 7m59.52s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

Checkpoint và API cache được giữ; không tự đổi model hoặc padding các câu chưa chạy thành null.
