# Nguồn Vanna và lựa chọn triển khai

Kiểm tra ngày 26/10/2026.

- Package chính thức: [Vanna 2.0.2 trên PyPI](https://pypi.org/project/vanna/2.0.2/).
- Repo chính thức: [vanna-ai/vanna](https://github.com/vanna-ai/vanna). Repo đang được GitHub hiển thị là archived, nên cố định source artifact thay vì phụ thuộc main thay đổi.
- [Tài liệu SQLite + Chroma + LLM tùy chọn](https://ask.vanna.ai/docs/sqlite-other-llm-chromadb/).
- [Tài liệu lớp base legacy](https://legacy.vanna.ai/docs/base/).
- [Migration 0.x sang 2.0](https://vanna.ai/docs/migration): phân biệt luồng SQL/RAG legacy và agent/UI 2.0.
- Paper tham chiếu: [ProbGate at EHRSQL 2024](https://aclanthology.org/2024.clinicalnlp-1.65/).

## Artifact cố định

- `vanna-2.0.2-py3-none-any.whl`
- URL: https://files.pythonhosted.org/packages/bf/80/29ac542e8efe1d93fc99b25c870794673b22aeeb404060fd190e92aaf359/vanna-2.0.2-py3-none-any.whl
- SHA256: `d54f039572b0bcc520859ba99b7a587bdf96eebafc0c77c28fe44c0962550553`
- License của framework: MIT, đi kèm distribution trong `.vendor`.
- Phiên bản lấy từ metadata distribution `importlib.metadata.version('vanna')`. Không dùng `vanna.__version__`, vì artifact này khai báo nội bộ `0.1.0` không trùng phiên bản distribution.

## Phần giữ nguyên và phần cấu hình

Giữ source framework không chỉnh sửa: native similarity search, SQL prompt assembly, extraction, `generate_sql`, format/ID tài liệu Chroma. Adapter triển khai các abstract message/submit methods để dùng transport API có accounting sẵn. Chỉ thêm output contract SQL/null để phù hợp benchmark; tắt data introspection, auto-training, multi-turn UI. Dùng embedding đã cache trong dự án và nạp train examples/DDL theo đúng định dạng native.

Đây là **Vanna legacy RAG được cấu hình cho EHRSQL, nằm trong distribution 2.0.2**. Không tuyên bố đã dựng toàn bộ agent Vanna 2.0 mới nhất hoặc tái hiện một paper Vanna có điểm EHRSQL công bố. Điểm của đối chứng này sẽ do thí nghiệm mới đo.

Muốn so phương pháp công bằng: cùng backbone LLM với hệ thống đề xuất, chỉ dùng dữ liệu train cho ví dụ, chọn tham số trên dev, cố định trước test, báo token/calls và mọi khác biệt cấu hình. Chưa chọn model và chưa có kết quả để kết luận bên nào tốt hơn.
