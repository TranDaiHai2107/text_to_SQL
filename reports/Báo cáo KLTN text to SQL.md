# Viết khóa luận Ours theo khung bài báo BIRD

Mười bài báo text-to-SQL có ảnh hưởng nhất giai đoạn 2023–2026 đều đi theo một khung chung. Khung đó gồm Giới thiệu kèm danh sách đóng góp, Nghiên cứu liên quan, Phương pháp, Thực nghiệm và Kết luận. Phần Phương pháp mở đầu bằng một hình tổng quan, rồi viết mỗi thành phần thành một tiểu mục. Phần Thực nghiệm đi theo thứ tự: thiết lập (dữ liệu, độ đo, baseline, chi tiết cài đặt), kết quả chính, ablation, phân tích chi phí, phân tích lỗi. Phụ lục chứa các prompt. Khung này khớp gần như một-một với bố cục 5 chương mà quy định khóa luận của UET, HCMUS và NEU yêu cầu. Vì vậy em có thể viết khóa luận như một bài báo dài bằng tiếng Việt. Nội dung đã đủ để viết. Cùng snapshot `gpt-4o-mini-2024-07-18`, cùng prompt và cùng bộ chấm điểm của OmniSQL, Ours đạt **63,62% EX với đúng 8 mẫu** như baseline (61,99% khi chạy lại; paper báo 61,5%). Trên 1.234 câu held-out đã tách trước, Ours đạt 63,37% so với 61,18% (**McNemar chính xác p = 0,012**). Cấu hình đầy đủ 17 ứng viên đạt **65,06%** (p = 0,0003), tốn 6,46 USD, gấp 2,7 lần baseline. Ba điểm làm khóa luận mạnh hơn mức chung của ngành: so sánh cùng ngân sách, kiểm định ghép cặp, và tập tuning/held-out đăng ký trước. Không bài nào trong mười bài tham chiếu báo cáo kiểm định ý nghĩa thống kê. Còn hai lỗ hổng phải lấp trước khi bảo vệ: baseline 17 ứng viên và lần lấy mẫu thứ hai, hiện đang được chấm. Tài liệu này để sẵn chỗ trống cho cả hai. Phần còn lại đi qua từng chương: dữ kiện cần viết, bảng số liệu, công thức, cách diễn đạt từng nhận định, cuối cùng là danh mục tài liệu tham khảo kiểu IEEE.

**Quy ước nguồn.** Số liệu về Ours và baseline chỉ lấy từ các tệp của dự án, đánh dấu bằng mã trong ngoặc nhọn:

| Mã | Tệp |
|---|---|
| {N1} | `reports/Ours so với OmniSQL trên BIRD.md` |
| {N2} | `reports/Câu hỏi phản biện Ours BIRD.md` |
| {N3} | `benchmarks/omnisql/README.md` |
| {N4} | `benchmarks/omnisql/GPT4O_MINI_CODE_FIDELITY.md` |
| {N5} | `benchmarks/omnisql/AUDIT.md` |
| {N6} | `benchmarks/omnisql/experiments/README.md` |
| {N7} | `src/ehrqa/bird/ours_v9.py`, `ours_v8.py`, `fewshot.py`, `values.py`, `database.py` |
| {N8} | `benchmarks/omnisql/experiments/draws_and_budget.py` |
| {N9} | `reports/Cải thiện Ours BIRD giữ 8 mẫu.md` |

Tài liệu bên ngoài dùng trích dẫn số kiểu IEEE [n], ứng với danh mục ở cuối. Mọi ô ghi **[CHỜ KẾT QUẢ: …]** là số đang được chấm, không được đoán. Mọi ô ghi **[CẦN BỔ SUNG: …]** là số chưa có trong các tệp nguồn nhưng tính được từ dữ liệu đã lưu, không cần gọi API.

---

## Mười bài báo 2023–2026 dùng chung một khung mà khóa luận có thể mượn nguyên

### Trình tự các mục gần như cố định giữa các venue

Các bài DIN-SQL [16], DAIL-SQL [17], MAC-SQL [18], CHESS [19], CHASE-SQL [20], MCS-SQL [21], RSL-SQL [22], XiYan-SQL [24], Alpha-SQL [25] và OmniSQL [14] đều theo trình tự: Abstract, Introduction (kết thúc bằng danh sách đóng góp), Related Work, Method, Experiments, Conclusion, References, Appendix. Mục Method luôn mở bằng một tiểu mục "Overview" có hình pipeline, rồi viết mỗi tác tử hoặc mô-đun thành một tiểu mục. Ví dụ, CHASE-SQL có 3.2 Value Retrieval, 3.3 Multi-path Candidate Generation, 3.4 Query Fixer, 3.5 Selection Agent [20]. MAC-SQL có Selector, Decomposer, Refiner [18]. Mục Experiments mở bằng phần thiết lập gồm dữ liệu, độ đo, baseline và chi tiết cài đặt. OmniSQL tách phần này thành sáu tiểu mục 6.1.1–6.1.6, trong đó có riêng "Inference Strategy" [14]. Sau đó lần lượt là Main Results, Ablation, các phân tích "Impact of X" hoặc "Study of X", và cuối cùng là chi phí và phân tích lỗi. MCS-SQL và RSL-SQL tách hẳn "Experimental Setup" và "Results and Analysis" thành hai mục cấp một [21], [22]. Đây là cách tách gọn nhất để bê sang Chương 4.

Có ba biến thể đáng học. Thứ nhất, DIN-SQL đặt một mục **phân tích lỗi trước phần phương pháp** ("3 Few-shot Error Analysis"), rồi thiết kế từng mô-đun để sửa một nhóm lỗi đã quan sát [16]. Ours có sẵn bảng 630 câu sai của baseline, nên lối viết này hợp nhất cho Chương 3. Thứ hai, chỉ DIN-SQL và MAC-SQL có mục **Limitations** riêng. MAC-SQL còn có Ethics Statement, Alpha-SQL có Impact Statement [16], [18], [25]. DAIL-SQL gộp hạn chế vào mục Discussion, OmniSQL không có mục hạn chế [17], [14]. Thứ ba, RSL-SQL có hẳn một mục "Case Study", trình bày một ví dụ được lợi và một ví dụ bị hại [22]. Cách này giúp người chấm thấy phương pháp có lúc làm hỏng câu đúng, không chỉ toàn sửa được.

Ký hiệu hình thức trong các bài này nhẹ. MAC-SQL định nghĩa bài toán là bộ ba X = (Q, S, K): câu hỏi, lược đồ và tri thức ngoài [18]. Alpha-SQL định nghĩa CSDL D = (T, C, R) và cây tìm kiếm Ψ = (V, E) [25]. DAIL-SQL viết bài toán là cực đại hóa P_M(s* | σ(q, D, Q′)) với |Q′| = k ví dụ [17]. CHASE-SQL viết luật chọn bằng tổng số lần thắng theo cặp [20], còn MCS-SQL định nghĩa độ tin cậy là tỷ lệ ứng viên có cùng kết quả thực thi, với ngưỡng T = 0,2 [21]. DIN-SQL, CHESS và OmniSQL không có định nghĩa hình thức [16], [19], [14]. Vì vậy một tiểu mục ký hiệu dài khoảng một trang, kèm 4–6 công thức, là đủ chuẩn.

### Quy ước báo cáo thực nghiệm và chi phí

Mức chi tiết cài đặt mà khóa luận nên theo là của OmniSQL. Bài này ghi phiên bản mô hình có ngày (GPT-4o-mini-2024-07-18), nêu greedy ở temperature 0, và majority với 8 ứng viên ở temperature 0,8, gom theo kết quả thực thi [14]. MCS-SQL ghi rõ temperature 1,0, n = 20, số prompt mỗi bước, k = 20 ví dụ và timeout 180 giây [21]. Ngược lại, MAC-SQL không ghi temperature, còn RSL-SQL không ghi phiên bản mô hình [18], [22]. Người phản biện sẽ chỉ ra những chỗ thiếu như vậy. Bảng kết quả BIRD chuẩn có các cột Method, backbone, Dev EX và Test EX, thường tách thêm theo simple, moderate, challenging [18], [19]. Alpha-SQL thêm cột "Zero-shot ✓/✗" để tách phương pháp không fine-tune khỏi phương pháp có fine-tune [25]. Khóa luận nên dùng đúng cột đó, vì Ours nằm ở nhóm không fine-tune.

Ablation có hai kiểu. Kiểu bỏ từng thành phần (leave-one-out) có cột Δ. Ví dụ, CHASE-SQL đầy đủ đạt 73,01; thay selector bằng self-consistency còn 68,84 (−4,17); bỏ query fixer còn 69,23 (−3,78) [20]. Kiểu cộng dần (add-one) như RSL-SQL đi từ 48,70 lên 67,21 [22], hay MCS-SQL đi từ 50,7 lên 63,4 [21]. Ablation của Ours dựng lại từ cùng một lần chạy theo kiểu cộng dần, nên trình bày theo mẫu của RSL-SQL và MCS-SQL. Về chi phí, RSL-SQL có bảng chuẩn mực: tổng token vào và ra cùng số USD cho cả BIRD dev. GPT-4o dùng 21,90 triệu token vào và 0,73 triệu token ra, tốn 62,06 USD, đạt 67,21 EX. MAC-SQL tốn 342,44 USD, E-SQL 182,56 USD [22]. CHESS báo "approximately 83% fewer LLM calls" [19]. DIN-SQL ghi khoảng 0,5 USD và 60 giây cho mỗi câu, ngay trong mục Limitations [16]. CHASE-SQL, MCS-SQL và Alpha-SQL không báo chi phí [20], [21], [25].

Phân tích lỗi trên BIRD gần như luôn phát hiện **một tỷ lệ lớn lỗi nằm ở nhãn**. Trong CHASE-SQL, 10,0% BIRD dev có "wrong golden query", 10,4% có ứng viên đúng nhưng không được chọn, và 6,7% không có ứng viên đúng nào [20]. MCS-SQL lấy 100 câu sai và quy khoảng 62% cho gold sai hoặc giới hạn của EX [21]. MAC-SQL ghi Gold Error 30% trên BIRD [18]. CHESS có hẳn một nhánh "Incorrect Golden SQL" trong cây phân loại lỗi [19]. Điểm đáng chú ý nhất cho khóa luận: **không bài nào trong mười bài báo kiểm định ý nghĩa, khoảng tin cậy, độ lệch chuẩn hay chạy nhiều seed**. Tất cả chỉ báo một con số đo một lần. Một số ablation còn có mức chênh nhỏ hơn độ phân giải của tập con 147 câu (một câu ≈ 0,68 điểm) [25], [19]. Báo cáo McNemar ghép cặp và phương sai giữa các lần lấy mẫu đã đặt khóa luận cao hơn chuẩn chung của lĩnh vực.

### Cách các bài báo diễn đạt nhận định

Nhận định mạnh thường có dạng "đạt state-of-the-art X% trên BIRD, vượt Y%" [20], [24]. Nhận định cẩn trọng gắn thêm phạm vi so sánh. CHESS viết "among the methods using open-source models" [19]. Alpha-SQL viết "using a 32B open-source LLM without fine-tuning" và "fine-tuning-free, plug-and-play" [25]. OmniSQL gọi các mô hình đóng là "a point of reference rather than a direct comparison" [14]. CHESS chia kết quả theo ngân sách tính toán cao và thấp, và nhận xét rằng các phương pháp chỉ dựa vào tăng lấy mẫu "become less effective" [19]. Chính các bài này cũng hay mâu thuẫn số liệu nội bộ. MCS-SQL đưa hai mức chênh SOTA khác nhau (+5,86 và 4,74). RSL-SQL ghi 87,5 trong bảng nhưng 87,7 trong văn bản. DAIL-SQL ghi 82,4 và 83,5 cho cùng một đại lượng [21], [22], [17]. MAC-SQL viết "more frequent in BIRD (2%) than in Spider (8%)", ngược với chính số của mình [18]. Bài học cho khóa luận: đối chiếu từng con số giữa bảng và văn bản trước khi nộp (xem danh sách kiểm tra ở Phần C).

### Quy định khóa luận Việt Nam khớp với khung bài báo

Quy định của ĐHQGHN – Trường ĐH Công nghệ yêu cầu phần Mở đầu nêu "tính cần thiết của đề tài, ý nghĩa khoa học và thực tiễn…, đối tượng và phương pháp nghiên cứu", và phần Kết luận nêu "những kết quả chính và đánh giá kết quả đạt được". Quy định này cũng yêu cầu: tóm tắt khoảng 360 từ kèm tối đa 4 cụm từ khóa; chương, mục đánh số Ả Rập; chú thích bảng đặt trên bảng, chú thích hình đặt dưới hình; font 13pt, giãn dòng 1,3; được phép dùng LaTeX; tài liệu tham khảo đánh số [n], xếp theo ABC và nhóm theo ngôn ngữ ([UET](https://uet.edu.vn/wp-content/uploads/2017/07/Quy-%C4%91i%CC%A3nh-v%C3%AA%CC%80-tri%CC%80nh-ba%CC%80y-kho%CC%81a-lu%C3%A2%CC%A3n-t%C3%B4%CC%81t-nghi%C3%AA%CC%A3pCLC.pdf)). Khoa CNTT ĐH KHTN TP.HCM yêu cầu bố cục Mở đầu, Tổng quan, Nghiên cứu thực nghiệm hoặc lý thuyết, Trình bày và đánh giá kết quả, Kết luận ("ngắn gọn, không có lời bàn"), Hướng phát triển, dài 50–100 trang ([HCMUS](https://www.ctda.hcmus.edu.vn/wp-content/uploads/2015/12/CLC_Mau-quy-dinh-trinh-bay-KLTN.pdf)). Khoa CNTT ĐH Kinh tế Quốc dân yêu cầu tối thiểu 50 trang. Phân bổ gợi ý là Chương 1 Tổng quan 5–10 trang, Chương 2 Cơ sở lý thuyết 10–15, Chương 3 Phương pháp 15–20, Chương 4 Kết quả và thảo luận 10–15. Khoa này bắt buộc **trích dẫn IEEE**, nộp kết quả Turnitin, và yêu cầu mọi hình, bảng đều được nhắc đến trong văn bản ([NEU FIT](https://fit.neu.edu.vn/post/mot-so-quy-dinh-viet-bao-cao-khoa-luan)). Mẫu LaTeX cộng đồng của UIT đặt "Tóm tắt khóa luận" ở trang 1, kết thúc bằng một đoạn giới thiệu cấu trúc các chương ([Overleaf UIT](https://www.overleaf.com/latex/templates/hcmuit-thesistemplate/ghqpckjqdxfz.pdf)). Các quy định này phần lớn ban hành khoảng năm 2017. Em cần kiểm tra bản hiện hành của khoa mình, nhất là thứ tự nhóm tài liệu tham khảo: IEEE xếp theo thứ tự trích dẫn, UET xếp theo ABC.

Bảng dưới ánh xạ khung bài báo sang khung khóa luận được đề xuất. Cột cuối cho biết bài nào là mẫu tốt nhất để bắt chước cho từng mục.

| Khóa luận | Tương ứng trong bài báo | Mẫu nên bắt chước |
|---|---|---|
| Tóm tắt (+ Abstract) | Abstract | Alpha-SQL (nêu phạm vi "không fine-tune" ngay câu đầu) [25] |
| Chương 1 Giới thiệu | Introduction + danh sách đóng góp | CHESS, Alpha-SQL [19], [25] |
| Chương 2 Cơ sở lý thuyết và nghiên cứu liên quan | Preliminaries + Related Work | MAC-SQL §2 (định nghĩa bài toán), DAIL-SQL §2 [18], [17] |
| Chương 3 Phương pháp đề xuất | Few-shot Error Analysis + Method | DIN-SQL §3–4, CHASE-SQL §3 [16], [20] |
| Chương 4 Thực nghiệm và đánh giá | Experimental Setup + Results and Analysis + Case Study | MCS-SQL §4–5, RSL-SQL §IV–VI, OmniSQL §6.1 [21], [22], [14] |
| Chương 5 Thảo luận, hạn chế, hướng phát triển | Discussion + Limitations | DAIL-SQL §5, DIN-SQL §7 [17], [16] |
| Kết luận | Conclusion | Ngắn, không thêm số mới (theo HCMUS) |
| Phụ lục | Appendix: prompts, error examples | Alpha-SQL A.4 (prompt của baseline), CHESS F (lỗi) [25], [19] |

Phần đầu khóa luận theo thứ tự: Bìa, Phụ bìa, Lời cam đoan (có chữ ký), Lời cảm ơn, Tóm tắt và Abstract, Mục lục, Danh mục hình, Danh mục bảng, Danh mục từ viết tắt (EX, LLM, CoT, BM25, SC, VES…).

---

## Bộ nội dung từng chương: số liệu, công thức và câu chữ đã sẵn để viết

### Tóm tắt (bản nháp khoảng 330 từ)

> Chuyển câu hỏi ngôn ngữ tự nhiên thành truy vấn SQL (text-to-SQL) cho phép người dùng không chuyên khai thác cơ sở dữ liệu quan hệ. Các hệ thống mạnh nhất trên bộ đánh giá BIRD hiện dựa vào mô hình lớn, bộ chọn được tinh chỉnh hoặc mô hình fine-tune chuyên biệt, nên tốn kém và khó so sánh công bằng. Khóa luận đề xuất [TÊN HỆ THỐNG], một hệ thống text-to-SQL dạng tác tử, không cần huấn luyện (training-free), dùng mô hình `gpt-4o-mini-2024-07-18` qua API. Hệ thống bổ sung vào prompt chuẩn của OmniSQL hai lớp ngữ cảnh: các giá trị lưu trong cơ sở dữ liệu khớp với câu hỏi, và ba ví dụ truy hồi bằng BM25 từ tập huấn luyện BIRD. Sau đó hệ thống sinh ứng viên từ hai kiểu prompt, sửa lỗi dựa trên phản hồi thực thi, bỏ phiếu theo tập kết quả, và chỉ gọi bộ chọn LLM khi không có đa số. Đánh giá trên BIRD dev (1.534 câu) dùng bộ chấm gốc của tác giả OmniSQL. Baseline GPT-4o-mini tái dựng đạt 58,93% (greedy) và 61,99% (bỏ phiếu 8 mẫu), sát số công bố 58,8% và 61,5%. Cùng 8 mẫu, hệ thống đề xuất đạt 63,62% EX. Trên 1.234 câu held-out được tách trước khi chạy, hệ thống đạt 63,37% so với 61,18% của baseline (kiểm định McNemar chính xác, p = 0,012). Cấu hình đầy đủ 17 ứng viên đạt 65,06% (p = 0,0003), cao hơn GPT-4o trong cùng bảng của OmniSQL (64,0%), với chi phí 6,46 USD cho toàn bộ dev, gấp 2,7 lần baseline. Cải thiện tập trung ở câu mức simple (67,35% lên 71,24%); với câu moderate và challenging, chưa có khác biệt có ý nghĩa. Khóa luận cũng báo cáo các hướng không hiệu quả: thêm mô tả cột, gọi bộ chọn vô điều kiện, sửa lỗi mọi mẫu. Ngoài ra, khóa luận phân tích ảnh hưởng của nhiễu nhãn trong BIRD đến trần EX. [CHỜ KẾT QUẢ: một câu về độ ổn định qua hai lần lấy mẫu và so sánh với baseline 17 ứng viên.]
>
> **Từ khóa:** text-to-SQL; mô hình ngôn ngữ lớn; tự nhất quán; BIRD.

Câu đầu của tóm tắt nêu ngay phạm vi "không cần huấn luyện, cùng gpt-4o-mini", theo cách Alpha-SQL viết abstract [25]. Mọi con số trong tóm tắt phải xuất hiện y hệt trong Chương 4.

### Chương 1. Giới thiệu: từ 23% đến 65% trên BIRD, và câu hỏi về ngân sách

**1.1 Bối cảnh.** Text-to-SQL ánh xạ câu hỏi tự nhiên thành SQL chạy được trên một CSDL cụ thể. Bài toán này đã đi qua ba thời kỳ, được tổng kết trong các survey [51]–[54]. Thời kỳ đầu là các mô hình mã hóa lược đồ như IRNet, RAT-SQL, PICARD, RESDSQL, Graphix-T5 [43]–[47]. Chúng thống trị Spider [2], nhưng trên BIRD, T5-3B chỉ đạt 23,34% dev EX [9]. Thời kỳ thứ hai là học trong ngữ cảnh với GPT-4. GPT-4 zero-shot đạt 46,35% [9]; DIN-SQL, DAIL-SQL, TA-SQL, MAC-SQL đưa con số lên 50,72–57,56% [9], [16]–[18], [30]. Thời kỳ thứ ba, 2024–2026, là tính toán lúc suy luận (test-time compute): sinh nhiều ứng viên, truy hồi giá trị, rồi chọn. Các hệ thống tiêu biểu là MCS-SQL 63,36%, CHESS 68,31%, OpenSearch-SQL 69,30%, CHASE-SQL 73,01% [9], [19]–[21], [28]. Song song là dòng fine-tune mô hình mở 7–32B bằng dữ liệu tổng hợp hoặc RL: OmniSQL-32B đạt 67,0% với bỏ phiếu 8 mẫu, Arctic-Text2SQL-R1-32B đạt 72,20% [14], [38]. Con người đạt 92,96% EX trên tập test [1]. Đầu bảng xếp hạng tháng 11/2026 đạt 83,40% test (AskData) [9]. BIRD được chọn vì sát với thực tế: 12.751 cặp câu hỏi–SQL, 95 CSDL tổng cộng 33,4 GB, 37 lĩnh vực, có giá trị bẩn và tri thức ngoài (evidence) [1].

**1.2 Bài toán.** Cho câu hỏi tiếng Anh q, evidence e và CSDL SQLite D, cần sinh truy vấn ŷ sao cho tập kết quả của ŷ trùng với tập kết quả của SQL vàng. Độ đo là execution accuracy (EX) trên BIRD dev, phiên bản `dev_20240627`, gồm 1.534 câu trên 11 CSDL {N3}. Ràng buộc của đề tài: không fine-tune; chỉ dùng một mô hình đóng giá rẻ (`gpt-4o-mini-2024-07-18`, 0,15 USD mỗi 1 triệu token vào và 0,60 USD mỗi 1 triệu token ra [57]); và so sánh với đúng baseline GPT-4o-mini mà OmniSQL công bố [14].

**1.3 Động lực.** Có bốn lý do, mỗi lý do đều có số liệu đi kèm. (i) Fine-tune tốn kém. OmniSQL cần tổng hợp SynSQL-2.5M (2.544.390 mẫu trên 16.583 CSDL) và huấn luyện mô hình 7–32B [14]. Ngay việc chạy lại trọng số OmniSQL cũng cần GPU khoảng 16 GB trở lên {N5}. (ii) Với cùng prompt, GPT-4o-mini chỉ đạt 58,8% greedy và 61,5% bỏ phiếu 8 mẫu [14], thấp hơn khoảng 5 điểm so với OmniSQL-7B (63,9/66,1) [14]. Vậy phần hệ thống bao quanh mô hình thu hẹp được bao nhiêu khoảng cách đó? (iii) Nhiều hệ thống trên bảng xếp hạng không so sánh được với nhau. Chúng dùng backbone mạnh hơn (GPT-4o, Gemini), selector được fine-tune (CHASE-SQL [20]), hoặc fine-tune chính GPT-4o (Distillery [29]). Không bài nào trong mười bài tham chiếu so sánh cùng ngân sách hay kiểm định ý nghĩa (xem phần đầu tài liệu). (iv) Phân tích lỗi của baseline greedy cho thấy lỗi tập trung vào những nhóm sửa được bằng ngữ cảnh. Trong 630 câu sai, 236 câu đúng cấu trúc nhưng sai giá trị, 145 câu sai số cột, 104 câu sai số dòng, 74 câu lỗi thực thi và 68 câu trả về rỗng {N1}, {N2}.

**1.4 Mục tiêu.** Mục tiêu tổng quát là xây dựng và đánh giá có kiểm soát một hệ thống text-to-SQL không fine-tune, nâng EX của gpt-4o-mini trên BIRD dev so với baseline công bố, ở cùng và ở lớn hơn ngân sách mẫu. Có bốn mục tiêu cụ thể. Một là tái lập baseline GPT-4o-mini của OmniSQL theo giao thức công bố, kiểm chứng bộ chấm. Hai là thiết kế các thành phần nhắm vào từng nhóm lỗi. Ba là đo đóng góp của từng thành phần, kèm kiểm định ghép cặp trên tập held-out đăng ký trước. Bốn là phân tích chi phí, phân tích lỗi, kết quả âm và ảnh hưởng của nhiễu nhãn.

**1.5 Câu hỏi nghiên cứu.** Viết thành bốn câu hỏi đánh số, mỗi câu có một mục kết quả tương ứng ở Chương 4:

| RQ | Câu hỏi | Được trả lời ở |
|---|---|---|
| RQ1 | Ở cùng ngân sách 8 mẫu như giao thức Maj của OmniSQL, việc làm giàu ngữ cảnh (giá trị lưu trữ + few-shot BM25) có nâng EX một cách có ý nghĩa thống kê không? | 4.3, 4.4 tầng 1, 4.5 |
| RQ2 | Khi nới ngân sách lên 17 ứng viên, đa dạng prompt, sửa lỗi theo thực thi và selector có điều kiện góp thêm bao nhiêu? Lợi thế có còn khi baseline được cùng 17 ứng viên không? | 4.4 tầng 3, 4.7 |
| RQ3 | Cải thiện phân bố thế nào theo độ khó và theo lớp lỗi? | 4.6, 4.9 |
| RQ4 | Kết luận có vững trước nhiễu lấy mẫu của API, lựa chọn thiết kế trên tập tuning và nhiễu nhãn của BIRD không? | 4.2, 4.5, 4.9, 5.2 |

**1.6 Đóng góp.** Theo mẫu CHESS và Alpha-SQL, viết thành 4 đóng góp có đo lường. Đóng góp thứ nhất là hệ thống Ours: không fine-tune, chỉ thêm bốn lớp quanh prompt gốc của OmniSQL (truy hồi giá trị bằng chỉ mục ngược, few-shot BM25 từ BIRD train, bộ sinh "query plan", bỏ phiếu theo tập kết hợp selector có cổng). Hệ thống đạt 63,62% EX ở 8 mẫu và 65,06% ở 17 ứng viên với gpt-4o-mini {N1}. Đóng góp thứ hai là quy trình đánh giá có kiểm soát. Quy trình gồm: tái lập bộ chấm OmniSQL đúng 6/6 con số của paper; dựng lại baseline GPT-4o-mini lệch +0,1 và +0,5 điểm so với paper; chia tuning/held-out 300/1.234 với seed cố định; so sánh cùng ngân sách; McNemar chính xác {N5}, {N1}. Đóng góp thứ ba là các phát hiện thực nghiệm trên gpt-4o-mini. Selector chưa tinh chỉnh chỉ có ích khi phiếu phân tán. Đa dạng prompt nâng độ phủ oracle, còn thêm mô tả cột thì không giúp. Sửa lỗi nâng độ chính xác từng mẫu nhưng không đổi kết quả bỏ phiếu {N2}, {N6}. Đóng góp thứ tư là toàn bộ dự đoán, trace, ứng viên và lệnh chạy được công bố, nên chấm lại được từng con số mà không cần gọi API {N1}, {N2}.

**1.7 Phạm vi.** Phạm vi đề tài: chỉ BIRD dev `dev_20240627`, tiếng Anh, SQLite, độ đo EX, một mô hình `gpt-4o-mini-2024-07-18`. Đề tài không fine-tune, không dùng tập test ẩn của BIRD (1.789 câu [1]), không thử mô hình khác. Nếu khóa luận còn có phần hỏi đáp tiếng Việt và dữ liệu y tế, nêu rõ rằng chương BIRD chỉ đánh giá lõi sinh SQL trên một benchmark công khai có baseline đã công bố. Các khâu dịch và diễn đạt kết quả được đánh giá riêng {N2, câu 49}.

**1.8 Bố cục.** Một đoạn giới thiệu nội dung các chương 2–5 và phụ lục, như mẫu UIT.

### Chương 2. Cơ sở lý thuyết và các nghiên cứu liên quan

#### 2.1 Định nghĩa bài toán text-to-SQL

Viết theo MAC-SQL §2.1 [18]. Một CSDL D gồm lược đồ S = (T, C, K): T là tập bảng, C là tập cột, K là tập khóa chính và khóa ngoại. Kèm theo là nội dung các bảng. Đầu vào gồm câu hỏi q và tri thức ngoài e (evidence của BIRD). Mô hình M sinh truy vấn y. Gọi exec(y, D) là kết quả thực thi: một danh sách bộ giá trị, hoặc ⊥ nếu lỗi hay quá thời gian. Với LLM sinh tự hồi quy, xác suất của y phân rã theo token:

$$P_M(y \mid q, e, S) = \prod_{t=1}^{|y|} P_M(y_t \mid y_{<t}, \sigma(q, e, S))$$

trong đó σ là hàm dựng prompt, theo cách viết của DAIL-SQL [17].

#### 2.2 Mô hình ngôn ngữ lớn, học trong ngữ cảnh và nhiệt độ lấy mẫu

GPT-3 (175 tỷ tham số) cho thấy LLM giải được tác vụ khi chỉ được cho mô tả và vài ví dụ trong prompt, không cập nhật gradient. Đây là định nghĩa gốc của học trong ngữ cảnh (in-context learning) và là cơ sở để gọi Ours là "training-free" [55]. GPT-4 là mô hình đa phương thức, đạt mức con người trên nhiều kỳ thi chuyên môn [56]. GPT-4o mini ra mắt ngày 18/7/2024. Theo số của nhà cung cấp: MMLU 82,0%, HumanEval 87,2%, cửa sổ ngữ cảnh 128K token, tối đa 16K token đầu ra, kiến thức đến tháng 10/2023, giá 0,15 và 0,60 USD mỗi 1 triệu token vào và ra [57]. OpenAI không công bố số tham số hay dữ liệu huấn luyện của mô hình này. Phân phối lấy mẫu với nhiệt độ T:

$$p_i = \frac{\exp(z_i / T)}{\sum_j \exp(z_j / T)}$$

T → 0 tiến về greedy, T = 1 giữ nguyên phân phối của mô hình, T > 1 làm phân phối phẳng hơn. Nucleus sampling của Holtzman et al. là tài liệu chuẩn về giải mã ngẫu nhiên [58]. Trên BIRD dev, CHASE-SQL đo được rằng tăng nhiệt độ làm ứng viên đa dạng hơn nhưng "compromise the quality". Ví dụ, self-consistency của bộ sinh divide-and-conquer giảm từ 66,43 (T = 0,5) xuống 64,41 (T = 1,8) [20]. Ours dùng T = 0,8 cho mẫu và T = 0 cho câu greedy, giống giao thức của OmniSQL [14], {N7}.

#### 2.3 Chuỗi suy luận (CoT), zero-shot CoT và CoT dạng kế hoạch truy vấn

CoT cho mô hình viết các bước trung gian trước đáp án. PaLM 540B dùng 8 ví dụ CoT đạt SOTA trên GSM8K [59]. Zero-shot CoT chỉ cần thêm "Let's think step by step": InstructGPT tăng từ 17,7% lên 78,7% trên MultiArith và từ 10,4% lên 40,7% trên GSM8K [60]. Prompt của OmniSQL yêu cầu suy nghĩ từng bước trước khi viết SQL, tức là zero-shot CoT [14], {N1}. Trong text-to-SQL, DIN-SQL tách bài toán thành các bước schema linking, phân loại và phân rã, sinh, rồi tự sửa [16]. CHASE-SQL đề xuất "Query Plan CoT", mô phỏng các bước của bộ máy CSDL: tìm bảng liên quan, thực hiện phép toán, trả cột. Với một ứng viên trên Gemini 1.5 Pro, phương pháp này đạt 63,62 so với baseline 57,75 [20]. Prompt "query plan" của Ours là một biến thể có cấu trúc thuộc dòng này (Chương 3).

#### 2.4 Chọn ví dụ few-shot bằng truy hồi và hàm BM25

Liu et al. cho thấy chọn ví dụ gần nghĩa với câu hỏi (kNN) tốt hơn chọn ngẫu nhiên: +41,9% trên ToTTo và +45,5% trên NQ [66]. DAIL-SQL hệ thống hóa ba khía cạnh: biểu diễn câu hỏi, chọn ví dụ và cách tổ chức ví dụ. Kết hợp self-consistency, DAIL-SQL đạt 86,6% EX trên Spider với GPT-4 [17]. Trên BIRD dev với GPT-4, few-shot là bước tăng lớn nhất trong ablation của MCS-SQL: từ 55,2 lên 60,0 (+4,8) [21]. Chọn ngẫu nhiên đạt 57,0, chọn theo độ tương đồng câu hỏi đạt 59,3, chọn theo câu hỏi đã che token lược đồ đạt 60,0 [21]. BM25 có dạng chuẩn [67]:

$$\text{score}(D, Q) = \sum_{q \in Q} \text{IDF}(q) \cdot \frac{f(q, D)\,(k_1 + 1)}{f(q, D) + k_1\left(1 - b + b \frac{|D|}{\text{avgdl}}\right)}$$

Trong đó IDF(q) = log((N − n(q) + 0,5)/(n(q) + 0,5)), với k₁ thường lấy trong khoảng 1,2–2,0 và b ≈ 0,75. Công thức này ghi từ kiến thức chuẩn và chưa được đối chiếu lại với §3 của [67]; cần kiểm tra trước khi nộp.

#### 2.5 Tự nhất quán, bỏ phiếu theo kết quả thực thi và tự nhất quán phổ quát

Self-consistency lấy m đường suy luận có đáp án a₁…a_m, rồi chọn đáp án được nhiều đường đồng ý nhất [61]:

$$\hat a = \arg\max_a \sum_{i=1}^{m} \mathbb{1}[a_i = a]$$

So với CoT greedy, phương pháp tăng 17,9% trên GSM8K, 11,0% trên SVAMP và 12,2% trên AQuA [61]. Với chương trình, phép "bằng nhau" được thay bằng **trùng kết quả thực thi**. Đó là MBR-exec: chọn chương trình p̂ = argmax_p Σ_{p′} 𝟙[exec(p) = exec(p′)] [63]. LEVER huấn luyện một bộ kiểm chứng dựa trên kết quả thực thi, nên không thuộc nhóm training-free [64]. Universal Self-Consistency (USC) cho chính LLM chọn đáp án nhất quán nhất, nên dùng được khi đáp án không so khớp chính xác được [62]. Trên BIRD dev, CHASE-SQL đo: một ứng viên đạt 63,01, self-consistency đạt 68,84, cận trên oracle đạt 82,79 [20]. Trong text-to-SQL, C3 dùng bỏ phiếu nhất quán theo kết quả thực thi với ChatGPT zero-shot, đạt 82,3% EX trên Spider [33]. MCS-SQL định nghĩa độ tin cậy của một ứng viên là tỷ lệ ứng viên cùng kết quả. Bỏ phiếu đa số của MCS-SQL đạt 62,8 với GPT-4 [21]. OmniSQL dùng đúng giao thức bỏ phiếu này cho mọi mô hình: 8 mẫu, gom theo `frozenset` kết quả, bỏ mẫu lỗi; mẫu trả rỗng vẫn được bỏ phiếu; nếu mọi mẫu đều lỗi thì chọn ngẫu nhiên một mẫu {N2, câu 5}, [14]. Lý do bỏ phiếu theo tập là nó **khớp với cách EX so kết quả**: khóa gom phiếu và độ đo dùng cùng một quan hệ tương đương.

#### 2.6 Giải mã dựa trên thực thi và sửa lỗi bằng phản hồi thực thi

Wang et al. (2018) là công trình đầu tiên dùng tín hiệu thực thi khi giải mã SQL: chạy truy vấn từng phần, bỏ các nhánh lỗi hoặc rỗng, đạt 83,8% EX trên WikiSQL [69]. Self-Debugging cho LLM tự giải thích mã và dùng phản hồi thực thi. Trên Spider, phương pháp tăng 2–3%, riêng nhóm câu khó nhất tăng 9%, và ngang hoặc hơn các baseline sinh gấp hơn 10 lần ứng viên [70]. DIN-SQL kết thúc pipeline bằng một bước tự sửa [16]. MAC-SQL có tác tử Refiner sửa theo lỗi thực thi, đạt 59,59% trên tập test [18]. Query fixer của CHASE-SQL thêm +3,83 cho baseline một ứng viên; bỏ nó khỏi hệ thống đầy đủ làm giảm 3,78 điểm [20]. Huang et al. cho thấy LLM **không tự sửa được lập luận** nếu không có phản hồi bên ngoài [71]. Kết quả này biện minh cho lựa chọn của Ours: chỉ sửa khi có tín hiệu thực thi (lỗi hoặc rỗng), không bắt mô hình xét lại mọi câu. Riêng với gpt-4o-mini, E-SQL đo được vòng sửa lỗi biến 6,58% truy vấn không chạy được thành chạy được, so với 0,39% ở GPT-4o [26].

#### 2.7 Liên kết lược đồ và truy hồi giá trị

BRIDGE là công trình đầu tiên chèn giá trị ô khớp với câu hỏi vào lược đồ đầu vào [48]. Với LLM, cách biểu diễn lược đồ và nội dung CSDL trong prompt (câu lệnh `CREATE TABLE`, dòng mẫu) đã được khảo sát có hệ thống bởi Rajkumar et al. và Chang & Fosler-Lussier [49], [50]; prompt của OmniSQL thuộc dạng DDL kèm giá trị ví dụ. RESDSQL tách liên kết lược đồ khỏi bước sinh khung truy vấn [46]. CHESS truy hồi giá trị bằng locality-sensitive hashing. Trong ablation của CHASE-SQL, bỏ bước truy hồi giá trị bằng LSH làm EX giảm từ 73,01 xuống 70,09 [19], [20]. CodeS dùng truy hồi giá trị hai tầng, từ thô đến mịn [34]. Theo ablation của MCS-SQL, thêm liên kết lược đồ được +2,1 điểm, thêm nội dung mẫu của bảng được +2,4 điểm [21]. Hai hướng đối lập cũng đáng nêu. Maamari et al. đưa toàn bộ lược đồ và vẫn đạt 71,83% test, lập luận rằng cắt lược đồ dễ làm mất cột cần thiết [29]. E-SQL đo được rằng lọc lược đồ cứng làm gpt-4o-mini giảm 5,54–8,21 điểm [26]. Ours giữ toàn bộ DDL của OmniSQL và chỉ **thêm** giá trị tìm được qua chỉ mục ngược. Chỉ mục ngược ánh xạ mỗi từ tới danh sách giá trị chứa nó [68]. Tra chính xác trên chỉ mục ngược rẻ hơn LSH nhưng kém chịu lỗi chính tả. Đây là đánh đổi nên nêu thẳng.

#### 2.8 LLM làm bộ chọn và các thiên lệch của nó

Hệ đa ứng viên chia tính toán thành hai pha: sinh đa dạng, rồi chọn. Selector theo cặp của CHASE-SQL là Gemini-1.5-Flash được fine-tune. Độ chính xác nhị phân: Claude-3.5-Sonnet chưa tinh chỉnh đạt 60,21%, Gemini-1.5-Pro chưa tinh chỉnh 63,98%, bản đã tinh chỉnh 71,01%. Trên cùng tập ứng viên, selector đã tinh chỉnh hơn self-consistency khoảng 6 điểm [20]. Selector trắc nghiệm của MCS-SQL **thấp hơn** bỏ phiếu khi không lọc (62,5 so với 62,8). Chỉ khi loại các ứng viên có độ tin cậy dưới 0,2, nó mới vượt lên 63,4 [21]. Bước merge top-2 của CSC-SQL, khi dùng mô hình chưa huấn luyện, cho 61,73 so với 61,86 của bỏ phiếu [40]. DPC (training-free) lật đúng 21,4% số câu mà đa số sai, nhưng làm hỏng 3% số câu mà đa số đúng [42]. LLM làm giám khảo còn thiên lệch theo vị trí. Chỉ đổi thứ tự ứng viên, Vicuna-13B đã thắng ChatGPT ở 66/80 câu [76]. GPT-4 làm giám khảo đồng ý với người trên 80% [77]. Từ các kết quả này rút ra cơ sở lý thuyết cho **cổng kích hoạt**: chỉ gọi selector khi phiếu phân tán, vì khi đó phiếu bầu mang ít thông tin, còn khi đã có đa số thì selector yếu dễ phá đáp án đúng.

#### 2.9 Tính toán lúc suy luận: độ phủ và khâu chọn

Lấy càng nhiều mẫu thì **độ phủ** (pass@k, hay oracle) càng tăng, gần như tuyến tính theo log số mẫu. Trên SWE-bench Lite, độ phủ tăng từ 15,9% với 1 mẫu lên 56% với 250 mẫu. Nhưng bỏ phiếu và reward model bão hòa sau vài trăm mẫu [72]. Phân bổ tính toán thích ứng theo độ khó hiệu quả hơn best-of-N đến hơn 4 lần [73]. Ước lượng không chệch của pass@k là pass@k = E[1 − C(n−c, k)/C(n, k)] [74]. Chen et al. (2024) chỉ ra rằng độ chính xác của bỏ phiếu có thể **không đơn điệu** theo số lời gọi: thêm lời gọi giúp câu dễ nhưng hại câu khó [75]. Trên BIRD dev, self-consistency bão hòa nhanh. Với Qwen2.5-Coder-32B, EX đi từ 67,56 (N = 8) lên 68,54 (N = 16) rồi 68,67 (N = 64) [40]. OpenSearch-SQL ghi nhận gpt-4o-mini đạt đỉnh ở khoảng 7–15 ứng viên [28]. Khoảng cách giữa độ phủ và khâu chọn rất lớn: oracle của CHASE-SQL đạt 82,79, trong khi self-consistency chỉ 68,84 [20]. Ours gọi selector ở 161/1.534 câu (10,5%), một dạng đơn giản của phân bổ thích ứng theo độ khó {N1}.

#### 2.10 Kiểm định thống kê cho so sánh ghép cặp

Hai hệ thống A và B được chấm trên cùng N câu. Gọi b là số câu A đúng còn B sai, c là số câu A sai còn B đúng. Kiểm định McNemar chỉ dùng các câu bất đồng [79]. Dạng tiệm cận là χ² = (|b − c| − 1)²/(b + c). Dạng chính xác dùng phân phối nhị thức: dưới H₀, b ~ Binomial(b + c, 0,5), và

$$p = \min\Big(1,\; 2\sum_{i=0}^{\min(b,c)} \binom{b+c}{i} 0{,}5^{\,b+c}\Big)$$

Dietterich chứng minh McNemar là kiểm định duy nhất (trong năm kiểm định ông khảo sát) có sai lầm loại I chấp nhận được khi mỗi thuật toán chỉ chạy được một lần [80]. Đây đúng là tình huống của một LLM cố định chấm một lần trên BIRD dev. Dror et al. đưa ra quy trình chọn kiểm định cho NLP và cho thấy kiểm định ý nghĩa thường bị bỏ qua hoặc dùng sai [81]. Khoảng tin cậy bootstrap ghép cặp lấy mẫu lại N câu B lần (ví dụ B = 10.000), tính ΔEX cho mỗi lần, rồi lấy phân vị 2,5–97,5 [82], [83]. Khi có m kiểm định, Bonferroni bác bỏ khi p ≤ α/m. Holm sắp các p-value tăng dần và bác bỏ khi p₍ᵢ₎ ≤ α/(m − i + 1); cách này mạnh hơn Bonferroni mà vẫn kiểm soát sai lầm theo họ [84]. Cần nói rõ giới hạn của McNemar: nó xét biến thiên theo câu hỏi, không xét biến thiên do lấy mẫu của mô hình. Phần biến thiên này phải đo bằng nhiều lần lấy mẫu (mục 4.5).

#### 2.11 Phân loại hướng tiếp cận và vị trí của Ours (bảng cho mục Nghiên cứu liên quan)

Bảng 2.x. EX (%) trên BIRD dev của các hướng tiếp cận tiêu biểu. "LB" là số lấy từ bảng xếp hạng chính thức, truy cập ngày 21/11/2026 [9]. "Paper" là số trong bài báo. Cột "Không FT" đánh dấu phương pháp không fine-tune bất kỳ thành phần nào.

| Nhóm | Phương pháp | Backbone | Dev EX | Không FT | Nguồn |
|---|---|---|---|---|---|
| PLM fine-tune | T5-3B | T5 | 23,34 | ✗ | [9] |
| LLM zero-shot | GPT-4 | GPT-4 | 46,35 | ✓ | [9] |
| ICL / phân rã | DIN-SQL | GPT-4 | 50,72 | ✓ | [9], [16] |
| ICL / phân rã | DAIL-SQL | GPT-4 | 54,76 | ✓ | [9], [17] |
| ICL / phân rã | TA-SQL | GPT-4 | 56,19 | ✓ | [9], [30] |
| Đa tác tử | MAC-SQL | GPT-4 | 57,56 | ✓ | [9], [18] |
| Prompting | SuperSQL | họ GPT-4 [chưa xác minh] | 58,50 | ✓ | [9], [32] |
| ICL | PURPLE | GPT-4o | 62,97 | ✓ | [9], [31] |
| Đa ứng viên + chọn | MCS-SQL | GPT-4 | 63,36 | ✓ | [9], [21] |
| Làm giàu câu hỏi | E-SQL | GPT-4o-mini | **61,60** | ✓ | [9], [26] |
| Làm giàu câu hỏi | E-SQL | GPT-4o | 65,58 | ✓ | [9], [26] |
| Tìm kiếm cây (MCTS) | MCTS-SQL | GPT-4o-mini | **63,15** (paper) | ✓ | [27] |
| Đa chiến lược | Pi-SQL | GPT-4o-mini | **64,54** (paper, chọn bằng kiểm chứng chéo; bỏ phiếu SQL 63,62) | ✓ | [41] |
| Liên kết lược đồ | RSL-SQL | GPT-4o | 67,21 | ✓ | [9], [22] |
| Đủ lược đồ + FT | Distillery | GPT-4o (fine-tune) | 67,21 | ✗ | [9], [29] |
| Truy hồi + sinh + unit test | CHESS (IR+CG+UT) | hỗn hợp | 68,31 | [chưa xác minh] | [9], [19] |
| Few-shot động | OpenSearch-SQL v2 | GPT-4o | 69,30 | ✓ | [9], [28] |
| MCTS, zero-shot | Alpha-SQL | Qwen2.5-Coder-32B | 69,70 | ✓ | [9], [25] |
| Đa đường + selector FT | CHASE-SQL | Gemini | 73,01 (paper) / 74,90 (LB, cập nhật 4/2025) | ✗ | [20], [9] |
| Đa bộ sinh | XiYan-SQL | hỗn hợp, có FT | 73,34 | ✗ | [9], [23] |
| Test-time scaling | Agentar-Scale-SQL | — | 74,90 | — | [9], [39] |
| FT mô hình mở | CodeS-15B | CodeS | 58,47 | ✗ | [9], [34] |
| Mô hình mã mở, chưa FT riêng | Qwen2.5-Coder-7B / 32B-Instruct (Gre/Maj, đo bởi OmniSQL) | — | 50,9/61,3; 64,5/67,0 | ✓ (cho text-to-SQL) | [14], [35] |
| FT dữ liệu tổng hợp | OmniSQL-7B / 32B (Gre/Maj) | Qwen2.5-Coder | 63,9/66,1; 64,5/67,0 | ✗ | [14] |
| RL | SQL-R1-7B / 14B | Qwen2.5-Coder | 66,6 / 67,1 | ✗ | [36] |
| RL | Reasoning-SQL 14B | Qwen2.5-Coder | 72,29 | ✗ | [9], [37] |
| RL | Arctic-Text2SQL-R1-32B | Qwen2.5-Coder | 72,20 | ✗ | [9], [38] |
| Mốc mô hình đóng (OmniSQL) | GPT-4o-mini (Gre/Maj) | — | 58,8 / 61,5 | ✓ | [14] |
| Mốc mô hình đóng (OmniSQL) | GPT-4o (Gre/Maj) | — | 61,9 / 64,0 | ✓ | [14] |
| Mốc mô hình đóng (OmniSQL) | GPT-4-Turbo; DeepSeek-V3 (Gre/Maj) | — | 62,0/63,6; 63,2/63,8 | ✓ | [14] |
| **Đề tài** | **Ours@8 / Ours v9** | **GPT-4o-mini** | **63,62 / 65,06** | ✓ | {N1} |

Cần ghi chú ba điểm dưới bảng. Thứ nhất, số của OmniSQL trên bảng xếp hạng (32B: 69,23 dev) khác số trong paper (67,0). Nhiều khả năng do cấu hình suy luận khác, nên chỉ dẫn số trong paper [9], [14]. Thứ hai, MCTS-SQL, E-SQL và Pi-SQL không báo số lời gọi theo cách so được cùng ngân sách. Vì vậy chỉ phép so với OmniSQL là thật sự cùng ngân sách. Thứ ba, các mục nhập năm 2026 trên bảng xếp hạng dùng bản dev mới (`dev_20251106`), không cùng thang với bảng này [9], [12]. Về vị trí của Ours: ở 8 mẫu, Ours cao hơn mọi con số gpt-4o-mini đã công bố mà nhóm nghiên cứu tìm được (61,5; 61,60; 63,15). Mức hơn MCTS-SQL chỉ khoảng 0,5 điểm và không kiểm định được, nên viết là "tương đương". Ở cấu hình đầy đủ, Ours cao hơn MCTS-SQL khoảng 2 điểm, ngang E-SQL + GPT-4o (65,58) và GPT-4o Maj (64,0). Ours vẫn thấp hơn OmniSQL-7B/32B Maj (66,1 và 67,0).

#### 2.12 Bộ dữ liệu: BIRD là trọng tâm, Spider và EHRSQL làm bối cảnh

**BIRD** (Li et al., NeurIPS 2023 Datasets and Benchmarks [1]) có 12.751 cặp câu hỏi–SQL trên 95 CSDL (33,4 GB, 37 lĩnh vực). Dữ liệu chia thành train 9.428 câu (69 CSDL), dev 1.534 câu (11 CSDL) và test ẩn 1.789 câu (15 CSDL). Trung bình mỗi CSDL có 7,3 bảng và 549 nghìn dòng. Nguồn CSDL: 32% từ Kaggle, 48% từ CTU Prague Relational Learning Repository, 20% tự xây [1]. Bài báo chia tri thức ngoài thành bốn loại, có chồng lấn: suy luận số 24,5%, tri thức miền 23,6%, đồng nghĩa 7,2%, minh họa giá trị 70,1% [1]. Câu hỏi do 11 người bản ngữ có kiến thức CSDL viết. SQL do hai người gán nhãn độc lập (double-blind) và chỉ được giữ khi kết quả khớp; nếu không khớp thì chuyên gia phân xử [1]. Bản dev dùng trong đề tài là `dev_20240627`: 925 câu simple, 464 moderate, 145 challenging (60,3/30,2/9,5%). Theo CSDL: card_games 191, codebase_community 186, formula_1 174, thrombosis_prediction 163, student_club 158, toxicology 145, superhero 129, european_football_2 129, financial 106, california_schools 89, debit_card_specializing 64. Trong bản này, 148/1.534 câu có evidence rỗng. Các số này đếm trực tiếp trên tệp `data/benchmarks/bird/dev_20240627/dev.json` của dự án, {N1}. Bản trích HTML của bài báo ghi tỷ lệ "simple 30% / moderate 60%", ngược với số đếm thực tế. Nên dẫn số đếm và đối chiếu bảng gốc trong PDF. BIRD đã phát hành một bản dev "cleaner" ngày 25/9/2023. Ngày 13/11/2025, BIRD phát hành `dev_20251106`, có rà soát lại toàn bộ câu nhưng không công bố số câu đã sửa [9], [12]. Mini-Dev (500 câu; 30/50/20% theo độ khó; chạy trên SQLite, MySQL và PostgreSQL) bổ sung Soft-F1 và R-VES [11]. Con người đạt 72,37% EX khi không có tri thức ngoài và 92,96% khi có, trên tập test. GPT-4 đạt 46,35 (dev) và 54,89 (test) [1]. Abstract của bài báo ghi ChatGPT đạt 40,08%, khác số 39,30 trong bảng; con số 40,08 có lẽ là của cấu hình ChatGPT + CoT [1], [9]. Giấy phép BIRD hiện là CC BY-SA 4.0 [10].

**Spider** [2] có 10.181 câu, 5.693 SQL duy nhất, 200 CSDL, 138 lĩnh vực, bốn mức độ khó và các độ đo EM/EX. Từ 11/2020, test-suite accuracy [3] là độ đo chính thức ([taoyds/spider](https://github.com/taoyds/spider)). Spider ngừng nhận bài từ 05/02/2024, đầu bảng đạt 91,2% EX ([Spider leaderboard](https://yale-lily.github.io/spider)). **Spider 2.0** [4] gồm 632 bài toán quy trình doanh nghiệp, CSDL thường trên 1.000 cột; o1-preview chỉ đạt 21,3%. **EHRSQL** [5] là benchmark y khoa trên MIMIC-III và eICU. Câu hỏi thu từ 222 nhân viên bệnh viện, tổng khoảng 24,4 nghìn cặp, có câu không trả lời được, và 93,2% truy vấn dùng cột thời gian. Viết hai bộ cuối như bối cảnh để giải thích vì sao chọn BIRD: đủ khó, có baseline gpt-4o-mini đã công bố, có giá trị bẩn và evidence. Không đề xuất thí nghiệm trên các bộ này.

#### 2.13 Độ đo: EX, VES, R-VES, Soft-F1, test-suite và cách bộ chấm thực sự hoạt động

BIRD định nghĩa [1]:

$$\text{EX} = \frac{1}{N}\sum_{n=1}^{N} \mathbb{1}(V_n, \hat V_n), \qquad \text{VES} = \frac{1}{N}\sum_{n=1}^{N} \mathbb{1}(V_n, \hat V_n)\cdot \sqrt{\frac{E(Y_n)}{E(\hat Y_n)}}$$

V_n và V̂_n là tập kết quả của SQL vàng và SQL dự đoán. E(·) là thời gian thực thi. Từ 04/8/2024, R-VES (thưởng theo bậc) thay VES cho các bài nộp mới [9]. Soft-F1 so từng ô giữa hai bảng kết quả, nên ít nhạy với thứ tự cột và giá trị thiếu [11]. Test-suite accuracy chạy truy vấn trên nhiều CSDL được chưng cất, nhằm giảm EX dương tính giả. Với độ đo cũ của Spider, tỷ lệ âm tính giả trung bình là 2,5%, tệ nhất 8,1% [3]. Về cài đặt, cả bộ chấm chính thức của BIRD và `evaluate_bird.py` của OmniSQL đều so `set(pred_rows) == set(gold_rows)`. Phép so này bỏ qua thứ tự dòng và dòng trùng, nhưng vẫn phân biệt thứ tự cột. Lỗi hoặc quá thời gian đều bị tính 0. Bộ chấm chính thức mặc định timeout 30 giây [10]. OmniSQL mặc định 20 tiến trình và 10 giây cho cả cặp SQL dự đoán và SQL vàng [15], {N5}. Cách so tập này "dễ dãi" với ORDER BY và DISTINCT nhưng "khắt khe" với cột thừa. FLEX ghi nhận 58,13% số âm tính giả của 10 mô hình hàng đầu là do biến thể cấu trúc đầu ra chấp nhận được [8]. Đề tài giữ EX vì đó là độ đo của paper so sánh, và cả hai hệ thống chịu cùng hạn chế {N2, câu 7}.

#### 2.14 Nhiễu nhãn trong BIRD và trần thực tế của EX

Viết mục này như một mục riêng, vì nó giải thích giới hạn ở câu khó. Wretblad et al. [6] kiểm tra một phần BIRD dev. Ở CSDL financial, 49% câu có nhiễu (52/106) và 20,7% SQL vàng sai (22/106). Ở california_schools, SQL vàng sai 40% (8/20); ở thrombosis_prediction, 30% (6/20). Khi sửa SQL vàng, zero-shot GPT-3.5 vượt DIN-SQL và MAC-SQL. Jin et al. [7] sửa tay 100 câu dev ngẫu nhiên và thấy 48 câu cần sửa. Đánh giá lại 16 agent trên tập đã sửa, hiệu năng tương đối thay đổi từ −7% đến +31%, thứ hạng dịch tới ±9 bậc. Tương quan hạng với dev gốc giảm từ r_s = 0,85 (tập chưa sửa) xuống 0,32 (tập đã sửa). Trên tập đã sửa, CHESS tăng từ 62% lên 81% {N9}, [7]. Jin et al. cũng kiểm tra Mini-Dev và thấy 52,8% câu có lỗi. Arcwise báo cáo 161 câu lỗi trên Mini-Dev, khoảng 32,3% [13], [7]. Trên 200 cặp BIRD do chuyên gia gán nhãn, FLEX thấy EX có 21 dương tính giả và 17 âm tính giả. FLEX dùng GPT-4o làm giám khảo, đạt Cohen's κ = 87,04 với chuyên gia, so với 62,00 của EX [8]. Từ đó có thể suy luận trần thực tế của EX trên dev gốc vào khoảng 75–85%. Đây là suy luận, chưa có trần chính thức nào được công bố {N9}. Đề tài có số liệu riêng khớp với các nghiên cứu trên: trên tập tuning, 9% câu có cả 8/8 mẫu cho cùng một kết quả mà vẫn bị chấm sai {N2, câu 8}. Hệ quả cho khóa luận: chênh lệch vài điểm EX phải đi kèm kiểm định ghép cặp. So sánh tương đối giữa hai hệ thống cùng mô hình vẫn hợp lệ, vì cả hai cùng chịu một bộ nhãn.

#### 2.15 Rò rỉ dữ liệu huấn luyện

Ranaldi et al. [78] che 25% tên cột và yêu cầu GPT-3.5 khôi phục. Mô hình khôi phục đúng trung bình 33,42% trên Spider, so với 13,21% trên Termite, một bộ chưa công bố. Test-suite accuracy cũng giảm trên Termite: 16,11 điểm ở nhóm easy và 20,50 điểm ở nhóm hard. BIRD được công bố ngày 4/5/2023, trước mốc kiến thức tháng 10/2023 của GPT-4o mini [1], [57]. Vì vậy giá trị EX tuyệt đối có thể bị thổi phồng. Tuy nhiên, Ours và baseline dùng cùng snapshot, nên phần chênh lệch giữa hai hệ thống không đến từ rò rỉ {N2, câu 9}. Few-shot chỉ lấy từ BIRD train, nên không có câu dev nào lọt vào prompt. Biện pháp này không giải quyết được rò rỉ nằm sẵn trong trọng số mô hình.

### Chương 3. Phương pháp đề xuất: bốn lớp quanh prompt gốc, mỗi lớp nhắm một nhóm lỗi

#### 3.1 Phát biểu bài toán và ký hiệu

Đặt π_base(q, e, S) là prompt gốc của OmniSQL (trường `input_seq`). Prompt này gồm 6 phần: Task Overview; Database Engine (SQLite); Database Schema (DDL đầy đủ, mỗi cột có kiểu, khóa và chú thích `-- example: [...]`); Question (evidence ghép trước câu hỏi); Instructions ("suy nghĩ từng bước", "chỉ trả đúng thông tin được hỏi"); Output Format (khối ```` ```sql ````) {N1}. Lưu ý quan trọng: phần example **đã chứa** giá trị khớp với chữ trong câu hỏi. Nghĩa là baseline đã có một lớp truy hồi giá trị đơn giản {N2, câu 2}. Ours định nghĩa:

| Ký hiệu | Ý nghĩa | Giá trị trong v9 {N7} |
|---|---|---|
| V(q, e) | Tập giá trị lưu trữ khớp với q ⊕ e | tối đa 12 giá trị |
| F(q, e) | Ví dụ few-shot từ BIRD train | k = 3, BM25 |
| P = enrich(π_base, V, F) | Prompt đã làm giàu | chèn trước "Instructions:" |
| P_plan | P với Instructions thay bằng 6 bước kế hoạch | — |
| y_g | Ứng viên greedy trên P | T = 0, n = 1 |
| {y_s^i} | Mẫu từ P | n = 8, T = 0,8 |
| {y_p^j} | Mẫu từ P_plan | n = 8, T = 0,8 |
| y_gr | Bản sửa của y_g nếu exec(y_g) = ⊥ hoặc rỗng/toàn NULL | ≤ 1 lời gọi, T = 0 |
| κ(y) | Dấu vân tay của **tập** dòng exec(y) | SHA-256 trên các dòng đã chuẩn hóa |
| G₁, …, G_m | Nhóm ứng viên cùng κ, sắp theo kích thước giảm dần | — |
| τ | Ngưỡng tỷ lệ phiếu để không gọi selector | 0,5 |
| K, L | Số nhóm đưa vào selector, số mẫu selector | 3, 5 (T = 0,8) |

Tập ứng viên là C = {y_g} ∪ {y_s^i}_{i=1}^{8} ∪ {y_p^j}_{j=1}^{8} ∪ {y_gr}. Tập bỏ phiếu C⁺ gồm các ứng viên chạy được và trả về ít nhất một giá trị khác NULL. Nếu C⁺ rỗng thì dùng mọi ứng viên chạy được. Luật chọn:

$$s = \frac{|G_1|}{\sum_k |G_k|},\qquad \hat y = \begin{cases} \text{rep}(G_1) & \text{nếu } m = 1 \ \text{hoặc}\ (|G_1| > |G_2| \ \text{và}\ s \ge \tau) \\ \text{rep}(G_{k^*}),\ k^* = \arg\max_{k \le K} \sum_{l=1}^{L} \mathbb{1}[a_l = k] & \text{ngược lại} \end{cases}$$

Trong đó rep(G) là ứng viên xuất hiện đầu tiên của nhóm G (greedy đứng đầu), và a_l là lựa chọn của lần lấy mẫu selector thứ l. Khi hòa phiếu selector, chọn nhóm lớn hơn. Nếu không đọc được lựa chọn nào, quay về G₁ {N7}. Công thức này là MBR-exec [63] trên tập ứng viên trộn hai prompt, cộng thêm một cổng theo độ tin cậy kiểu MCS-SQL [21].

#### 3.2 Phân tích lỗi của baseline là căn cứ thiết kế

Theo DIN-SQL [16], mở chương bằng bảng lỗi của baseline greedy (630/1.534 câu sai), rồi ánh xạ mỗi nhóm lỗi sang một thành phần {N1}, {N2, câu 24}:

| Nhóm lỗi của baseline | Số câu | Thành phần nhắm tới |
|---|---|---|
| Đúng cấu trúc, sai giá trị | 236 | Truy hồi giá trị (3.4), few-shot (3.5) |
| Sai số cột | 145 | Bước 1 và 6 của prompt query plan (3.6) |
| Sai số dòng | 104 | Bỏ phiếu theo tập: gộp biến thể DISTINCT (3.8) |
| Lỗi thực thi / trả rỗng | 74 / 68 | Sửa lỗi theo thực thi (3.7) |
| Phiếu phân tán | — | Selector có cổng (3.9) |

Tổng các nhóm là 627, ít hơn 630 câu sai 3 câu. Cần kiểm tra lại trong `baseline_sample_analysis.json` xem 3 câu còn lại thuộc nhóm nào, hoặc thêm dòng "khác" [CẦN BỔ SUNG].

#### 3.3 Tổng quan pipeline (Hình 3.1) và thuật toán

Vẽ Hình 3.1 từ sơ đồ trong {N1} §5.1. Luồng gồm: truy hồi giá trị và few-shot; dựng prompt làm giàu; ba nhánh sinh chạy song song (1 greedy, 8 mẫu prompt gốc, 8 mẫu prompt kế hoạch); thực thi 17 SQL; sửa câu greedy nếu cần; bỏ phiếu theo tập; cổng; selector. Thuật toán 3.1 (mã giả, viết lại từ `OursV9.run` {N7}):

```
Thuật toán 3.1  Ours v9 cho một câu hỏi
Vào: q, e, D, π_base;  Ra: ŷ
1  V ← ValueIndex(D).search(q ⊕ e)[:12];  F ← BM25_train(q ⊕ e)[:3]
2  P ← enrich(π_base, V, F);  P_plan ← replace_instructions(P)
3  song song: y_g ← M(P, T=0);  Y_s ← M(P, n=8, T=0.8);  Y_p ← M(P_plan, n=8, T=0.8)
4  C ← {y_g} ∪ Y_s ∪ Y_p;  thực thi mọi c ∈ C trên D (chỉ đọc, timeout 60 s)
5  nếu exec(y_g) lỗi hoặc không có giá trị khác NULL:
6      y_gr ← M(repair(P, y_g, thông_báo_lỗi_hoặc_rỗng), T=0);  nếu y_gr ≠ y_g: C ← C ∪ {y_gr}
7  C⁺ ← {c ∈ C : chạy được và có giá trị}  (nếu rỗng: mọi c chạy được)
8  nếu C⁺ = ∅: trả y_g (trạng thái unresolved)
9  G ← gom C⁺ theo κ(c), sắp |G| giảm dần, giữ thứ tự xuất hiện khi hòa
10 nếu |G| = 1 hoặc (|G₁| > |G₂| và |G₁|/Σ|G_k| ≥ 0.5): trả rep(G₁)
11 a₁..a₅ ← M(select(P, rep(G₁..G₃)), n=5, T=0.8);  trả rep(G_k*) theo đa số aₗ (dự phòng: G₁)
```

Số lời gọi API mỗi câu: 3 lời gọi cố định (lời gọi `n = 8` tính là một), cộng tối đa 1 lời gọi sửa lỗi và tối đa 1 lời gọi selector. Trung bình đo được là 3,21 lời gọi mỗi câu {N3}.

#### 3.4 Thành phần 1: truy hồi giá trị bằng chỉ mục ngược

Động lực: 236/630 câu sai của baseline đúng cấu trúc nhưng sai giá trị. Baseline chỉ chèn giá trị khớp vào danh sách ví dụ của cột, lẫn với các ví dụ khác. Ours nêu thẳng giá trị nằm ở cột nào {N1}. Cài đặt (`values.py` {N7}):

- **Xây chỉ mục, một lần cho mỗi CSDL, lưu cache JSON.** Chỉ duyệt cột không mang kiểu số hay BLOB. Lấy các giá trị DISTINCT kiểu text dài 1–80 ký tự. Bỏ cả cột nếu có hơn 50.000 giá trị khác nhau, vì đó là cột văn bản tự do hoặc định danh, không phải cột phân loại. Bỏ giá trị dài hơn 8 từ. Mỗi từ (chữ thường, `[0-9a-z]+`, trừ 67 stopword như "the", "count", "average") trỏ tới danh sách các giá trị chứa nó.
- **Truy vấn.** Văn bản truy vấn là câu hỏi ghép với evidence. Chỉ dùng từ dài từ 3 ký tự trở lên hoặc là số. Bỏ từ quá phổ biến (danh sách trỏ dài hơn 2.000 giá trị). Một giá trị được giữ nếu khớp chính xác bề mặt (cả cụm xuất hiện trong câu, có ranh giới từ, hoặc nằm trong dấu nháy), hoặc nếu độ phủ từ của nó ≥ 0,5. Giá trị toàn số chỉ được giữ khi nằm trong dấu nháy.
- **Điểm và giới hạn.** Điểm = 100·exact + round(10·coverage) + số từ khớp. Mỗi cột giữ tối đa 4 giá trị, tổng tối đa 24, rồi cắt còn 12 khi đưa vào prompt (`max_value_hints = 12`).
- **Định dạng chèn vào prompt.** Một khối mở đầu bằng *"Stored database values that match words in the question (exact stored spelling; use one only if the question refers to it):"*, tiếp theo là các dòng `- bảng.cột = 'giá trị'`.

Ví dụ minh họa cho Hình 3.2: câu hỏi nhắc "Contra Costa" thì baseline chèn giá trị này vào phần example của cột `County Name` {N1}, còn Ours thêm dòng chỉ rõ bảng và cột. Em nên lấy dòng thật từ trace để vẽ hình. Đánh đổi cần nêu trong khóa luận: so khớp từ chính xác thì rẻ và tất định, nhưng không bắt được lỗi chính tả như LSH của CHESS [19].

#### 3.5 Thành phần 2: few-shot BM25 từ BIRD train

Cài đặt (`fewshot.py` {N7}). Kho ví dụ là BIRD train, 9.428 câu trên 69 CSDL. Khi nạp kho, mã nguồn **tự kiểm tra** rằng không ví dụ nào trùng `db_id` hay trùng câu hỏi với dev; nếu trùng thì dừng. Chỉ mục BM25Okapi (thư viện `rank_bm25`, tham số mặc định) dựng trên câu hỏi ghép evidence của train, tách token `[0-9a-z]+`, chữ thường. Lấy top 3 ví dụ, hòa điểm thì giữ thứ tự gốc. Mỗi ví dụ có dạng `Question / Evidence / SQL`, đặt dưới tiêu đề *"Examples from other databases (they show SQL patterns only, not this database)"*. Động lực: cho mô hình xem quy ước SQL của BIRD, như CAST AS REAL, cách đếm và cách lọc {N1}. Lý do chọn BM25 thay vì embedding: tất định, rẻ, không thêm lời gọi API, dễ tái lập. Câu hỏi BIRD tương tự thường trùng từ khóa phép toán như tỷ lệ, phần trăm, đếm {N2, câu 21}. Đối chiếu với tài liệu: chọn ví dụ theo câu hỏi đã che token lược đồ hơn chọn theo câu hỏi thô khoảng 0,7 điểm trên BIRD [21]. Đây là một hướng cải tiến chưa thử.

#### 3.6 Thành phần 3: làm giàu prompt và hai bộ sinh

Hàm `enrich_prompt` chèn khối giá trị và khối ví dụ **ngay trước** "Instructions:" của prompt gốc. Mọi phần khác của prompt OmniSQL được giữ nguyên {N7}. Bộ sinh thứ nhất dùng P: 1 câu greedy và 8 mẫu, giống giao thức Gre/Maj của paper nhưng ngữ cảnh giàu hơn. Bộ sinh thứ hai dùng P_plan, thay Instructions bằng 6 bước: (1) liệt kê đúng các mục được hỏi theo thứ tự câu hỏi nhắc, mỗi mục một cột, không thêm cột phụ, không dùng `SELECT *`, chỉ dùng hàm gộp khi được hỏi; (2) áp dụng evidence đúng nghĩa đen; (3) ánh xạ mỗi điều kiện sang cột và giá trị lưu trữ, kiểm tra chính tả và hoa thường; (4) chỉ join các bảng cần thiết theo khóa trong lược đồ; (5) với "cao nhất/thấp nhất/nhiều nhất", dùng ORDER BY kèm LIMIT; (6) đọc lại câu hỏi và kiểm tra danh sách SELECT. Toàn văn tiếng Anh đặt ở Phụ lục A. Động lực của bộ sinh thứ hai là tạo đa dạng: prompt khác thì sai theo kiểu khác. Trên tập tuning, số câu có ít nhất một ứng viên đúng tăng từ 217 lên 227 khi thêm bộ sinh này {N1}. Cơ sở lý thuyết là Query Plan CoT của CHASE-SQL [20] và việc dùng nhiều prompt trong MCS-SQL (+1,3 điểm từ 1 lên 5 prompt) [21] và DiVeRSe [65].

#### 3.7 Thành phần 4: thực thi và sửa lỗi câu greedy

Mọi SQL chạy trên SQLite ở chế độ chỉ đọc (URI `mode=ro`). Một progress handler ngắt truy vấn sau 60 giây, bằng timeout của bộ chấm, và chỉ lấy tối đa 200.000 dòng (`database.py` {N7}). Nếu câu greedy lỗi, hoặc chạy được nhưng không có giá trị khác NULL, hệ thống gửi lại cho mô hình: prompt P, SQL cũ, và phản hồi (thông báo lỗi SQLite, hoặc *"The query executed but returned no rows (or only NULL values)."*). Kèm theo là chỉ dẫn mở: *"If the previous query was in fact correct, you may return it unchanged."* Chỉ dẫn này tránh giả định chắc chắn có lỗi, tương tự prompt sửa "gentle" của DIN-SQL [16]. Chỉ sửa một lần, ở T = 0. Động lực: baseline có 74 câu lỗi thực thi và 68 câu trả rỗng {N1}. Cơ sở lý thuyết: phản hồi thực thi là tín hiệu bên ngoài mà Huang et al. cho là cần thiết để tự sửa có tác dụng [71], [70].

#### 3.8 Thành phần 5: bỏ phiếu theo tập kết quả

Dấu vân tay κ(y) chuẩn hóa từng ô. NULL thành `null`; bytes thành chuỗi hex; số được chuẩn hóa qua `Decimal(str(v)).normalize()` để 1 và 1.0 trùng nhau; các kiểu khác thành (tên kiểu, chuỗi). Sau đó lấy tập các dòng duy nhất, sắp xếp, và băm SHA-256 {N7}. Như vậy thứ tự dòng và dòng trùng bị bỏ qua, đúng như EX và như `frozenset` trong hàm bỏ phiếu của baseline. Bản v8 gom theo multiset, nên hai SQL chỉ khác nhau ở DISTINCT bị tách thành hai nhóm và phiếu bị chia nhỏ. Bản v9 sửa lại cho đúng định nghĩa {N2, câu 16}. Trong khóa luận, nói rõ: đây là **sửa cho khớp quan hệ tương đương của độ đo**, không phải mẹo tăng điểm. Có hai khác biệt với hàm `major_voting()` của tác giả. Thứ nhất, Ours ưu tiên các ứng viên có giá trị: ứng viên rỗng hoặc toàn NULL chỉ được tính khi không còn ứng viên nào khác. Baseline thì vẫn tính phiếu cho ứng viên rỗng {N7}, [14]. Thứ hai, khi mọi ứng viên đều lỗi, Ours trả câu greedy thay vì chọn ngẫu nhiên. Phải nêu khác biệt thứ nhất, vì nó cũng có mặt trong so sánh "cùng 8 mẫu" (xem 4.4).

#### 3.9 Thành phần 6: selector có cổng

Selector chỉ được gọi khi có ít nhất 2 nhóm và một trong hai điều kiện đúng: hai nhóm lớn nhất bằng nhau, hoặc nhóm lớn nhất chiếm dưới 50% phiếu (`needs_selection` {N7}). Prompt selector gồm phần đầu của P (lược đồ, giá trị, ví dụ, câu hỏi) và tối đa 3 ứng viên đại diện cho 3 nhóm lớn nhất. Mỗi ứng viên kèm SQL và bản xem trước kết quả: tên cột, số dòng, số dòng khác nhau, 5 dòng đầu (mỗi ô cắt còn 60 ký tự). Phần cuối là bảng kiểm 4 điểm: danh sách SELECT đúng thông tin được hỏi; mọi điều kiện và evidence được áp đúng cột và giá trị; join, gộp, sắp xếp, giới hạn đúng; kết quả hợp lý. Mô hình được yêu cầu kết thúc bằng một dòng "Answer: <id>". Selector được lấy 5 mẫu ở T = 0,8, rồi bầu theo đa số. Động lực và lựa chọn ngưỡng đều từ thí nghiệm trên tuning: khi gọi selector cả lúc đã có đa số, gpt-4o-mini sửa được bao nhiêu câu thì làm hỏng bấy nhiêu, gần như tung đồng xu {N1}, {N2, câu 17, 28}. Trên toàn dev, selector được gọi ở 161/1.534 câu {N1}. Selector chỉ thấy SQL ứng viên và kết quả của chúng, không bao giờ thấy SQL vàng. Có test đơn vị trong `tests/test_bird_ours.py` {N2, câu 42}.

#### 3.10 Quá trình phát triển v6 → v8 → v9 (bài học thiết kế)

Nên dành nửa trang cho mục này, vì người chấm hay hỏi "đã thử gì khác". Bản **v6** là pipeline tác tử với các bước JSON (liên kết lược đồ, phân rã, 3 nhánh, bỏ phiếu theo dấu vân tay cục bộ, selector khi bất đồng). Bản này chỉ đạt 60,04% trên toàn dev với 5,31 lời gọi mỗi câu và 3,74 USD, **thấp hơn baseline Maj (61,99)** {N3}. Trên tuning, các bước JSON không có suy luận và khối yêu cầu/kế hoạch nặng làm các ứng viên **đồng thuận về cùng một SQL sai có hệ thống**. Tài liệu cũng ghi nhận liên kết lược đồ và phân rã ít giá trị, thậm chí có hại, với gpt-4o-mini (chú thích đầu `ours_v8.py` {N7}; khớp với kết quả của E-SQL [26]). Bản **v8** quay về dùng đúng prompt baseline làm bộ sinh, rồi thêm giá trị, few-shot, sửa lỗi, bỏ phiếu và selector khi hòa. Kết quả: 63,30% toàn dev, 63,05% held-out, 2,13 lời gọi mỗi câu, 3,29 USD. So với Maj-8 trên held-out: 66 câu chỉ v8 đúng, 43 câu chỉ baseline đúng, p = 0,035; trên toàn dev p = 0,10 {N3}. Bản **v9** thêm bộ sinh kế hoạch, bỏ phiếu theo tập và selector có cổng: 65,06%, 3,21 lời gọi mỗi câu. So với v8: 63 câu chỉ v9 đúng, 36 câu chỉ v8 đúng, p = 0,0086 {N3}. Bài học rút ra: với mô hình nhỏ, giữ nguyên prompt có suy luận mạnh nhất rồi bổ sung ngữ cảnh tốt hơn tái cấu trúc thành nhiều bước JSON.

#### 3.11 Các bảo đảm chống rò rỉ và tính tái lập

SQL vàng chỉ dùng trong bộ chấm. Trường `output_seq` (chứa gold) của tệp prompt không bao giờ được gửi lên API. Kho few-shot được kiểm tra tự động không trùng dev. Selector và bước sửa lỗi chỉ thấy dữ liệu từ ứng viên. Mọi dự đoán, trace và ứng viên đều được lưu, nên chấm lại được từng con số mà không gọi API {N1}, {N2, câu 41–42}, {N4}.

### Chương 4. Thực nghiệm: thiết lập, kết quả, cùng ngân sách, ablation, lỗi, chi phí

#### 4.1 Thiết lập thực nghiệm

**Dữ liệu và phân chia.** BIRD dev `dev_20240627`, 1.534 câu, 11 CSDL SQLite. Tệp `dev.zip` lấy từ host chính thức, SHA-256 `cdd6d19f…a630` {N3}, {N5}. Trước khi chạy v9, 1.534 câu được chia ngẫu nhiên với seed 20261119: 300 câu tuning và 1.234 câu held-out, lưu ở `results/omnisql/ours/splits.json`. Mọi lựa chọn của v9 (prompt kế hoạch, ngưỡng và số mẫu selector, bỏ phiếu theo tập) đều chọn trên tuning. Bản full chỉ chạy một lần {N1}, {N2, câu 34}.

**Baseline.** Hàng GPT-4o-mini trong Bảng 4 của OmniSQL [14]. Prompt là `input_seq` trong `data/dev_bird.json` do tác giả phát hành (Hugging Face revision `e1db8bb1…`, SHA-256 `65186bb8…5b50`). Greedy dùng T = 0, n = 1. Maj dùng một lời gọi n = 8 ở T = 0,8, rồi chọn bằng hàm `major_voting()` của tác giả. SQL được trích từ khối ```` ```sql ```` cuối cùng, theo `infer.py`. `max_tokens` = 2.048. Tác giả không công bố mã gọi API GPT, nên `run_gpt4o_reference.py` là adapter **tái dựng theo giao thức công bố**. Câu diễn đạt đúng trong khóa luận: *"Tái dựng baseline GPT-4o mini theo giao thức được công bố; dùng đúng BIRD dev và evaluator tác giả; các lựa chọn API không được công bố được ghi nhận như giả định triển khai."* Không viết "sao chép chính xác mã API của tác giả" {N4}.

**Bộ chấm.** `evaluate_bird.py` gốc tại commit `a66d732010c89fac4353488d1c59e0b06f92b742`, giống từng byte với upstream (63 tệp) {N5}. Tham số chấm là `num_cpus = 4`, `timeout = 60` giây, chạy một lượt warm-up rồi một lượt ghi điểm. Bước bỏ phiếu của baseline cũng được áp cùng giới hạn này, bằng cách thay hàm `execute_sqls_parallel` lúc chạy mà không sửa tệp gốc {N5}. Lý do chọn 60 giây: thời gian chạy SQL vàng đo trên cả 1.534 câu cho thấy chỉ 4 câu vượt 5 giây (q701 891 s, q518 178 s, q646 17,5 s, q596 9,4 s), và không câu nào nằm trong khoảng 20–170 giây. Ở ngưỡng 60 giây, q646 luôn chạy kịp, còn q518 và q701 luôn timeout, giống tình huống trên máy chủ của tác giả với 10 giây. Với 120 giây, q518 sát ngưỡng và bị lật kết quả giữa các lần chạy {N5}. Môi trường: Windows 11, Python 3.12.4, SQLite 3.45.3 {N5}.

**Chi tiết cài đặt Ours** (Bảng 4.x):

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Mô hình | `gpt-4o-mini-2024-07-18` | {N1} |
| `max_tokens` mọi lời gọi | 2.048 | {N7} |
| Greedy | T = 0, n = 1 | {N7} |
| Mẫu prompt gốc đã làm giàu | n = 8, T = 0,8, một lời gọi | {N7} |
| Mẫu prompt kế hoạch | n = 8, T = 0,8, một lời gọi | {N7} |
| Sửa lỗi | ≤ 1 lời gọi, T = 0, khi greedy lỗi/rỗng/toàn NULL | {N7} |
| Giá trị gợi ý | ≤ 12 (tìm ≤ 24, ≤ 4 mỗi cột) | {N7} |
| Few-shot | k = 3, BM25Okapi trên question + evidence của train | {N7} |
| Bỏ phiếu | theo tập dòng, ưu tiên ứng viên có giá trị | {N7} |
| Cổng selector | ≥ 2 nhóm và (hòa top hoặc tỷ lệ < 0,5) | {N7} |
| Selector | top-3 nhóm, n = 5, T = 0,8, bầu đa số | {N7} |
| Thực thi | SQLite chỉ đọc, timeout 60 s, ≤ 200.000 dòng | {N7} |
| Song song | 8 luồng; giới hạn chi phí `--max-usd 10` | {N1} |
| Thời gian chạy toàn dev | khoảng 45 phút với 8 luồng; 11,8 s mỗi câu | {N1} |

**Cấu hình con tính từ cùng lần chạy.** Hai cột Ours Gre và Ours Maj **không phải hai lần chạy riêng**. Ours Gre là ứng viên `g`; nếu `g` lỗi hoặc rỗng thì dùng bản sửa `gr`, xảy ra ở 98 câu. Ours Maj (Ours@8) là bỏ phiếu trên đúng 8 mẫu `s1`–`s8`. Bộ chấm cục bộ khớp 998/998 câu với bộ chấm gốc trên lần chạy v9, nên các cột tính lại này đáng tin. Trong khóa luận phải ghi đúng cụm "cấu hình con được tính từ cùng một lần chạy" {N1}, {N2, câu 40}.

#### 4.2 Kiểm chứng tái lập bộ chấm và baseline

Mục này trả lời câu hỏi phản biện "em có tái lập đúng không" trước khi bị hỏi. Đưa dự đoán do tác giả công bố qua bộ chấm cho ra **đúng 6/6 con số EX của paper** {N5}:

| Mô hình | Chế độ | Đúng / 1.534 | EX (%) | Paper (%) |
|---|---|---|---|---|
| OmniSQL-7B | greedy | 980 | 63,89 | 63,9 |
| OmniSQL-14B | greedy | 985 | 64,21 | 64,2 |
| OmniSQL-32B | greedy | 989 | 64,47 | 64,5 |
| OmniSQL-7B | majority | 1.014 | 66,10 | 66,1 |
| OmniSQL-14B | majority | 1.011 | 65,91 | 65,9 |
| OmniSQL-32B | majority | 1.028 | 67,01 | 67,0 |

Chạy lại thật baseline GPT-4o-mini trên đủ 1.534 câu: máy chủ trả về đúng snapshot, mọi phản hồi có `finish_reason = stop` {N5}:

| Chế độ | Đúng / 1.534 | EX (%) | Paper (%) | Chênh | Token vào / ra | Chi phí |
|---|---|---|---|---|---|---|
| Greedy | 904 | 58,93 | 58,8 | +0,1 (≈ 2 câu) | 3,12 triệu / 0,40 triệu | 0,71 USD |
| Maj-8 | 951 | 61,99 | 61,5 | +0,5 (≈ 8 câu) | 3,12 triệu / 3,24 triệu | 2,41 USD |

Phân tích độ lệch so với paper không cần gọi API {N4}. (i) Hàm `max()` của tác giả chọn nhóm gặp trước khi hòa phiếu. Có 66 câu hòa ở nhóm đầu, trong đó thứ tự mẫu quyết định đúng hay sai ở 37 câu. Xáo thứ tự 8 mẫu 300 lần cho Maj dao động 61,47–62,58 (độ lệch chuẩn 0,20). (ii) Bootstrap trên 8 mẫu (300 lần) cho Maj trung bình 61,18, độ lệch chuẩn 0,39, khoảng 95% là 60,30–61,93. Số 61,5 của paper nằm trong khoảng này; bản chạy lại nằm ở đuôi trên. (iii) Bước `random.choice` khi cả 8 mẫu lỗi xảy ra ở 8 câu, không câu nào có mẫu đúng, nên không ảnh hưởng. (iv) Timeout 60 s so với 10 s không đổi kết quả Maj (vẫn 951). Kết luận nên viết: baseline chạy lại **cao hơn** paper, nên so sánh khó hơn cho Ours chứ không dễ hơn {N2, câu 4}.

#### 4.3 Kết quả chính

Bảng 4.x. EX (%) trên BIRD dev. Baseline chạy lại, cùng bộ chấm (`num_cpus = 4`, `timeout = 60`) {N1}:

| Tập | Số câu | Baseline Gre | **Ours Gre** | Baseline Maj-8 | **Ours@8** | **Ours v9** |
|---|---|---|---|---|---|---|
| Toàn bộ dev | 1.534 | 58,93 | **60,50** | 61,99 | **63,62** | **65,06** |
| Held-out | 1.234 | 58,51 | **59,89** | 61,18 | **63,37** | **64,83** |
| Tuning | 300 | 60,67 | 63,00 | 65,33 | 64,67 | 66,00 |

Nên đặt thêm một bảng nhỏ đối chiếu với các mốc trong Bảng 4 của OmniSQL, ghi rõ là "tham khảo, khác lần chạy": GPT-4o-mini 58,8/61,5; GPT-4o 61,9/64,0; GPT-4-Turbo 62,0/63,6; DeepSeek-V3 63,2/63,8; OmniSQL-7B 63,9/66,1; OmniSQL-32B 64,5/67,0 [14]. Có thể diễn giải như sau. Ở 8 mẫu, Ours@8 (63,62) xấp xỉ GPT-4-Turbo Maj (63,6) của paper. Ở cấu hình đầy đủ, v9 (65,06) cao hơn GPT-4o Maj (64,0) và DeepSeek-V3 Maj (63,8), nhưng vẫn thấp hơn OmniSQL-7B/32B Maj. Tệp {N1} còn so v9 với Llama-3.1-70B (65,1 greedy và 67,4 Maj) và Qwen2.5-72B. Các số này không có trong ghi chú tài liệu; phải đối chiếu lại Bảng 4 của paper trước khi dẫn [CẦN BỔ SUNG].

Tuning có một điểm bất thường cần giải thích chủ động: trên 300 câu này, Ours@8 (64,67) thấp hơn baseline (65,33). Lý do là tập nhỏ. Hai lần lấy 8 mẫu của Ours trên tuning cho 194 và 190 câu đúng, chênh khoảng 1,3 điểm. Tuning chỉ dùng để so các biến thể với nhau. Kết luận dựa trên held-out, tập lớn gấp 4 lần và đã được đăng ký trước {N2, câu 36}.

#### 4.4 So sánh cùng ngân sách: ba tầng

Đây là mục phản biện sẽ hỏi nhiều nhất ("17 ứng viên so với 8 có công bằng không?"). Cấu trúc ba tầng lấy từ {N9}. Quy ước "giữ nguyên tập ứng viên, chỉ đổi cách chọn" có tiền lệ trong CHASE-SQL Table 6 và CSC-SQL [20], [40].

**Tầng 1: cùng 8 mẫu, không thêm lời gọi.** Bỏ phiếu lại trên chính các ứng viên của lần chạy v9. Bộ chấm cục bộ cho set-EX trùng bộ chấm chính thức 998/998 câu {N3}:

| Ours, chỉ 8 mẫu (không greedy, không sửa, không selector) | EX toàn dev | So với Maj-8 (toàn dev): chỉ Ours đúng / chỉ baseline đúng, p | p held-out |
|---|---|---|---|
| 8 mẫu prompt gốc đã làm giàu (**Ours@8**) | **63,62** | 83 / 58, p = 0,043 | **0,012** (68 / 41) |
| 4 mẫu prompt gốc + 4 mẫu prompt kế hoạch | 63,62 | 97 / 72, p = 0,065 | 0,030 |
| 8 mẫu prompt kế hoạch | 62,45 | p = 0,68 | 0,49 |
| Tập con ngẫu nhiên 4 + 4 (30 lần rút) | 63,90 ± 0,35 | — | — |
| Lần lấy mẫu thứ hai: Ours@8 (s1–s8 của lần chạy `v9_noplan`) {N8} | [CHỜ KẾT QUẢ: Ours@8 lần lấy mẫu 2] | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ] |

Số 68/41 trên held-out lấy từ {N9}. Nó khớp với hiệu số đúng trên held-out: (63,37 − 61,18) × 1.234 ≈ 27 câu = 68 − 41. Có hai điểm phải viết rõ. Một, "cùng 8 lời gọi" không có nghĩa là "cùng token": prompt của Ours dài hơn vì có thêm giá trị và 3 ví dụ. Chi phí riêng của Ours@8 chưa được đo tách [CẦN BỔ SUNG: token vào/ra của nhánh `s` trong trace v9]. Hai, như đã nêu ở 3.8, luật bỏ phiếu của Ours@8 ưu tiên ứng viên có giá trị, còn hàm của tác giả vẫn bỏ phiếu cho ứng viên rỗng. Có thể đo riêng ảnh hưởng của khác biệt này mà không tốn API: bỏ phiếu lại 8 mẫu của baseline bằng `vote_groups` của Ours [CẦN BỔ SUNG].

**Tầng 2: 8 mẫu cộng lời gọi có điều kiện, với đối chứng đối xứng.** Áp cùng một bước sửa lỗi cho mọi mẫu lỗi hoặc rỗng trước khi bỏ phiếu, cho cả Ours và baseline. Trên tuning, kết quả không đổi gì: Ours lần A 194 → 194, lần B 190 → 192, baseline 196 → 196 {N6}. Trên cả hai hệ thống, kết quả âm này cho thấy phần hơn của Ours không đến từ việc có thêm bước sửa.

**Tầng 3: khớp ngân sách ứng viên với v9.**

| So sánh | EX toàn dev | EX held-out | Chỉ A đúng / chỉ B đúng, p |
|---|---|---|---|
| Ours v9 (17 ứng viên + selector) | 65,06 | 64,83 | — |
| Baseline Maj-8 (lần 1) | 61,99 | 61,18 | v9 so với: 105 / 58, p = 0,0003 (held-out 87 / 42, p = 0,0001) |
| Baseline Maj-16 (8 mẫu lần 1 + 8 mẫu lần 2) | [CHỜ KẾT QUẢ: baseline Maj-16] | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ: v9 so với Maj-16] |
| Baseline greedy + 16 mẫu (17 ứng viên) | [CHỜ KẾT QUẢ: baseline 17 ứng viên] | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ: v9 so với baseline 17 ứng viên] |
| Ours 16 mẫu (8 + 8), chỉ bỏ phiếu | 64,80 | — | so với Maj-8: 105 / 62, p = 0,001 (held-out p = 0,0001) {N3} |

Cách đọc tầng 3, viết sẵn cho cả hai trường hợp. Nếu v9 vẫn hơn baseline 17 ứng viên có ý nghĩa, câu kết luận là: *"Ở cùng 17 ứng viên, hệ thống đề xuất vẫn hơn baseline X điểm (p = …), nên phần cải thiện đến từ phương pháp chứ không chỉ từ ngân sách."* Nếu khoảng cách thu hẹp mà không còn ý nghĩa, viết: *"Phần lợi thế ở cấu hình đầy đủ chủ yếu đến từ ngân sách mẫu lớn hơn; khẳng định chính của khóa luận là kết quả cùng 8 mẫu."* Tài liệu cho thấy bỏ phiếu bão hòa nhanh trên BIRD. Với Qwen2.5-Coder-32B, EX chỉ tăng từ 67,56 lên 68,54 khi đi từ 8 lên 16 mẫu [40]. Với gpt-4o-mini, OpenSearch-SQL ghi nhận đỉnh ở 7–15 ứng viên [28]. Vì vậy dự đoán hợp lý là baseline 16–17 mẫu chỉ tăng ít so với 61,99. Đây chỉ là dự đoán: không được ghi vào khóa luận như kết quả, và phải thay bằng số thật.

#### 4.5 Kiểm định ý nghĩa và phương sai giữa các lần lấy mẫu

Kiểm định chính được xác định trước là trên **held-out**. Các phân nhóm theo độ khó là phân tích khám phá. Hiệu chỉnh Bonferroni cho 3 kiểm định chính (ngưỡng 0,0167): Ours@8 (p = 0,012) và v9 (p = 0,0001) vẫn đạt {N2, câu 38}. Bảng McNemar chính xác {N1}, {N3}:

| So sánh | Toàn dev (a / b, p) | Held-out | Simple | Moderate | Challenging |
|---|---|---|---|---|---|
| Ours Gre so với Baseline Gre | 96 / 72, p = 0,076 | p = 0,17 | p = 0,33 | p = 0,24 | p = 0,42 |
| Ours@8 so với Baseline Maj-8 | 83 / 58, **p = 0,043** | **p = 0,012** | **p = 0,005** | p = 1,0 | p = 1,0 |
| Ours v9 so với Baseline Maj-8 | 105 / 58, **p = 0,0003** | **p = 0,0001** | **p = 0,0002** | p = 0,27 | p = 1,0 |
| Ours v9 so với Baseline Gre | 142 / 48, p < 0,0001 | — | — | — | — |
| Ours v9 so với Ours v8 | 63 / 36, p = 0,0086 | — | — | — | — |

Trong đó a là số câu chỉ Ours đúng, b là số câu chỉ baseline đúng.

McNemar chỉ xét biến thiên theo câu hỏi, không xét biến thiên do lấy mẫu của mô hình {N2, câu 39}. Hiện đã biết độ lệch chuẩn bootstrap của Maj-8 baseline khoảng 0,39–0,4 điểm, và phạm vi khi xáo thứ tự mẫu là 61,47–62,58 {N4}. Mức chênh 2,2 điểm trên held-out lớn hơn khoảng 5 lần độ lệch chuẩn đó. Bảng phương sai giữa hai lần lấy mẫu, theo thiết kế của `draws_and_budget.py` {N8}:

| Cặp so sánh | Toàn dev | Held-out | Tuning | Ghi chú |
|---|---|---|---|---|
| Baseline Maj-8: lần 1 / lần 2 | 61,99 / [CHỜ KẾT QUẢ: baseline Maj-8 lần lấy mẫu 2] | 61,18 / [CHỜ KẾT QUẢ] | 65,33 / [CHỜ KẾT QUẢ] | lần 2 lưu ở `major_voting_draw2` |
| Ours@8: lần 1 / lần 2 | 63,62 / [CHỜ KẾT QUẢ: Ours@8 lần lấy mẫu 2] | 63,37 / [CHỜ KẾT QUẢ] | 64,67 / [CHỜ KẾT QUẢ] | lần 2 = s1–s8 của `v9_noplan` |
| Ours@8 lần 2 so với Maj-8 lần 2 | [CHỜ KẾT QUẢ: a / b, p] | [CHỜ KẾT QUẢ] | — | cặp cùng lượt |
| Ours@8 lần 1 so với Maj-8 lần 2; lần 2 so với lần 1 | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ] | — | cặp chéo |
| Ours@8 lần 2 so với lần 1; Maj-8 lần 2 so với lần 1 | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ] | — | nhiễu cùng hệ thống |
| Baseline 17 ứng viên so với Maj-8 lần 1 | [CHỜ KẾT QUẢ] | [CHỜ KẾT QUẢ] | — | lợi ích thuần của tăng mẫu |

Nên bổ sung khoảng tin cậy 95% bootstrap ghép cặp cho ΔEX của hai so sánh chính. Có thể tính từ các tệp `*_per_question.json` đã lưu, không tốn API [CẦN BỔ SUNG]. Khi có số của lần 2, viết kết luận theo hai mẫu. Nếu lần 2 vẫn cho Ours@8 hơn Maj-8 có ý nghĩa: *"Kết quả lặp lại qua hai lần lấy mẫu độc lập."* Nếu không: *"Mức hơn dương nhưng không ổn định qua các lần lấy mẫu; cần thêm lần chạy."*

#### 4.6 Theo độ khó

| Độ khó | Số câu | Baseline Gre | Ours Gre | Baseline Maj-8 | Ours@8 | Ours v9 |
|---|---|---|---|---|---|---|
| Simple | 925 | 65,62 | 66,81 | 67,35 | **70,05** | **71,24** |
| Moderate | 464 | 49,78 | 51,72 | 54,96 | 54,96 | 57,11 |
| Challenging | 145 | 45,52 | 48,28 | 50,34 | 50,34 | 51,03 |

Nguồn: {N1}. Diễn giải: cải thiện có ý nghĩa chỉ ở nhóm simple, tức nhóm lỗi "sai giá trị" và "sai số cột" mà truy hồi giá trị và prompt kế hoạch nhắm tới. Ở 8 mẫu, Ours bằng đúng baseline ở moderate và challenging. Với 145 câu challenging, khoảng tin cậy 95% của EX rộng khoảng ±8 điểm (ước lượng xấp xỉ nhị thức với p ≈ 0,5: 1,96·√(0,25/145) ≈ 0,081), nên không thể kỳ vọng đạt ý nghĩa thống kê ở nhóm này.

#### 4.7 Ablation: đóng góp của từng thành phần

Theo kiểu cộng dần của RSL-SQL và MCS-SQL [22], [21]. Tất cả đo trên toàn dev, dựng lại từ cùng lần chạy v9 {N1}:

| Cấu hình | EX | Δ so với dòng trên | Diễn giải |
|---|---|---|---|
| Baseline Maj-8 | 61,99 | — | mốc |
| Ours, 8 mẫu prompt gốc đã làm giàu | 63,62 | +1,63 | tác động gộp của giá trị + few-shot, cùng 8 mẫu |
| Ours, chỉ 8 mẫu prompt kế hoạch | 62,45 | (so với 63,62: −1,17) | dùng một mình thì không hơn |
| 8 gốc + 8 kế hoạch, chỉ bỏ phiếu | 64,80 | +1,18 (so với 63,62) | hai prompt bổ sung cho nhau, nhưng có cả 16 mẫu |
| + greedy + sửa lỗi, chỉ bỏ phiếu | 64,54 | −0,26 | không thay đổi đáng kể |
| + selector khi không có đa số (**v9**) | **65,06** | +0,52 | selector gọi ở 161 câu |
| Ours Gre: chỉ greedy `g` | 58,80 | — | ngữ cảnh làm giàu, không sửa lỗi |
| Ours Gre: greedy + sửa lỗi | 60,50 | +1,70 | sửa lỗi là phần chính của cải thiện greedy |

Cần viết kèm bốn lưu ý. (a) Dòng "+1,18 do đa dạng" có lẫn ảnh hưởng của việc tăng từ 8 lên 16 mẫu. Tách bạch hai yếu tố này cần baseline Maj-16 [CHỜ KẾT QUẢ: baseline Maj-16]. Ở cùng 8 mẫu, trộn 4 + 4 không hơn 8 mẫu prompt gốc (63,62 = 63,62; trung bình 30 lần rút 63,90 ± 0,35). Điều này khớp với CHASE-SQL: trộn bộ sinh nâng trần oracle nhiều hơn nâng kết quả bỏ phiếu [20]. (b) Ablation riêng của giá trị (`v8_novalues`) và few-shot (`v8_nofewshot`) trên tuning chỉ chênh vài câu, nằm trong nhiễu. Hiện mới khẳng định được **tác động gộp** {N1}, {N2, câu 20}. (c) Mức +0,52 của selector chưa có kiểm định riêng. Nên tính McNemar giữa v9 và cấu hình "16 mẫu + greedy + sửa lỗi, chỉ bỏ phiếu" từ dữ liệu đã lưu [CẦN BỔ SUNG]. (d) Ours `g` không sửa lỗi đạt 58,80, **thấp hơn** baseline greedy 58,93. Nghĩa là ở chế độ greedy, ngữ cảnh làm giàu không giúp gì. Lợi ích của ngữ cảnh chỉ thể hiện khi bỏ phiếu (xem 5.1). Đồng thời, phép so Ours Gre với Baseline Gre trộn lẫn ngữ cảnh và sửa lỗi, vì baseline greedy không có bước sửa.

#### 4.8 Kết quả âm (các hướng đã thử nhưng không giúp)

Mọi thí nghiệm dưới đây đo trên tuning, tính theo số câu bỏ phiếu đúng trên 300 câu với 8 mẫu {N2, câu 29}, {N6}:

| Hướng thử | Kết quả | Giải thích |
|---|---|---|
| Thêm mô tả cột/giá trị của BIRD vào DDL (`descriptions_exp.py`, khoảng 0,4 USD) | 192, nằm giữa hai lần rút 190 và 194 | prompt dài hơn, nhiễu hơn |
| Selector listwise/pairwise/tự nhất quán gọi cả khi đã có đa số | sửa được bao nhiêu thì làm hỏng bấy nhiêu | gpt-4o-mini không phân biệt tốt hơn bỏ phiếu; khớp với [20], [21], [40] |
| Đánh trọng số phiếu theo bộ sinh | không tăng | — |
| Sửa mọi mẫu lỗi/rỗng trước khi bỏ phiếu (khoảng 0,83 USD) | Ours 194 → 194 và 190 → 192; baseline 196 → 196; mẫu hỏng giảm 181 → 88; độ chính xác từng mẫu tăng khoảng 1,5 điểm | mẫu lỗi vốn không được bỏ phiếu; bản sửa thường rơi vào phe đa số |
| Quy tắc căn cột | 194 = 194 (thêm sửa lỗi vẫn 194) | SQL vàng của BIRD không nhất quán về cột thừa |
| Pipeline JSON nhiều bước (v6, toàn dev) | 60,04 < 61,99 | ứng viên đồng thuận về SQL sai có hệ thống (3.10) |

Mọi p ≥ 0,5, nên không hướng nào được chạy trên toàn dev {N6}. Báo cáo kết quả âm giúp tránh nghi ngờ "chỉ chọn kết quả đẹp". Đây cũng là những số đo trực tiếp hiếm hoi trên gpt-4o-mini ở N cố định {N9}.

#### 4.9 Phân tích lỗi

Mục này gồm ba tầng. **Tầng 1: lỗi của baseline** (bảng ở 3.2), dùng làm căn cứ thiết kế. **Tầng 2: phân rã lỗi của Ours@8 trên tuning** {N9}, là ước lượng xấp xỉ suy ra từ số đo, nên ghi rõ "xấp xỉ". Khoảng 27 câu (9 điểm) có mẫu đúng nhưng bỏ phiếu chọn sai. Khoảng 27 câu (9 điểm) sai mà cả 8 mẫu đồng thuận. Khoảng 54 câu (18 điểm) sai mà không có mẫu nào đúng và các mẫu không đồng thuận. Có 55 câu không đạt đa số, và ở nhóm này bỏ phiếu chỉ đúng 33%. Độ phủ oracle trên tuning tăng từ 217 lên 227 khi thêm bộ sinh kế hoạch {N1}. Vẽ Hình 4.x minh họa khoảng cách giữa oracle và bỏ phiếu, theo cách CHASE-SQL trình bày 82,79 so với 68,84 [20]. **Tầng 3: lỗi nhãn.** Nhóm "8/8 mẫu đồng thuận mà sai" (9% tuning) nhiều khả năng chứa nhiều lỗi nhãn. Đề xuất: gán nhãn tay khoảng 30 câu theo các loại E1–E4 của Jin et al. (E1 lệch logic câu hỏi–SQL, E2 hiểu sai dữ liệu hoặc lược đồ, E3 tri thức miền sai, E4 mơ hồ) [7], chia thành lỗi nhãn, lỗi mô hình và mơ hồ. Việc này không tốn API, mất khoảng 2–3 giờ {N2, câu 48}, {N9}. Kết quả sẽ là một dòng kiểu "x% câu sai đồng thuận là lỗi nhãn", tương tự con số 10,0% của CHASE-SQL hay 30% của MAC-SQL [20], [18] [CẦN BỔ SUNG].

**Case study** (theo RSL-SQL §VI [22]): chọn từ trace 2 câu Ours sửa được (một câu do giá trị lưu trữ, một câu do selector) và 1 câu Ours làm hỏng. Với mỗi câu, trình bày câu hỏi, evidence, SQL của baseline, SQL của Ours, kết quả, và phân tích nguyên nhân [CẦN BỔ SUNG: chọn từ `results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/`].

#### 4.10 Chi phí và độ trễ

Theo mẫu bảng của RSL-SQL [22]. Chi phí tính theo giá OpenAI cho gpt-4o-mini, trên toàn bộ 1.534 câu {N1}, {N3}, {N5}:

| Hệ thống | SQL ứng viên / câu | Lời gọi API / câu | Token vào / ra | Chi phí | Thời gian / câu | EX |
|---|---|---|---|---|---|---|
| Baseline Gre | 1 | 1 | 3,12 triệu / 0,40 triệu | 0,71 USD | — | 58,93 |
| Baseline Maj-8 | 8 | 1 (n = 8) | 3,12 triệu / 3,24 triệu | 2,41 USD | — | 61,99 |
| Ours v6 | — | 5,31 | [CẦN BỔ SUNG] | 3,74 USD | — | 60,04 |
| Ours v8 | 9 (+1 bản sửa) | 2,13 | [CẦN BỔ SUNG] | 3,29 USD | — | 63,30 |
| Ours@8 (cấu hình con) | 8 | 1 | [CẦN BỔ SUNG] | [CẦN BỔ SUNG] | — | 63,62 |
| **Ours v9** | 17 (+1 bản sửa) | 3,21 | [CẦN BỔ SUNG] | **6,46 USD** | 11,8 s | **65,06** |
| Baseline 17 ứng viên | 17 | 3 | — | [CHỜ KẾT QUẢ] | — | [CHỜ KẾT QUẢ] |

Có thể diễn đạt: v9 tốn gấp 2,7 lần Maj-8 để đổi lấy +3,07 điểm. Ours@8 có số lời gọi bằng Maj-8, chỉ tốn thêm token đầu vào cho giá trị và ví dụ {N2, câu 43}. Nên vẽ biểu đồ EX theo chi phí (Hình 4.x). Không so chi phí với GPT-4o bằng số cụ thể, vì giá của GPT-4o không có trong nguồn đã kiểm tra.

### Chương 5. Thảo luận, hạn chế và hướng phát triển

#### 5.1 Thảo luận: vì sao từng thành phần có tác dụng hoặc không

**Ngữ cảnh giúp bỏ phiếu hơn là giúp từng câu.** Ở greedy, Ours `g` đạt 58,80, không hơn baseline 58,93. Ở 8 mẫu, Ours@8 đạt 63,62 so với 61,99. Giả thuyết: bỏ phiếu chỉ đúng khi đa số mẫu đúng. Giá trị viết đúng chính tả và ví dụ đúng quy ước làm nhiều mẫu cùng hội tụ về một đáp án đúng, nên phe đúng dễ chiếm đa số hơn {N2, câu 27}. Có thể kiểm chứng giả thuyết này mà không gọi API: so phân phối tỷ lệ phiếu của nhóm lớn nhất, và độ chính xác trung bình từng mẫu, giữa Ours@8 và baseline [CẦN BỔ SUNG]. Đây là một nhận định mới đáng nhấn mạnh, vì các bài báo thường chỉ báo kết quả cuối.

**Đa dạng nâng trần oracle, không nâng kết quả bỏ phiếu ở N cố định.** Prompt kế hoạch dùng riêng thì yếu hơn (62,45), nhưng tăng oracle trên tuning thêm 10 câu. Ở 8 mẫu, trộn 4 + 4 không hơn 8 mẫu prompt gốc. Ở 16 mẫu, 8 + 8 đạt 64,80. CHASE-SQL ghi nhận đúng mẫu hình này: self-consistency trên 21 ứng viên của ba bộ sinh đạt 68,84, chỉ nhỉnh hơn self-consistency trong từng bộ sinh (64,4–67,3) [20]. Chen et al. giải thích rằng thêm phiếu từ một nguồn yếu hơn có thể hại câu khó [75]. Sau khi có baseline Maj-16 [CHỜ KẾT QUẢ], mục này sẽ trả lời được phần +1,18 là do đa dạng hay do số mẫu.

**Selector yếu chỉ nên phân xử khi phiếu yếu.** Kết quả "tung đồng xu" trên tuning khớp với tài liệu. Selector chưa tinh chỉnh chỉ đạt khoảng 60–64% độ chính xác nhị phân [20]. Selector trắc nghiệm của MCS-SQL thua bỏ phiếu khi không lọc [21]. CSC-SQL với bộ merge chưa huấn luyện cũng thua bỏ phiếu [40]. DPC làm hỏng 3% số câu mà đa số đúng [42]. Áp cổng (161 câu) cho mức tăng nhỏ nhưng dương: 64,54 lên 65,06. Đây là phát hiện có giá trị thực tiễn: với mô hình nhỏ, thiết kế cổng kích hoạt quan trọng hơn thiết kế prompt cho selector.

**Sửa lỗi giúp greedy, không giúp bỏ phiếu.** Sửa lỗi nâng greedy thêm 1,70 điểm. Áp cho mọi mẫu thì giảm một nửa số mẫu hỏng (181 → 88) nhưng kết quả bỏ phiếu không đổi. Lý do: mẫu lỗi vốn không được bỏ phiếu, và bản sửa thường rơi vào phe đã thắng {N2, câu 30}. Nếu cần độ trễ thấp, hãy chọn cấu hình "greedy + sửa lỗi" (60,50; một lời gọi, cộng một lời gọi sửa khi greedy lỗi hoặc rỗng) {N2, câu 44}.

**Câu khó và trần nhãn.** Các câu moderate và challenging sai chủ yếu ở logic nhiều bước, không phải ở giá trị. Nhóm challenging chỉ có 145 câu. Nhãn ở nhóm câu khó cũng nhiễu nhiều hơn {N2, câu 26}. Với 48/100 câu dev cần sửa nhãn và tương quan hạng chỉ 0,32 sau khi sửa [7], chênh lệch dưới khoảng 2 điểm giữa các phương pháp trên dev gốc không nên được diễn giải như khác biệt thật nếu không có kiểm định ghép cặp.

#### 5.2 Hạn chế (viết thẳng, theo cách DIN-SQL và MAC-SQL viết mục Limitations)

Viết các hạn chế thành từng đoạn ngắn, mỗi đoạn một ý.

Thứ nhất, held-out **không hoàn toàn sạch**. Các bản v6 và v8 đã được chạy và chấm trên toàn bộ dev trước khi có `splits.json`. Quá trình phát triển qua nhiều phiên bản vì vậy vẫn có rủi ro thích nghi theo dev. Tập test của BIRD bị ẩn, còn Mini-Dev là tập con của dev, nên không có tập BIRD nào khác để kiểm tra lại {N2, câu 35}. Lập luận giảm nhẹ: so sánh cùng 8 mẫu dùng giao thức cố định của paper và không có tham số nào chỉnh theo held-out.

Thứ hai, mỗi cấu hình mới **chạy một lần**. Lần lấy mẫu thứ hai đang được chấm [CHỜ KẾT QUẢ].

Thứ ba, **chưa tách được đóng góp riêng** của truy hồi giá trị và few-shot.

Thứ tư, câu moderate và challenging **chưa cải thiện có ý nghĩa**.

Thứ năm, so sánh "cùng 8 mẫu" **không cùng token**, và luật bỏ phiếu khác baseline ở cách xử lý kết quả rỗng (3.8).

Thứ sáu, **chỉ một mô hình** (gpt-4o-mini) và **chỉ một benchmark** (BIRD dev). Các thành phần được thiết kế để không phụ thuộc mô hình, nhưng điều này chưa được kiểm chứng {N2, câu 46}.

Thứ bảy, adapter baseline là **bản tái dựng**. Các tham số API không công bố (`max_tokens`, `top_p`, retry, cách đóng gói message) là giả định triển khai {N4}.

Thứ tám, EX có dương tính giả và âm tính giả [8]. Kết quả tuyệt đối có thể bị ảnh hưởng bởi rò rỉ dữ liệu [78]. Cả hai ảnh hưởng tác động lên hai hệ thống như nhau.

Thứ chín, Ours v9 **tốn gấp 2,7 lần** và chậm khoảng 11,8 giây mỗi câu, vẫn **thua** các mô hình fine-tune chuyên biệt ở chế độ Maj (OmniSQL-7B 66,1, OmniSQL-32B 67,0) [14].

#### 5.3 Hướng phát triển (trong phạm vi BIRD)

Xếp theo mức chắc của bằng chứng và chi phí, rút từ {N9} và {N2}:

| Ưu tiên | Hướng | Lời gọi thêm / câu | Kỳ vọng (suy luận, không phải kết quả) |
|---|---|---|---|
| 0 | Gán nhãn tay khoảng 30 câu sai đồng thuận theo E1–E4 [7] để ước lượng trần | 0 | xác định trần, viết phần hạn chế |
| 1 | Luật gộp phiếu trên mẫu đã lưu: phá hòa theo thời gian thực thi, gộp mềm theo phép chiếu cột | 0 | +0 đến +0,5 |
| 2 | Few-shot trên câu hỏi đã che token lược đồ; ví dụ dạng câu hỏi → CoT → SQL [21], [28] | 0 | +0,5 đến +1 |
| 3 | Đa dạng bên trong prompt mạnh: 4 biến thể few-shot hoặc thứ tự lược đồ × 2 mẫu [65], [21] | 0 | 0 đến +1 |
| 4 | Selector dùng bằng chứng thực thi trên top-2 nhóm, chỉ khi không có đa số, được bỏ phiếu trắng (kiểu DPC [42]) | khoảng 0,2 | +0,3 đến +1 |
| 5 | Đường cong EX theo N = 1, 4, 8, 16 cho cả hai hệ thống | 0 (bỏ phiếu lại) đến thấp | trả lời dứt điểm câu hỏi ngân sách |
| 6 | Phân rã câu hỏi hoặc mô hình mạnh hơn cho bước lập kế hoạch, nhắm vào câu challenging | cao | chưa rõ |
| 7 | Áp các lớp của Ours lên một mô hình mở (ví dụ Qwen2.5-Coder-7B hoặc OmniSQL-7B) trên BIRD dev | GPU | kiểm tra tính độc lập mô hình |
| 8 | Báo cáo thêm trên BIRD `dev_20251106` (bản dev sạch hơn) [12] | như một lần chạy | kiểm tra độ vững trước nhiễu nhãn |

Các mức tăng không cộng tuyến tính, vì hướng 2–3 cùng nhắm vào nhóm "thiếu mẫu đúng", còn hướng 1 và 4 cùng nhắm vào nhóm "chọn sai" {N9}. Không đề xuất thí nghiệm trên Spider hay bộ dữ liệu khác.

### Kết luận của khóa luận (bản nháp, theo yêu cầu "ngắn gọn, không bình luận thêm")

> Khóa luận đã xây dựng một hệ thống text-to-SQL không cần huấn luyện, dùng `gpt-4o-mini-2024-07-18`. Hệ thống bổ sung bốn lớp vào prompt gốc của OmniSQL: truy hồi giá trị lưu trữ, few-shot BM25 từ BIRD train, bộ sinh dạng kế hoạch truy vấn, và bỏ phiếu theo tập kết quả kèm bộ chọn có cổng. Bộ chấm OmniSQL được tái lập đúng 6/6 con số của paper; baseline GPT-4o-mini được dựng lại lệch +0,1 và +0,5 điểm. Trên BIRD dev, ở cùng 8 mẫu, hệ thống nâng EX từ 61,99% lên 63,62%; trên 1.234 câu held-out, từ 61,18% lên 63,37% (p = 0,012). Cấu hình 17 ứng viên đạt 65,06% (p = 0,0003), với chi phí 6,46 USD, gấp 2,7 lần baseline. Cải thiện tập trung ở câu mức simple. Câu moderate và challenging chưa khác biệt có ý nghĩa. Các thí nghiệm âm cho thấy: với gpt-4o-mini, bộ chọn LLM chỉ có ích khi phiếu phân tán; thêm mô tả cột và sửa lỗi mọi mẫu không cải thiện kết quả bỏ phiếu. [CHỜ KẾT QUẢ: câu về độ ổn định qua lần lấy mẫu thứ hai và so sánh với baseline 17 ứng viên.] Hướng tiếp theo là nâng chất lượng từng mẫu ở ngân sách cố định, xây bộ chọn dựa trên bằng chứng thực thi, và kiểm toán nhãn để ước lượng trần EX.

---

## Phần C. Hình, bảng, cách viết nhận định và danh sách kiểm tra trước khi nộp

### Danh mục hình và bảng đề xuất

| Số | Loại | Nội dung | Dữ liệu từ |
|---|---|---|---|
| Hình 1.1 | Đường | EX trên BIRD dev qua các thời kỳ (T5-3B 23,34 → GPT-4 46,35 → MAC-SQL 57,56 → MCS-SQL 63,36 → CHASE-SQL 73,01), đánh dấu vị trí Ours | Bảng 2.x |
| Hình 2.1 | Sơ đồ | Phân loại các hướng: PLM, ICL/phân rã, đa ứng viên + chọn, fine-tune/RL | 2.11 |
| Hình 2.2 | Ví dụ | Một câu BIRD gồm question, evidence (ví dụ "eligible free rate = Free Meal Count / Enrollment"), SQL vàng | `dev.json`, {N1} |
| Hình 3.1 | Sơ đồ | Pipeline Ours v9 | {N1} §5.1 |
| Hình 3.2 | So sánh | Bố cục prompt: gốc, làm giàu, kế hoạch | {N7}, Phụ lục A |
| Hình 3.3 | Lưu đồ | Bỏ phiếu theo tập, cổng τ = 0,5, selector top-3 × 5 mẫu | {N7} |
| Hình 4.1 | Cột | EX theo độ khó: Baseline Maj-8, Ours@8, v9 | 4.6 |
| Hình 4.2 | Cột chồng | Câu bất đồng a/b cho từng so sánh McNemar | 4.5 |
| Hình 4.3 | Phân tán | EX theo chi phí USD: Gre, Maj-8, v6, v8, v9, [baseline 17 ứng viên] | 4.10 |
| Hình 4.4 | Thác nước | Ablation cộng dần 61,99 → 65,06 | 4.7 |
| Hình 4.5 | Histogram | Phân bố Maj-8 khi xáo thứ tự mẫu (61,47–62,58) và khi bootstrap | {N4} |
| Hình 4.6 | Cột | Oracle so với bỏ phiếu trên tuning (217/227 so với khoảng 194) | 4.9 |
| Hình 4.7 | Cột | Lớp lỗi của baseline (236/145/104/74/68) | 3.2 |
| Bảng 2.x | | Phân loại và EX trên BIRD dev | 2.11 |
| Bảng 4.1–4.12 | | Dữ liệu; tham số; tái lập bộ chấm; baseline chạy lại; kết quả chính; McNemar; cùng ngân sách (3 tầng); phương sai giữa các lần lấy mẫu; độ khó; ablation; kết quả âm; chi phí | Chương 4 |

Theo quy định UET và NEU, chú thích bảng đặt trên bảng, chú thích hình đặt dưới hình, đánh số theo chương, và mọi hình, bảng phải được nhắc đến trong văn bản. Hình nên vẽ từ các tệp `*_per_question.json` để số trên hình khớp với số trong bảng.

### Cách diễn đạt nhận định, rút từ cách các bài báo viết

Luôn kèm phạm vi so sánh, theo kiểu Alpha-SQL và CHESS [25], [19]. Câu mẫu cho nhận định chính: *"Với cùng mô hình nền `gpt-4o-mini-2024-07-18` và không fine-tune, ở cùng ngân sách 8 mẫu như giao thức của OmniSQL, hệ thống đề xuất đạt 63,62% EX trên BIRD dev, cao hơn 1,63 điểm phần trăm so với baseline chạy lại (61,99%) và 2,1 điểm so với số công bố (61,5%); trên tập held-out đăng ký trước, chênh lệch có ý nghĩa thống kê (McNemar chính xác, p = 0,012)."* Đặt ngân sách và chi phí ngay cạnh con số, theo kiểu bảng chi phí của RSL-SQL và cách CHESS chia theo ngân sách [22], [19].

Không dùng "state-of-the-art", "vượt trội" hay "tốt nhất" mà không kèm phạm vi. Phạm vi đúng là "trong nhóm không fine-tune, cùng gpt-4o-mini, trên BIRD dev". Khi so với GPT-4o, viết "cao hơn hàng GPT-4o trong Bảng 4 của OmniSQL (tham khảo, khác lần chạy)", theo cách OmniSQL tự gọi mô hình đóng là "a point of reference" [14].

Phân biệt rõ ba loại số: số của paper (1 chữ số thập phân), số chạy lại (2 chữ số), và số tính lại từ cùng một lần chạy (ghi "cấu hình con"). Dùng thống nhất dấu phẩy thập phân kiểu Việt Nam. Dùng "điểm phần trăm" cho chênh lệch tuyệt đối, "%" cho EX.

Mỗi khi báo p-value, kèm (a/b) và tên tập. Nêu rõ kiểm định nào được xác định trước (held-out), kiểm định nào là khám phá (theo độ khó).

Kết quả âm và hạn chế nên viết thẳng, bằng câu khẳng định. Ví dụ: *"Thêm mô tả cột không cải thiện kết quả bỏ phiếu (192/300, nằm giữa hai lần rút 190 và 194)"*. Không viết "có thể chưa phát huy hết tác dụng".

Nêu chủ động ba điểm yếu trước khi bị hỏi: held-out không hoàn toàn sạch; chưa có baseline 17 ứng viên [đang chấm]; câu moderate và challenging chưa cải thiện {N2}.

### Danh sách kiểm tra số liệu trước khi nộp

| # | Điểm cần kiểm tra | Vì sao |
|---|---|---|
| 1 | Phân biệt 58,80 (Ours `g` không sửa lỗi) với 58,8 (baseline paper) và 58,93 (baseline chạy lại) | ba số gần nhau, dễ nhầm |
| 2 | Tổng các lớp lỗi của baseline (627) so với số câu sai (630) | thiếu 3 câu |
| 3 | ~~Khoảng "65,6–67,4"~~ đã sửa trong {N1}: OmniSQL-7B/14B/32B 66,1 / 65,9 / 67,0; Qwen2.5-Coder-14B/32B 66,1 / 67,0; Llama-3.1-70B 67,4 (đối chiếu ảnh bảng kết quả trong `benchmarks/omnisql/official/assets/main_results.png`) | đã xong |
| 4 | Lời gọi trung bình ghi 3,2 hay 3,21; p ghi "< 0,001" hay 0,0003 | thống nhất giữa bảng và văn bản |
| 5 | Ghi rõ luật bỏ phiếu của Ours@8 khác `major_voting()` ở cách xử lý kết quả rỗng | phản biện về công bằng |
| 6 | Số OmniSQL trên bảng xếp hạng (69,23) khác số trong paper (67,0); CHASE-SQL 73,01 (paper) khác 74,90 (bảng xếp hạng) | chỉ dẫn số trong paper |
| 7 | BIRD: abstract ghi 40,08 còn bảng ghi 39,30 cho ChatGPT; tỷ lệ độ khó trong bản HTML ngược với số đếm thực tế | dẫn bảng hoặc số đếm |
| 8 | CHESS "83% fewer calls" (arXiv) khác "93%" (trang workshop) | chọn một nguồn và ghi rõ nguồn |
| 9 | Thay mọi ô [CHỜ KẾT QUẢ] và [CẦN BỔ SUNG] bằng số thật, và cập nhật Tóm tắt cùng Kết luận theo | tránh mâu thuẫn |
| 10 | Mọi tài liệu đánh dấu [chưa xác minh] trong danh mục: kiểm tra trên DBLP, ACL Anthology, IEEE Xplore | tránh trích sai |

### Phụ lục nên có

Phụ lục A chứa toàn văn các prompt tiếng Anh: bố cục `input_seq` của OmniSQL; khối giá trị và khối ví dụ chèn thêm; `PLAN_INSTRUCTIONS`; prompt sửa lỗi; prompt selector. Tất cả lấy nguyên văn từ `ours_v8.py` và `ours_v9.py` {N7}. Như mọi bài báo tham chiếu, prompt đặt ở phụ lục, kể cả prompt của baseline (Alpha-SQL A.4 [25]). Phụ lục B ghi môi trường và hash: commit OmniSQL, revision của tệp prompt, SHA-256 của `dev.zip`, phiên bản Python và SQLite {N3}, {N5}. Phụ lục C là các lệnh chạy lại, theo {N1} §7. Phụ lục D là bảng McNemar đầy đủ cho mọi cặp và mọi tập con, từ `compare_ours.py` và `draws_and_budget.py report` {N8}.

---

## Tài liệu tham khảo

Đánh số theo nhóm chủ đề để dễ tra. Khi đưa vào khóa luận, IEEE yêu cầu đánh số lại **theo thứ tự xuất hiện đầu tiên** trong văn bản. BibTeX với `IEEEtran.bst` làm việc này tự động. Nếu khoa theo quy định UET, đổi sang xếp ABC và nhóm theo ngôn ngữ. Nhãn **[chưa xác minh: …]** đánh dấu chi tiết mà các ghi chú nghiên cứu chưa kiểm chứng được từ nguồn gốc. Phải kiểm tra trước khi nộp, hoặc bỏ chi tiết đó đi. Với bài có hơn 6 tác giả, ghi tác giả đầu kèm "et al.".

**Bộ dữ liệu, độ đo, nhiễu nhãn**

[1] J. Li *et al.*, "Can LLM already serve as a database interface? A BIg bench for large-scale database grounded text-to-SQLs," in *Advances in Neural Information Processing Systems 36 (NeurIPS 2023), Datasets and Benchmarks Track*, 2023, arXiv:2305.03111. [Online]. Available: https://arxiv.org/abs/2305.03111

[2] T. Yu *et al.*, "Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)*, 2018, arXiv:1809.08887. [chưa xác minh: số trang]

[3] R. Zhong, T. Yu, and D. Klein, "Semantic evaluation for text-to-SQL with distilled test suites," in *Proc. EMNLP*, 2020, arXiv:2010.02840. [chưa xác minh: số trang]

[4] F. Lei *et al.*, "Spider 2.0: Evaluating language models on real-world enterprise text-to-SQL workflows," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2025, arXiv:2411.07763.

[5] G. Lee *et al.*, "EHRSQL: A practical text-to-SQL benchmark for electronic health records," in *Advances in Neural Information Processing Systems 35 (NeurIPS 2022), Datasets and Benchmarks Track*, 2022, arXiv:2301.07695.

[6] N. Wretblad, F. G. Riseby, R. Biswas, A. Ahmadi, and O. Holmström, "Understanding the effects of noise in text-to-SQL: An examination of the BIRD-Bench benchmark," in *Proc. 62nd Annu. Meeting Assoc. Comput. Linguistics (Vol. 2: Short Papers)*, 2024, pp. 356–369, doi: 10.18653/v1/2024.acl-short.34.

[7] T. Jin, Y. Choi, Y. Zhu, and D. Kang, "Pervasive annotation errors break text-to-SQL benchmarks and leaderboards," arXiv:2601.08778, 2026; also in *Proc. VLDB Endow.*, vol. 19, p. 931. [chưa xác minh: số issue, trang cuối, DOI của bản PVLDB] [Online]. Available: https://arxiv.org/abs/2601.08778

[8] H. Kim, T. Jeon, S. Choi, S. Choi, and H. Cho, "FLEX: Expert-level false-less execution metric for text-to-SQL benchmark," in *Proc. 2025 Conf. Nations of the Americas Chapter Assoc. Comput. Linguistics (NAACL), Long Papers*, 2025, pp. 4448–4475, arXiv:2409.19014.

[9] BIRD-bench, "BIRD-SQL leaderboard," 2026. [Online]. Available: https://bird-bench.github.io/ (truy cập 21/11/2026)

[10] AlibabaResearch, "DAMO-ConvAI/bird: Official evaluation code (evaluation.py)," GitHub. [Online]. Available: https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird

[11] BIRD-bench, "BIRD Mini-Dev," GitHub. [Online]. Available: https://github.com/bird-bench/mini_dev

[12] BIRD-bench, "bird_sql_dev_20251106," Hugging Face Datasets, Nov. 2025. [Online]. Available: https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106

[13] Arcwise, "BIRD Mini-Dev annotation corrections," GitHub issue #39, AlibabaResearch/DAMO-ConvAI. [Online]. Available: https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39 [chưa xác minh: bài gốc của Arcwise; con số 32,3% hay 36% chưa thống nhất]

**Baseline và các hệ thống text-to-SQL**

[14] H. Li *et al.*, "OmniSQL: Synthesizing high-quality text-to-SQL data at scale," *Proc. VLDB Endow.*, vol. 18, no. 11, 2025, arXiv:2503.02240. [Online]. Available: https://www.vldb.org/pvldb/vol18/p4695-li.pdf [chưa xác minh: trang cuối (trang đầu 4695 theo URL) và DOI]

[15] RUCKBReasoning, "OmniSQL," GitHub, commit a66d732010c89fac4353488d1c59e0b06f92b742. [Online]. Available: https://github.com/RUCKBReasoning/OmniSQL

[16] M. Pourreza and D. Rafiei, "DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction," in *Advances in Neural Information Processing Systems 36 (NeurIPS 2023)*, 2023, arXiv:2304.11015. [chưa xác minh: số trang]

[17] D. Gao *et al.*, "Text-to-SQL empowered by large language models: A benchmark evaluation," *Proc. VLDB Endow.*, vol. 17, no. 5, pp. 1132–1145, 2024, doi: 10.14778/3641204.3641221.

[18] B. Wang *et al.*, "MAC-SQL: A multi-agent collaborative framework for text-to-SQL," in *Proc. 31st Int. Conf. Comput. Linguistics (COLING)*, Abu Dhabi, UAE, 2025, pp. 540–557, arXiv:2312.11242.

[19] S. Talaei, M. Pourreza, Y.-C. Chang, A. Mirhoseini, and A. Saberi, "CHESS: Contextual harnessing for efficient SQL synthesis," arXiv:2405.16755, 2024. [chưa xác minh: venue chính thức; một ghi chú nêu ICML 2025 workshop]

[20] M. Pourreza *et al.*, "CHASE-SQL: Multi-path reasoning and preference optimized candidate selection in text-to-SQL," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2025, arXiv:2410.01943.

[21] D. Lee, C. Park, J. Kim, and H. Park, "MCS-SQL: Leveraging multiple prompts and multiple-choice selection for text-to-SQL generation," in *Proc. 31st Int. Conf. Comput. Linguistics (COLING)*, Abu Dhabi, UAE, 2025, pp. 337–353, arXiv:2405.07467.

[22] Z. Cao, Y. Zheng, Z. Fan, X. Zhang, W. Chen, and X. Bai, "RSL-SQL: Robust schema linking in text-to-SQL generation," arXiv:2411.00073, 2024.

[23] Y. Gao *et al.*, "A preview of XiYan-SQL: A multi-generator ensemble framework for text-to-SQL," arXiv:2411.08599, 2024.

[24] Y. Liu *et al.*, "XiYan-SQL: A novel multi-generator framework for text-to-SQL," arXiv:2507.04701, 2025. [chưa xác minh: venue]

[25] B. Li *et al.*, "Alpha-SQL: Zero-shot text-to-SQL using Monte Carlo tree search," in *Proc. 42nd Int. Conf. Mach. Learn. (ICML)*, PMLR vol. 267, 2025, pp. 36810–36830, arXiv:2502.17248. [chưa xác minh: số thứ tự hội nghị "42nd"]

[26] H. A. Caferoğlu and Ö. Ulusoy, "E-SQL: Direct schema linking via question enrichment in text-to-SQL," arXiv:2409.16751, 2024.

[27] S. Yuan, L. Chen, M. Yuan, and Z. Jin, "MCTS-SQL: Light-weight LLMs can master the text-to-SQL through Monte Carlo tree search," arXiv:2501.16607, 2025. [chưa xác minh: bản AAAI 2026, chỉ dựa trên ghi chú "Accepted AAAI 2026" của arXiv]

[28] X. Xie, G. Xu, L. Zhao, and R. Guo, "OpenSearch-SQL: Enhancing text-to-SQL with dynamic few-shot and consistency alignment," arXiv:2502.14913, 2025. [chưa xác minh: SIGMOD 2025]

[29] K. Maamari, F. Abubaker, D. Jaroslawicz, and A. Mhedhbi, "The death of schema linking? Text-to-SQL in the age of well-reasoned language models," arXiv:2408.07702, 2024.

[30] G. Qu *et al.*, "Before generation, align it! A novel and effective strategy for mitigating hallucinations in text-to-SQL generation," in *Findings Assoc. Comput. Linguistics: ACL 2024*, 2024, arXiv:2405.15307. [chưa xác minh: số trang, danh sách tác giả đầy đủ]

[31] T. Ren *et al.*, "PURPLE: Making a large language model a better SQL writer," in *Proc. IEEE Int. Conf. Data Eng. (ICDE)*, 2024, arXiv:2403.20014. [chưa xác minh: số trang]

[32] B. Li, Y. Luo, C. Chai, G. Li, and N. Tang, "The dawn of natural language to SQL: Are we fully ready?" *Proc. VLDB Endow.*, 2024, doi: 10.14778/3681954.3682003, arXiv:2406.01265. [chưa xác minh: tập, số, trang]

[33] X. Dong *et al.*, "C3: Zero-shot text-to-SQL with ChatGPT," arXiv:2307.07306, 2023.

[34] H. Li *et al.*, "CodeS: Towards building open-source language models for text-to-SQL," *Proc. ACM Manag. Data (SIGMOD 2024)*, 2024, arXiv:2402.16347. [chưa xác minh: tập, số]

[35] B. Hui *et al.*, "Qwen2.5-Coder technical report," arXiv:2409.12186, 2024.

[36] P. Ma, X. Zhuang, C. Xu, X. Jiang, R. Chen, and J. Guo, "SQL-R1: Training natural language to SQL reasoning model by reinforcement learning," arXiv:2504.08600, 2025. [chưa xác minh: bản NeurIPS 2025]

[37] M. Pourreza *et al.*, "Reasoning-SQL: Reinforcement learning with SQL tailored partial rewards for reasoning-enhanced text-to-SQL," arXiv:2503.23157, 2025.

[38] Z. Yao *et al.*, "Arctic-Text2SQL-R1: Simple rewards, strong reasoning in text-to-SQL," arXiv:2505.20315, 2025.

[39] P. Wang *et al.*, "Agentar-Scale-SQL: Advancing text-to-SQL through orchestrated test-time scaling," arXiv:2509.24403, 2025.

[40] "CSC-SQL," arXiv:2505.13271, 2025. [Online]. Available: https://arxiv.org/abs/2505.13271 [chưa xác minh: tác giả, tựa đầy đủ]

[41] "Pi-SQL," arXiv:2506.00912, 2025. [Online]. Available: https://arxiv.org/abs/2506.00912 [chưa xác minh: tác giả, tựa đầy đủ]

[42] "DPC: training-free dual-paradigm consistency selection for text-to-SQL," arXiv:2604.15163, 2026. [Online]. Available: https://arxiv.org/abs/2604.15163 [chưa xác minh: tác giả, tựa chính xác]

[43] J. Guo *et al.*, "Towards complex text-to-SQL in cross-domain database with intermediate representation," in *Proc. 57th Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2019, arXiv:1905.08205.

[44] B. Wang, R. Shin, X. Liu, O. Polozov, and M. Richardson, "RAT-SQL: Relation-aware schema encoding and linking for text-to-SQL parsers," in *Proc. 58th Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2020, arXiv:1911.04942.

[45] T. Scholak, N. Schucher, and D. Bahdanau, "PICARD: Parsing incrementally for constrained auto-regressive decoding from language models," in *Proc. EMNLP*, 2021, arXiv:2109.05093.

[46] H. Li, J. Zhang, C. Li, and H. Chen, "RESDSQL: Decoupling schema linking and skeleton parsing for text-to-SQL," in *Proc. AAAI Conf. Artif. Intell.*, 2023, arXiv:2302.05965.

[47] J. Li *et al.*, "Graphix-T5: Mixing pre-trained transformers with graph-aware layers for text-to-SQL parsing," in *Proc. AAAI Conf. Artif. Intell.*, 2023, arXiv:2301.07507.

[48] X. V. Lin, R. Socher, and C. Xiong, "Bridging textual and tabular data for cross-domain text-to-SQL semantic parsing," in *Findings Assoc. Comput. Linguistics: EMNLP 2020*, 2020, arXiv:2012.12627.

[49] N. Rajkumar, R. Li, and D. Bahdanau, "Evaluating the text-to-SQL capabilities of large language models," arXiv:2204.00498, 2022.

[50] S. Chang and E. Fosler-Lussier, "How to prompt LLMs for text-to-SQL: A study in zero-shot, single-domain, and cross-domain settings," in *NeurIPS 2023 Table Representation Learning Workshop*, 2023, arXiv:2305.11853.

[51] Z. Hong *et al.*, "Next-generation database interfaces: A survey of LLM-based text-to-SQL," *IEEE Trans. Knowl. Data Eng.*, 2025, arXiv:2406.08426. [chưa xác minh: tập, số, trang]

[52] X. Liu *et al.*, "A survey of text-to-SQL in the era of LLMs: Where are we, and where are we going?" *IEEE Trans. Knowl. Data Eng.*, Jul. 2025, arXiv:2408.05109. [chưa xác minh: tập, số, trang]

[53] L. Shi, Z. Tang, N. Zhang, X. Zhang, and Z. Yang, "A survey on employing large language models for text-to-SQL tasks," *ACM Comput. Surv.*, arXiv:2407.15186. [chưa xác minh: tập, số, năm xuất bản]

[54] G. Katsogiannis-Meimarakis and G. Koutrika, "A survey on deep learning approaches for text-to-SQL," *VLDB J.*, vol. 32, pp. 905–936, 2023, doi: 10.1007/s00778-022-00776-8.

**Mô hình ngôn ngữ, suy luận và tính toán lúc suy luận**

[55] T. B. Brown *et al.*, "Language models are few-shot learners," in *Advances in Neural Information Processing Systems 33 (NeurIPS 2020)*, 2020, arXiv:2005.14165.

[56] OpenAI, "GPT-4 technical report," arXiv:2303.08774, 2023.

[57] OpenAI, "GPT-4o mini: Advancing cost-efficient intelligence," Jul. 18, 2024. [Online]. Available: https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/

[58] A. Holtzman, J. Buys, L. Du, M. Forbes, and Y. Choi, "The curious case of neural text degeneration," in *Proc. ICLR*, 2020, arXiv:1904.09751.

[59] J. Wei *et al.*, "Chain-of-thought prompting elicits reasoning in large language models," in *Advances in Neural Information Processing Systems 35 (NeurIPS 2022)*, 2022, arXiv:2201.11903.

[60] T. Kojima, S. S. Gu, M. Reid, Y. Matsuo, and Y. Iwasawa, "Large language models are zero-shot reasoners," in *Advances in Neural Information Processing Systems 35 (NeurIPS 2022)*, 2022, arXiv:2205.11916.

[61] X. Wang *et al.*, "Self-consistency improves chain of thought reasoning in language models," in *Proc. ICLR*, 2023, arXiv:2203.11171.

[62] X. Chen *et al.*, "Universal self-consistency for large language model generation," arXiv:2311.17311, 2023.

[63] F. Shi, D. Fried, M. Ghazvininejad, L. Zettlemoyer, and S. I. Wang, "Natural language to code translation with execution," in *Proc. EMNLP*, 2022, arXiv:2204.11454.

[64] A. Ni *et al.*, "LEVER: Learning to verify language-to-code generation with execution," in *Proc. 40th Int. Conf. Mach. Learn. (ICML)*, 2023, arXiv:2302.08468.

[65] Y. Li *et al.*, "Making large language models better reasoners with step-aware verifier," in *Proc. 61st Annu. Meeting Assoc. Comput. Linguistics (ACL)*, 2023, arXiv:2206.02336. [chưa xác minh: venue, trang]

[66] J. Liu, D. Shen, Y. Zhang, B. Dolan, L. Carin, and W. Chen, "What makes good in-context examples for GPT-3?" in *Proc. DeeLIO 2022 Workshop*, 2022, arXiv:2101.06804. [chưa xác minh: venue]

[67] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," *Found. Trends Inf. Retr.*, vol. 3, no. 4, pp. 333–389, 2009, doi: 10.1561/1500000019. [chưa xác minh]

[68] J. Zobel and A. Moffat, "Inverted files for text search engines," *ACM Comput. Surv.*, vol. 38, no. 2, Art. 6, 2006, doi: 10.1145/1132956.1132959. [chưa xác minh]

[69] C. Wang *et al.*, "Robust text-to-SQL generation with execution-guided decoding," arXiv:1807.03100, 2018.

[70] X. Chen, M. Lin, N. Schärli, and D. Zhou, "Teaching large language models to self-debug," in *Proc. ICLR*, 2024, arXiv:2304.05128.

[71] J. Huang *et al.*, "Large language models cannot self-correct reasoning yet," in *Proc. ICLR*, 2024, arXiv:2310.01798. [chưa xác minh: các tác giả sau tác giả đầu]

[72] B. Brown *et al.*, "Large language monkeys: Scaling inference compute with repeated sampling," arXiv:2407.21787, 2024.

[73] C. Snell, J. Lee, K. Xu, and A. Kumar, "Scaling LLM test-time compute optimally can be more effective than scaling model parameters," arXiv:2408.03314, 2024. [chưa xác minh: bản ICLR 2025]

[74] M. Chen *et al.*, "Evaluating large language models trained on code," arXiv:2107.03374, 2021. [chưa xác minh: công thức pass@k chưa được đối chiếu lại]

[75] L. Chen *et al.*, "Are more LLM calls all you need?" in *Advances in Neural Information Processing Systems 37 (NeurIPS 2024)*, 2024, arXiv:2403.02419. [chưa xác minh: danh sách tác giả, phụ đề]

[76] P. Wang *et al.*, "Large language models are not fair evaluators," arXiv:2305.17926, 2023.

[77] L. Zheng *et al.*, "Judging LLM-as-a-judge with MT-Bench and Chatbot Arena," in *Advances in Neural Information Processing Systems 36 (NeurIPS 2023), Datasets and Benchmarks Track*, 2023, arXiv:2306.05685.

[78] F. Ranaldi *et al.*, "Investigating the impact of data contamination of large language models in text-to-SQL translation," in *Findings Assoc. Comput. Linguistics: ACL 2024*, 2024, pp. 13909–13920, arXiv:2402.08100.

**Thống kê**

[79] Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947, doi: 10.1007/BF02295996. [chưa xác minh]

[80] T. G. Dietterich, "Approximate statistical tests for comparing supervised classification learning algorithms," *Neural Comput.*, vol. 10, no. 7, pp. 1895–1923, 1998, doi: 10.1162/089976698300017197.

[81] R. Dror, G. Baumer, S. Shlomov, and R. Reichart, "The hitchhiker's guide to testing statistical significance in natural language processing," in *Proc. 56th Annu. Meeting Assoc. Comput. Linguistics (ACL), Long Papers*, Melbourne, Australia, 2018, pp. 1383–1392, doi: 10.18653/v1/P18-1128.

[82] P. Koehn, "Statistical significance tests for machine translation evaluation," in *Proc. EMNLP*, 2004. [Online]. Available: https://aclanthology.org/W04-3250/ [chưa xác minh: số trang]

[83] B. Efron and R. J. Tibshirani, *An Introduction to the Bootstrap*. New York, NY, USA: Chapman & Hall, 1993. [chưa xác minh]

[84] S. Holm, "A simple sequentially rejective multiple test procedure," *Scand. J. Statist.*, vol. 6, no. 2, pp. 65–70, 1979. [chưa xác minh]

Các tài liệu sau chỉ có ích nếu khóa luận cần thêm. Gồm: Sainz et al. (Findings of EMNLP 2023) và Golchin & Surdeanu (ICLR 2024, arXiv:2308.08493) về rò rỉ dữ liệu; Berg-Kirkpatrick et al. (EMNLP-CoNLL 2012) về bootstrap trong NLP; Manning, Raghavan & Schütze, *Introduction to Information Retrieval* (CUP 2008) về chỉ mục ngược. Các ghi chú nghiên cứu chưa kiểm chứng chi tiết của các tài liệu này.

---

## Kết luận

Điều rút ra quan trọng nhất từ việc đối chiếu với mười bài báo là ở chỗ khác. Đóng góp đáng bảo vệ của khóa luận không nằm ở con số 65,06%, vốn thấp hơn nhiều hệ thống trên bảng xếp hạng. Nó nằm ở mức kiểm soát thực nghiệm mà các bài báo đó thiếu. Không bài nào trong mười bài kiểm định ý nghĩa thống kê, đo phương sai giữa các lần chạy, hay so với baseline cùng ngân sách. Khóa luận đã làm cả ba ở 8 mẫu, và đang hoàn tất ở 17 ứng viên. Vì vậy cách viết đúng là đặt **kết quả cùng 8 mẫu trên held-out làm khẳng định chính**, còn v9 là cấu hình mở rộng có ghi rõ chi phí. Khi số của lần lấy mẫu thứ hai và baseline 17 ứng viên về, chỉ cần điền vào bảng và chọn một trong hai câu kết luận đã viết sẵn ở 4.4. Cấu trúc lập luận không phải đổi.

Điều thứ hai là một nhận định mà chính số liệu của đề tài cho thấy nhưng chưa được viết thành luận điểm. Lợi ích của ngữ cảnh làm giàu **chỉ xuất hiện khi bỏ phiếu** (greedy 58,80 so với 58,93; 8 mẫu 63,62 so với 61,99). Cùng lúc, sửa lỗi chỉ giúp greedy, và selector chỉ giúp khi phiếu phân tán. Ba quan sát này hợp thành một luận điểm: với mô hình nhỏ, các thành phần của pipeline tác tử tác động lên **sự hội tụ của phân phối ứng viên** chứ không lên độ chính xác của từng câu. Vì vậy cần thiết kế và đánh giá chúng ở tầng bỏ phiếu. Nếu kiểm chứng thêm bằng phân phối tỷ lệ phiếu (không tốn API), luận điểm này có thể thành phần thảo luận có giá trị nhất của Chương 5. Cùng với phân tích nhiễu nhãn, nó cũng giải thích vì sao câu khó chưa cải thiện mà không cần né tránh.
