# Bộ câu hỏi phản biện: Ours so với OmniSQL (GPT-4o-mini) trên BIRD dev

Ngày: 2026-11-21. Đây là các câu hỏi một người phản biện có thể đặt ra. Mỗi câu có gợi ý trả lời, dựa trên số liệu đã chạy thật (xem `reports/Ours so với OmniSQL trên BIRD.md`). Những câu đánh dấu **⚠** là điểm yếu thật của đề tài: nên thừa nhận thẳng và nêu cách khắc phục, không nên né.

Số liệu chính:

| | Gre | Maj-8 | v9 đầy đủ |
|---|---|---|---|
| Baseline (paper) | 58,8 | 61,5 | — |
| Baseline (chạy lại) | 58,93 | 61,99 | — |
| Ours | 60,50 (p = 0,076) | 63,62 (held-out 63,37 vs 61,18, p = 0,012) | 65,06 (held-out 64,83, p = 0,0001) |

---

## A. Về hệ thống của paper (OmniSQL / baseline GPT-4o-mini)

**1. OmniSQL đóng góp gì, và tại sao em so với dòng GPT-4o-mini chứ không so với OmniSQL-7B/32B?**
Gợi ý:
- OmniSQL có hai đóng góp: bộ dữ liệu tổng hợp SynSQL-2.5M, và các mô hình Qwen2.5-Coder fine-tune trên đó.
- GPT-4o-mini trong Bảng 4 là mốc **không fine-tune**, chạy với cùng prompt.
- Đề tài của em không fine-tune, nên đối thủ công bằng là cùng mô hình, cùng prompt, chỉ khác phần hệ thống bao quanh. So với OmniSQL-7B sẽ là so "fine-tune vs không fine-tune", khác câu hỏi nghiên cứu.
- Em vẫn báo cáo các mô hình fine-tune để người đọc định vị kết quả: Majority 65,9–67,0 (OmniSQL-7B/14B/32B: 66,1 / 65,9 / 67,0).

**2. Prompt của baseline gồm những gì? Nó đã có truy hồi giá trị chưa?**
Gợi ý:
- Prompt gồm: DDL đầy đủ, chú thích `-- example: [...]` cho từng cột, evidence ghép trước câu hỏi, chỉ dẫn "suy nghĩ từng bước, trả đúng thông tin được hỏi", và định dạng khối `sql`.
- Phần example **đã chứa** các giá trị khớp với chữ trong câu hỏi. Nghĩa là baseline đã có một lớp truy hồi giá trị đơn giản. Vì vậy phần cải thiện của em không phải "thêm thứ baseline chưa có", mà là nêu giá trị rõ hơn (bảng.cột = 'giá trị').

**3. Paper không công bố code gọi API GPT. Làm sao em chắc chắn tái lập đúng baseline?**
Gợi ý:
- Prompt `input_seq` lấy nguyên văn từ file tác giả phát hành và đã kiểm tra hash.
- Regex trích SQL, `max_tokens = 2048` và hàm `major_voting()` lấy từ code của tác giả.
- Bộ chấm là `evaluate_bird.py` gốc, không sửa.
- Bản chạy lại lệch +0,1 (Gre) và +0,5 (Maj) so với paper. Mức lệch này nằm trong nhiễu đo được:
  - chỉ đổi thứ tự 8 mẫu, Maj đã dao động 61,47–62,58;
  - độ lệch chuẩn bootstrap khoảng 0,4.
- Chi tiết ở `benchmarks/omnisql/GPT4O_MINI_CODE_FIDELITY.md`.

**4. Tại sao baseline Majority của em (61,99) cao hơn paper (61,5)? Em có vô tình làm baseline mạnh lên không?**
Gợi ý:
- Mức chênh 0,5 nhỏ hơn biên độ dao động khi chỉ đổi thứ tự mẫu, vì hàm vote của tác giả gặp hòa thì chọn nhóm xuất hiện trước.
- Ngoài ra API của OpenAI không tất định.
- Baseline cao hơn paper thì so sánh **khó hơn** cho Ours, không dễ hơn.

**5. Majority voting của paper xử lý thế nào khi cả 8 câu đều lỗi?**
Gợi ý: chọn ngẫu nhiên một câu. Các câu lỗi không tham gia bỏ phiếu. Phiếu được gom theo tập kết quả (frozenset), không phân biệt thứ tự dòng.

**6. Em dùng BIRD dev phiên bản nào, cấu hình chấm điểm ra sao? Timeout có ảnh hưởng kết quả không?**
Gợi ý:
- Phiên bản dev_20240627, đúng bản paper dùng.
- Chấm với `num_cpus = 4`, `timeout = 60` giây, áp dụng giống nhau cho mọi hệ thống. Lý do chọn ghi ở `benchmarks/omnisql/AUDIT.md`.
- Timeout quá ngắn sẽ đánh sai các câu gold chạy chậm. Em đã đo thời gian chạy của gold để chọn mức 60 giây.

**7. EX có hạn chế gì? Có trường hợp SQL sai mà vẫn được tính đúng không?**
Gợi ý:
- Có. EX so tập kết quả, nên SQL sai logic vẫn có thể trùng kết quả trên dữ liệu hiện có (false positive). Ngược lại, SQL đúng nhưng khác quy ước của gold (thêm cột, khác cách làm tròn) bị tính sai.
- Đã có công trình đề xuất thay thế, ví dụ FLEX dùng LLM làm giám khảo.
- Em giữ EX vì đó là metric của paper. Cả hai hệ thống chịu cùng hạn chế, nên so sánh tương đối vẫn hợp lệ.

**8. Nhãn gold của BIRD có đáng tin không?**
Gợi ý:
- Không hoàn toàn. Jin et al. (PVLDB 2026) kiểm tra 100 câu dev và thấy 48 câu cần sửa. Arcwise và Wretblad et al. cũng ghi nhận nhiều lỗi nhãn.
- Trên tập tuning, 9% câu có cả 8/8 mẫu cùng ra một kết quả mà vẫn bị chấm sai. Một phần trong số đó nhiều khả năng do nhãn.
- Điều này đặt trần thực tế cho EX, và giải thích vì sao phần cải thiện ở câu khó bị giới hạn.

**9. GPT-4o-mini có thể đã thấy BIRD dev lúc huấn luyện không?**
Gợi ý:
- Có thể, vì BIRD công khai từ 2023. Nhưng ảnh hưởng này như nhau cho baseline và Ours, vì cùng snapshot `gpt-4o-mini-2024-07-18`.
- Phần chênh lệch giữa hai hệ thống không đến từ rò rỉ dữ liệu.
- Kết luận về giá trị tuyệt đối thì cần thận trọng.

**10. Vì sao không so với top leaderboard BIRD (CHASE-SQL, XiYan, …)?**
Gợi ý:
- Các hệ thống đó dùng mô hình lớn hơn (Gemini, GPT-4o), hàng chục ứng viên và selector được fine-tune, với chi phí lớn hơn nhiều lần.
- So với chúng sẽ trộn ảnh hưởng của mô hình với ảnh hưởng của phương pháp.
- Em kiểm soát biến mô hình bằng cách dùng cùng gpt-4o-mini, và chỉ đo đóng góp của phương pháp. Trong khóa luận có thể nêu chúng ở phần tổng quan.

---

## B. Về hệ thống của em (Ours)

**11. Mô tả ngắn luồng xử lý của Ours.**
Gợi ý:
1. Truy hồi tối đa 12 giá trị lưu trong database khớp với câu hỏi.
2. Lấy 3 ví dụ few-shot từ BIRD train bằng BM25.
3. Chèn cả hai vào prompt baseline, trước phần Instructions.
4. Sinh 1 câu greedy, 8 mẫu theo prompt baseline và 8 mẫu theo prompt "query plan".
5. Chạy cả 17 câu. Nếu câu greedy lỗi hoặc trả rỗng thì sửa 1 lần.
6. Bỏ phiếu theo tập kết quả.
7. Nếu không nhóm nào đạt đa số thì gọi selector, lấy 5 mẫu rồi bầu.

**12. Truy hồi giá trị hoạt động thế nào? Khác gì phần example của baseline?**
Gợi ý:
- Dựng chỉ mục ngược trên mọi giá trị văn bản của database, lưu cache.
- Đưa ra tối đa 12 giá trị khớp với chữ trong câu hỏi, dạng `bảng.cột = 'giá trị'`, đúng chính tả như khi lưu.
- Baseline chỉ chèn giá trị vào danh sách ví dụ của cột, lẫn với các ví dụ khác. Ours nêu rõ giá trị nằm ở cột nào.
- Lý do: lỗi lớn nhất của baseline là "đúng cấu trúc, sai giá trị" (236/630 câu sai).

**13. Few-shot lấy từ đâu? Có rò rỉ dev không?**
Gợi ý:
- Lấy từ BIRD **train** (69 database), không trùng 11 database của dev. Code tự kiểm tra điều kiện này.
- Gold SQL của dev không bao giờ vào prompt, chỉ dùng khi chấm.

**14. Dùng nội dung database trong prompt có phải là "gian lận" không?**
Gợi ý: không. Đề bài BIRD cho phép truy cập database. Baseline của paper cũng đưa giá trị khớp từ database vào prompt. Các hệ thống trên leaderboard BIRD đều làm truy hồi giá trị.

**15. Prompt "query plan" là gì? Tại sao dùng riêng thì kém (62,45) mà kết hợp lại tốt?**
Gợi ý:
- Prompt này thay Instructions bằng 6 bước: cột cần trả, evidence, bộ lọc, join, sắp xếp/giới hạn, tự kiểm tra danh sách SELECT.
- Dùng riêng thì không hơn. Nhưng nó **sai theo kiểu khác** prompt gốc, nên hai bộ 8 mẫu bổ sung cho nhau:
  - trên tuning, số câu có ít nhất một ứng viên đúng tăng từ 217 lên 227;
  - trên toàn dev, 8 + 8 mẫu chỉ bỏ phiếu đạt 64,80, so với 63,62 khi dùng 8 mẫu.
- Đây là đa dạng hóa bộ sinh, ý tưởng đã có trong các công trình như CHASE-SQL.

**16. "Bỏ phiếu theo tập" khác gì bỏ phiếu theo multiset, và tại sao chọn tập?**
Gợi ý:
- Bản trước (v8) gom theo multiset, nên hai câu chỉ khác nhau ở DISTINCT bị tách thành hai nhóm và phiếu bị chia nhỏ.
- Gom theo tập khớp với cách EX so kết quả, và cũng khớp với cách hàm vote của baseline gom (frozenset).
- Đây là sửa cho đúng định nghĩa, không phải mẹo để tăng điểm.

**17. Selector là gì, và tại sao chỉ gọi khi không có đa số?**
Gợi ý:
- Selector cho gpt-4o-mini xem tối đa 3 nhóm lớn nhất (SQL và vài dòng kết quả), suy luận từng bước, lấy 5 mẫu rồi bầu chọn.
- Trên tuning, nếu gọi cả khi đã có đa số thì selector sửa được bao nhiêu câu thì làm hỏng bấy nhiêu, gần như tung đồng xu. Vì vậy ngưỡng 0,5 được chọn trên tuning.
- Trên toàn dev, selector chỉ được gọi ở 161/1534 câu và góp khoảng +0,5 điểm.

**18. Sửa lỗi theo thực thi đóng góp bao nhiêu?**
Gợi ý:
- Với greedy, sửa lỗi là phần chính: nâng từ 58,80 lên 60,50, với 98 câu được dùng bản sửa.
- Trong v9, thêm greedy và bản sửa vào cuộc bỏ phiếu gần như không đổi gì (64,80 → 64,54).

**19. Cho bảng ablation: mỗi thành phần góp bao nhiêu?**
Gợi ý: đo trên toàn dev, từ cùng lần chạy v9:

| Cấu hình | EX |
|---|---|
| Baseline Maj-8 | 61,99 |
| Ours 8 mẫu, ngữ cảnh làm giàu | 63,62 (+1,6) |
| 8 mẫu query plan riêng | 62,45 |
| 8 + 8 mẫu, chỉ vote | 64,80 (+1,2) |
| + greedy và sửa lỗi | 64,54 |
| + selector (v9) | 65,06 (+0,5) |

**20. ⚠ Riêng truy hồi giá trị và riêng few-shot, mỗi phần góp bao nhiêu?**
Gợi ý:
- Thừa nhận: ablation từng phần của v8 trên tuning (có `v8_novalues`, `v8_nofewshot`) chỉ chênh vài câu, nằm trong nhiễu.
- Hiện mới khẳng định được **tác động gộp** của hai thành phần này (+1,6 ở 8 mẫu, p = 0,012 trên held-out).
- Muốn tách bạch thì cần tập lớn hơn hoặc chạy lặp nhiều lần.

**21. Tại sao chọn BM25 mà không dùng embedding để lấy few-shot?**
Gợi ý:
- BM25 tất định, rẻ, không cần gọi thêm API, và dễ tái lập.
- Với BIRD, câu hỏi tương tự thường trùng từ khóa về phép toán (tỷ lệ, phần trăm, đếm), nên BM25 đủ dùng.
- Embedding có thể tốt hơn nhưng chưa thử. Đây là hướng mở.

**22. Ngoài câu greedy bị lỗi, hệ thống có cơ chế an toàn nào khi mọi ứng viên đều lỗi không?**
Gợi ý: có.
- Bước vote ưu tiên các câu trả về giá trị. Nếu không có câu nào như vậy thì dùng mọi câu chạy được.
- Nếu không câu nào chạy được thì trả câu greedy với trạng thái `unresolved`.
- Mọi bước đều ghi trace để phân tích lỗi.

---

## C. Điểm cải thiện và lý do áp dụng

**23. Điểm cải thiện chính của đề tài là gì, nói trong một câu?**
Gợi ý: không fine-tune, cùng gpt-4o-mini và cùng 8 mẫu, Ours nâng EX từ 61,2 lên 63,4 trên held-out (p = 0,012). Cấu hình đầy đủ đạt 64,8 trên held-out (p = 0,0001) và 65,06 trên toàn dev, vượt GPT-4o trong cùng bảng của paper (64,0 Maj, tính trên toàn dev).

**24. Mỗi cải tiến xuất phát từ phân tích lỗi nào?**
Gợi ý: baseline sai 630 câu.

| Nhóm lỗi | Số câu | Cải tiến nhắm tới |
|---|---|---|
| Đúng cấu trúc, sai giá trị | 236 | Truy hồi giá trị, few-shot |
| Sai số cột | 145 | Bước 1 và bước 6 của prompt query plan |
| Sai số dòng | 104 | Bỏ phiếu theo tập (gộp biến thể DISTINCT) |
| Lỗi thực thi / trả rỗng | 74 / 68 | Sửa lỗi theo thực thi |
| Phiếu phân tán | — | Selector có điều kiện |

**25. Cải thiện tập trung ở đâu?**
Gợi ý:
- Ở câu simple: Maj từ 67,35 lên 70,05 (p = 0,005); v9 đạt 71,24 (p = 0,0002).
- Đây đúng là nhóm lỗi sai giá trị và sai cột mà các cải tiến nhắm tới.

**26. ⚠ Tại sao câu moderate và challenging không cải thiện có ý nghĩa?**
Gợi ý:
- Ở 8 mẫu, Ours bằng đúng baseline ở cả hai nhóm (54,96 và 50,34). v9 hơn +2,2 (p = 0,27) và +0,7 (p = 1,0).
- Lý do khả dĩ:
  - câu khó sai chủ yếu ở logic nhiều bước, không phải ở giá trị;
  - nhóm challenging chỉ có 145 câu, nên khó đạt ý nghĩa thống kê;
  - nhãn ở nhóm câu khó nhiễu nhiều hơn.
- Hướng khắc phục là tách câu hỏi thành các bước (decomposition), hoặc dùng mô hình mạnh hơn cho bước lập kế hoạch.

**27. Tại sao ngữ cảnh tốt hơn lại giúp tăng điểm vote, mà không chỉ tăng độ chính xác của từng mẫu?**
Gợi ý: vote chỉ đúng khi đa số mẫu đúng. Ngữ cảnh có giá trị đúng chính tả giúp nhiều mẫu cùng hội tụ về một đáp án đúng, nên tăng xác suất phe đúng chiếm đa số.

**28. Tại sao chọn ngưỡng selector 0,5 và lấy 5 mẫu selector? Có overfit tuning không?**
Gợi ý:
- Cả hai được chọn trên tuning trước khi chạy full.
- Trên held-out, v9 vẫn hơn (64,83), nên lựa chọn khái quát được.
- Đóng góp của selector nhỏ (+0,5). Bỏ selector đi, hệ thống vẫn đạt 64,5–64,8.

**29. Các hướng em đã thử nhưng không giúp là gì? Vì sao không giúp?**
Gợi ý: tất cả đều đo trên tuning.

| Hướng thử | Kết quả | Lý do |
|---|---|---|
| Thêm mô tả cột/giá trị của BIRD vào DDL | Không tăng | Prompt dài hơn, nhiễu hơn |
| Selector dạng listwise/pairwise/tự nhất quán, gọi cả khi đã có đa số | Như tung đồng xu | gpt-4o-mini không phân biệt tốt hơn vote |
| Đánh trọng số phiếu theo bộ sinh | Không tăng | — |
| Sửa mọi mẫu lỗi/rỗng trước vote | Vote 194 → 194 (baseline 196 → 196) | Mẫu lỗi vốn đã bị loại; bản sửa thường rơi vào đúng phe thắng |
| Quy tắc căn cột | Vote 194 = 194 | Gold BIRD không nhất quán về cột thừa |

- Báo cáo cả kết quả âm giúp tránh nghi ngờ "chỉ chọn kết quả đẹp".

**30. Vì sao sửa lỗi nâng độ chính xác từng mẫu mà không tăng điểm vote?**
Gợi ý:
- Sửa lỗi giảm khoảng một nửa số mẫu lỗi hoặc rỗng (ví dụ 181 → 88) và tăng độ chính xác từng mẫu khoảng 1,5 điểm.
- Nhưng mẫu lỗi vốn không được bỏ phiếu, và bản sửa thường cho cùng kết quả với phe đa số. Vì vậy phe thắng không đổi.
- Áp cùng bước này cho baseline cũng không đổi gì (2 câu được, 2 câu mất).

**31. Đóng góp của em có mới không, hay chỉ ghép các kỹ thuật đã có?**
Gợi ý:
- Từng kỹ thuật đều đã có trong tài liệu: truy hồi giá trị, few-shot, self-consistency, sửa lỗi, selector.
- Đóng góp nằm ở ba điểm:
  1. Một hệ thống không fine-tune, được kiểm soát chặt (cùng mô hình, cùng prompt gốc, cùng bộ chấm), với so sánh **cùng ngân sách mẫu**.
  2. Phát hiện thực nghiệm: selector của mô hình nhỏ chỉ có ích khi phiếu phân tán. Đa dạng prompt có ích hơn thêm mô tả.
  3. Quy trình đánh giá có tập tuning/held-out đăng ký trước, kiểm định ghép cặp và báo cáo cả kết quả âm.

**32. Kết quả có ý nghĩa thực tế không, hay chỉ vài điểm phần trăm?**
Gợi ý:
- +2,2 điểm ở cùng ngân sách nghĩa là cứ 100 câu thì đúng thêm khoảng 2 câu, với chi phí gần như không đổi.
- +3,1 điểm ở cấu hình đầy đủ đưa gpt-4o-mini (rẻ) vượt GPT-4o (đắt hơn nhiều lần) trong cùng bảng.
- Với ứng dụng thật, đây là cải thiện có giá trị trên một đơn vị chi phí.

---

## D. Phương pháp thực nghiệm và tính công bằng

**33. ⚠ v9 dùng 17 ứng viên, baseline dùng 8. So vậy có công bằng không?**
Gợi ý:
- Đó là lý do em báo cáo **so sánh cùng ngân sách**: Ours@8 đạt 63,62 so với baseline 61,99, và trên held-out p = 0,012. Đây là kết quả chính.
- v9 chỉ là cấu hình đầy đủ, có ghi rõ chi phí gấp 2,7 lần.
- **Thiếu sót cần thừa nhận:** chưa chạy baseline với 16–17 mẫu. Thí nghiệm này tốn khoảng $2,4 và nên chạy để hoàn thiện so sánh cho v9.

**34. Tập tuning/held-out được chia thế nào? Ai đảm bảo em không chỉnh trên held-out?**
Gợi ý:
- Chia ngẫu nhiên với seed cố định 20261119: 300 câu tuning và 1234 câu held-out. File `splits.json` được tạo trước lần chạy v9.
- Mọi lựa chọn của v9 dựa trên tuning: prompt query plan, ngưỡng selector, số mẫu selector, bỏ phiếu theo tập.

**35. ⚠ Trước v9 đã có v6, v8 chạy trên toàn dev. Như vậy held-out đã bị "nhìn" chưa?**
Gợi ý:
- Thừa nhận: v6 và v8 đã được chạy và chấm trên toàn bộ 1534 câu. Vì vậy quá trình phát triển qua nhiều phiên bản vẫn có rủi ro chọn thiết kế thích nghi theo dev.
- Biện pháp đã áp dụng: từ khi có `splits.json`, các thay đổi của v9 chỉ chọn trên tuning, và chạy full đúng một lần.
- Phạm vi đề tài chỉ là BIRD dev, và tập test của BIRD bị ẩn. Vì vậy không có tập BIRD nào hoàn toàn sạch để kiểm tra lại. BIRD mini-dev cũng không dùng được, vì đó là tập con của dev.
- Cách trình bày: nêu rõ đây là giới hạn. Nhấn mạnh rằng so sánh cùng 8 mẫu dùng giao thức cố định của paper, không có tham số nào để chỉnh theo held-out, và cải thiện vẫn lặp lại qua nhiều lần lấy mẫu (xem câu 39).

**36. ⚠ Trên tuning, Ours@8 (64,67) còn thấp hơn baseline (65,33). Vì sao vẫn tin Ours tốt hơn?**
Gợi ý:
- Tuning chỉ có 300 câu. Độ nhiễu khi lấy mẫu lại lớn: hai lần lấy 8 mẫu của Ours cho 194 và 190 câu, chênh khoảng 1,3 điểm.
- Held-out có 1234 câu, gấp 4 lần, và là tập được đăng ký trước để kết luận. Trên đó Ours@8 hơn 2,2 điểm (p = 0,012).
- Cũng chính vì tuning nhỏ nên em chỉ dùng nó để so các biến thể với nhau, không dùng để kết luận Ours hơn baseline.

**37. Tại sao dùng McNemar, không dùng t-test hay so trung bình?**
Gợi ý: hai hệ thống được chấm trên cùng từng câu, và kết quả là nhị phân (đúng/sai). McNemar chính xác chỉ xét các câu bất đồng, đúng với dữ liệu ghép cặp nhị phân.

**38. Em đưa ra nhiều p-value (toàn dev, held-out, ba mức khó). Có cần hiệu chỉnh so sánh bội không?**
Gợi ý:
- Kiểm định chính được xác định trước là held-out. Các nhóm theo độ khó là phân tích khám phá.
- Kể cả hiệu chỉnh Bonferroni cho 3 kiểm định (ngưỡng 0,0167), Ours@8 (p = 0,012) và v9 (p = 0,0001) vẫn đạt.

**39. ⚠ Mỗi cấu hình chỉ chạy một lần. McNemar có tính đến nhiễu giữa các lần chạy không?**
Gợi ý:
- Không hẳn. McNemar xét nhiễu theo câu hỏi, không xét nhiễu do lấy mẫu của mô hình.
- Bổ sung đã có: đổi thứ tự mẫu thì baseline dao động 61,47–62,58, và bootstrap cho độ lệch chuẩn khoảng 0,4. Mức chênh 2,2 điểm lớn hơn khoảng 5 lần độ lệch chuẩn đó.
- Muốn chặt hơn thì chạy lặp 3 lần mỗi hệ thống. Chi phí khoảng $7 cho baseline Maj và $13–20 cho v9.

**40. Cột Ours Gre và Ours Maj được tính lại từ lần chạy v9. Như vậy có hợp lệ không?**
Gợi ý:
- Hợp lệ. Ours Gre là ứng viên `g` (cộng bản sửa `gr`). Ours Maj là vote trên `s1`–`s8`, đúng giao thức Maj-8 của paper.
- Bộ chấm cục bộ khớp 998/998 câu với bộ chấm gốc.
- Trong khóa luận có ghi rõ đây là "cấu hình con được tính từ cùng một lần chạy".

**41. Kết quả có tái lập được không, khi API của OpenAI không tất định?**
Gợi ý:
- Snapshot mô hình được cố định.
- Lưu đầy đủ prediction, trace và mọi ứng viên SQL, nên có thể chấm lại đúng từng con số mà không cần gọi API.
- Có lệnh chạy lại trong README và script thí nghiệm trong `benchmarks/omnisql/experiments/`.
- Chạy lại API sẽ lệch khoảng ±0,4 điểm, như đã đo.

**42. Gold SQL có bao giờ lọt vào prompt, kể cả gián tiếp qua selector hay bước sửa lỗi?**
Gợi ý:
- Không. Selector chỉ thấy SQL ứng viên và kết quả của chúng. Bước sửa lỗi chỉ thấy lỗi của SQLite, hoặc thông báo "kết quả rỗng".
- Gold chỉ được dùng trong bộ chấm.
- Có test đơn vị trong `tests/test_bird_ours.py`.

---

## E. Chi phí, giới hạn và khả năng mở rộng

**43. Chi phí và độ trễ của Ours so với baseline?**
Gợi ý: tính trên toàn bộ 1534 câu.

| | Baseline Gre | Baseline Maj | Ours v9 |
|---|---|---|---|
| Chi phí | $0,71 | $2,41 | $6,46 |
| Request API / câu | 1 | 1 | 3,2 |
| Thời gian / câu | — | — | 11,8 s |

- Ours@8 có chi phí xấp xỉ baseline Maj, vì chỉ thêm token cho giá trị và few-shot.

**44. Nếu chỉ được chọn một cấu hình để triển khai, em chọn gì?**
Gợi ý:
- Ours@8 nếu ưu tiên chi phí: cùng ngân sách với baseline mà hơn 2,2 điểm.
- v9 nếu ưu tiên độ chính xác và chấp nhận chi phí gấp 2,7 lần.
- Greedy kèm sửa lỗi (60,50) nếu cần độ trễ thấp.

**45. ⚠ Ours vẫn thua các mô hình fine-tune (OmniSQL 65,9–67,0 Maj). Vậy hướng không fine-tune có ý nghĩa gì?**
Gợi ý:
- Mô hình fine-tune cần GPU và dữ liệu huấn luyện, và phải tự vận hành.
- Ours chỉ cần API và chạy được với bất kỳ mô hình nào. Các thành phần độc lập với mô hình, nên có thể áp lên chính OmniSQL-7B.
- v9 (65,06) đã tiệm cận mức của mô hình fine-tune.

**46. Phương pháp có áp dụng được cho mô hình khác, hay database khác không?**
Gợi ý:
- Về thiết kế thì có: các thành phần không phụ thuộc mô hình.
- Nhưng chưa kiểm chứng trên mô hình khác hay benchmark khác. Đề tài chỉ đánh giá trên BIRD dev. Đây là giới hạn cần nêu, và là hướng phát triển: thử với một mô hình mở (ví dụ Qwen2.5-Coder-7B).

**47. ⚠ Tại sao không thử tăng số mẫu lên 16 hay 32 cho cả hai hệ thống?**
Gợi ý:
- Tăng số mẫu thì baseline cũng tăng, và không trả lời được câu hỏi "phương pháp có tốt hơn không".
- Câu hỏi đúng là: ở cùng số mẫu N, Ours có hơn không. Đã có câu trả lời ở N = 8.
- Một đường cong theo N = 1, 4, 8, 16 cho cả hai hệ thống sẽ chặt chẽ hơn. Đây là việc nên làm nếu còn ngân sách.

**48. Trong 9% câu "cả 8 mẫu cùng sai một kiểu", bao nhiêu là lỗi nhãn, bao nhiêu là lỗi mô hình?**
Gợi ý:
- Chưa kiểm tra thủ công từng câu.
- Có thể lấy mẫu khoảng 30 câu để gán nhãn tay (lỗi nhãn / lỗi mô hình / mơ hồ), theo cách của Jin et al. 2026.
- Việc này giúp ước lượng trần EX thực tế mà không cần tốn API.

---

## F. Liên hệ với toàn bộ khóa luận

**49. BIRD là tiếng Anh, cơ sở dữ liệu phổ thông. Thí nghiệm này liên quan gì đến hệ thống hỏi đáp của em (tiếng Việt, dữ liệu y tế)?**
Gợi ý:
- BIRD là benchmark công khai và có baseline đã công bố. Nó dùng để chứng minh lõi sinh SQL của em tốt hơn một cách khách quan, độc lập với miền y tế.
- Luồng đầy đủ là: tiếng Việt → tiếng Anh → SQL → kết quả → câu trả lời tiếng Việt. Các khâu dịch và diễn đạt kết quả được đánh giá riêng bằng các metric không cần ground truth, như COMETKiwi, MetricX-QE, kiểm tra NLI hai chiều và G-Eval. Xem `reports/Metric không cần ground truth cho luồng Việt Anh SQL.md`.

**50. Nếu dịch tiếng Việt sang tiếng Anh sai, lỗi lan sang SQL thế nào? Em đo được không?**
Gợi ý:
- Có thể đo ở hai mức:
  1. Chất lượng bản dịch không cần tham chiếu (COMETKiwi / MetricX-QE).
  2. Độ ổn định của SQL: so kết quả SQL sinh từ câu tiếng Anh gốc với kết quả sinh từ bản dịch ngược Anh → Việt → Anh. Nếu kết quả khác nhau thì lỗi do dịch.
- Có thể làm trên chính BIRD bằng cách dịch câu hỏi sang tiếng Việt, rồi so EX giữa đầu vào tiếng Anh và tiếng Việt.

---

## Ba điểm yếu nên chủ động nói trước khi bị hỏi

1. **Held-out không hoàn toàn "sạch"**, vì v6 và v8 đã chạy và chấm trên toàn dev trước v9. Đây là giới hạn được thừa nhận. Lập luận đỡ: so sánh cùng 8 mẫu dùng giao thức cố định, và cải thiện lặp lại qua các lần lấy mẫu.
2. **Chưa có baseline ở 16–17 mẫu** để so trực tiếp với v9. Chi phí khoảng $2,4, nên chạy.
3. **Câu moderate và challenging chưa cải thiện**, và chưa tách được đóng góp riêng của truy hồi giá trị so với few-shot.
