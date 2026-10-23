# Model gốc — ghi chú, không thay model hoặc chạy API

Rà soát ngày 23/10/2026: container replay không khởi tạo model client nào. Mục dưới mô tả model tạo cache gốc; không có nghĩa weights/checkpoint đã được tải về.

## SQL generator GPT

- Paper: gpt-3.5-turbo fine-tuned trên câu hỏi trả lời được của EHRSQL.
- Notebook fine-tuning ghi base model `gpt-3.5-turbo-0125`.
- Notebook inference ghi một fine-tuned model ID thuộc tài khoản tác giả. ID này không làm model/checkpoint đó truy cập được bằng API key của người dùng.
- Inference source: temperature 0.0, logprobs=True, top_logprobs=5. Không có model Claude/Groq hoặc model GPT đời mới thay thế trong gói.
- Cache raw test công khai: `upstream/src/log_probability_final_test.json`, 1.167 ID; chứa SQL và token logprobs. Đây là đầu ra tác giả, không phải một model đã tải về.
- `upstream/src/chatgpt_sql_finetuning.ipynb` có nhiều system prompt; inference cũng gán đè system prompt nhiều lần. Mọi cell gốc được giữ nguyên; không chọn một prompt mới rồi gọi đó là prompt chính xác của paper.

## SQL generator T5

- Table 1 ghi `T5-small` và `T5-Large-text2sql-spider`.
- Source tham chiếu `gaussalgo/T5-LM-Large-text2sql-spider` cho large.
- Source small thực tế tham chiếu `google/flan-t5-small`, khác cách ghi tên T5-small trong paper. Chưa xác nhận được row nào dùng đúng checkpoint nào chỉ từ code công khai.
- Fine-tuned checkpoint `.pth.tar` được source tham chiếu bằng đường dẫn local nhưng không nằm trong repository. Model foundation trên Hugging Face không thay được checkpoint đã fine-tune EHRSQL.

## Answerability classifier

- Paper có Classifier(T5) và Classifier(gpt-3.5-turbo).
- Script T5 classifier tham chiếu `google/flan-t5-small` với `T5ForSequenceClassification(..., num_labels=1)`.
- Chưa có checkpoint classifier hoặc predictions dev đi kèm.
- Chưa xác định được implementation/prompt/checkpoint riêng đầy đủ của GPT classifier trong source công bố. Gói không tự tạo prompt mới để lấp phần này.

## Khi thực hiện bước chạy sau

Tách hai loại kết quả:

1. Replay các output test công khai: không cần truy cập model gốc, chỉ hậu xử lý và chấm.
2. Huấn luyện/inference lại: cần model/checkpoint hoặc job mới, khóa môi trường và ghi rõ khác biệt với run tác giả.

Đổi model vì model gốc không truy cập được là một thí nghiệm mới; không còn là tái hiện chính xác model gốc. Hiện chưa có API key hoặc model mới được cấu hình trong thư mục này.

## Model của ứng dụng chính, không phải baseline paper

- `rag_engine.py` hiện mặc định dùng `qwen/qwen3.8-27b` qua **Groq**, không phải xAI Grok. `.env` không ghi đè model này. Đã kiểm tra endpoint liệt kê model của tài khoản ngày 23/10: có model này; không gọi API sinh nội dung. Có trong danh sách không chứng minh chất lượng/độ chính xác.
- SQL generation, self-correction, rewrite và diễn giải dùng cùng client/LLM của ứng dụng. Prompt SQL đang hướng tiếng Việt/PostgreSQL; diễn giải cũng yêu cầu tiếng Việt.
- Embedding hiện là `paraphrase-multilingual-MiniLM-L12-v2`. Metadata của cả bốn collection Chroma khớp tên model, dimension 384 và số record thực tế: ICD 3.115, schema 31, examples 101, examples_eval 73. Hash nguồn của schema/examples/examples_eval đều khớp.
- Không đổi model trong đợt rà soát. Chạy lại ứng dụng bằng Qwen không phải tái huấn luyện lại GPT fine-tuned của ProbGate. Chưa có đường đánh giá RAG của ứng dụng trên English/EHRSQL/SQLite trong adapter offline.
- Nguồn model Groq hiện hành: https://console.groq.com/docs/models. Qwen này được liệt kê ở nhóm preview; cần ghi đúng model ID/ngày chạy khi báo cáo.
