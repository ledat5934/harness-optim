# Chạy lại MEDIUM với `gpt-6-luna` (Codex qua 9router): kết quả và so sánh với ling

Cùng giao thức MEDIUM như `docs/medium_results.md`: 1 seed, 5 vòng tiến hóa, 50 tác vụ train × 3 lượt, 30 val (chỉ B1 dùng), tập test cố định 100 tác vụ (AppWorld 99). Khác biệt duy nhất là model: `cx/gpt-6-luna` (tài khoản ChatGPT Plus, gọi qua gateway 9router tại `127.0.0.1:20128`) thay cho `inclusionai/ling-3.0-flash` (OpenRouter). Cùng một model đóng cả ba vai: agent, proposer và giám khảo của BrowseComp-Plus.

Số liệu đầy đủ (khoảng tin cậy Wilson 95%, McNemar, token, theo loại tác vụ, diễn biến tiến hóa) nằm trong `results/medium_luna/analysis.md`, tính lại bằng `RESULTS_SUFFIX=luna python3 scripts/analyze_medium.py`.

## 1. Kết quả test

| benchmark | H0 | B1 Meta-Harness | B2 ModularRSI | B3 MemoHarness |
|---|---|---|---|---|
| ALFWorld (100) | 87,0% | 90,0% (+7/−4, p = 0,55) | 90,0% ¹ (+6/−3, p = 0,51) | **94,0%** (+8/−1, **p = 0,039**) |
| AppWorld TGC (99) | 74,7% | **77,8%** (+8/−5, p = 0,58) | 74,7% ¹ (+6/−6, p = 1,0) | 75,8% (+7/−6, p = 1,0) |
| BrowseComp-Plus (100) | 24,0% | **28,0%** (+10/−6, p = 0,45) | 23,0% ¹ (+8/−9, p = 1,0) | 21,0% (+7/−10, p = 0,63) |

¹ B2 không thăng cấp thay đổi nào trên cả ba benchmark (mục 3), nên harness test của nó chính là H0. Chênh lệch giữa B2 và H0 chỉ là nhiễu giữa hai lần chạy cùng một harness: khoảng ±3 điểm.

Chỉ một kết quả khác H0 có ý nghĩa thống kê: B3 trên ALFWorld (thắng 8, thua 1). Các chênh lệch còn lại đều nhỏ hơn biên độ nhiễu ±3–4 điểm đo được qua B2.

**Token trung bình mỗi episode test:**

| benchmark | H0 | B1 | B2 | B3 |
|---|---|---|---|---|
| ALFWorld | 52,5k | 48,9k | 45,0k | 115,2k |
| AppWorld | 85,2k | 98,9k | 87,6k | 139,4k |
| BrowseComp-Plus | 24,3k | 48,8k | 23,4k | 39,3k |

B3 luôn tốn token nhất, vì nó chèn bundle kinh nghiệm vào prompt và gọi thêm bước thích nghi theo từng ca. Chi phí tính bằng tiền là $0, vì mọi lệnh gọi đều nằm trong gói ChatGPT Plus. Toàn bộ lần chạy dùng khoảng 1/5 quota tuần của Codex, và quota tuần ở mức 48% khi kết thúc. Thời gian chạy khoảng 11 giờ, trong đó khoảng 3 giờ là chờ cửa sổ quota 5 giờ được đặt lại; các tiến trình tự chờ lỗi 429 rồi chạy tiếp.

**AppWorld chi tiết:**

| | H0 | B1 | B2 | B3 |
|---|---|---|---|---|
| TGC | 74,7% | **77,8%** | 74,7% | 75,8% |
| SGC (33 scenario) | 63,6% | **66,7%** | 57,6% | 63,6% |
| tỉ lệ unit test đạt trung bình | 89,2% | **90,5%** | 89,4% | 88,1% |

**BrowseComp-Plus:** luna chỉ gọi `search` khoảng 4 lần mỗi câu (B1 khoảng 5,5 lần), và `get_document` dưới 0,5 lần. Không có câu nào bỏ trống đáp án. Nhưng nhiều câu kết thúc bằng một đáp án kiểu "không xác định được", sau khoảng 5 bước.

## 2. So sánh với ling (`docs/medium_results.md`)

| benchmark | H0 ling → luna | B1 ling → luna | B2 ling → luna | B3 ling → luna |
|---|---|---|---|---|
| ALFWorld | 73 → 87 | 86 → 90 | 60 → 90 | 65 → 94 |
| AppWorld TGC | 6,1 → 74,7 | 6,1 → 77,8 | 2,0 → 74,7 | 8,1 → 75,8 |
| BrowseComp-Plus | 17 → 24 | 21 → 28 | 23 → 23 | 18 → 21 |

- **Model mạnh hơn nâng mặt bằng nhiều hơn mọi baseline.** Chỉ riêng việc đổi model đã đưa H0 từ 6% lên 75% trên AppWorld và từ 73% lên 87% trên ALFWorld. Mức tăng do tiến hóa harness với luna chỉ khoảng 0–7 điểm.
- **Với ling, harness kém có thể kéo kết quả xuống dưới H0.** B2 ALFWorld giảm 13 điểm, B3 ALFWorld giảm 8 điểm. Với luna thì không baseline nào làm hại có ý nghĩa: model đủ mạnh để bỏ qua hướng dẫn thừa.
- **Thứ hạng thay đổi theo model.**
  - ALFWorld: ling xếp B1 nhất; luna xếp B3 nhất, B1 và B2 hòa nhau.
  - BrowseComp-Plus: ling xếp B2 nhất; luna xếp B1 nhất và B3 cuối.
  - Không baseline nào thắng ổn định trên cả hai model.
- **Lượng token khác hẳn trên BrowseComp-Plus:** ling khoảng 500k mỗi câu với khoảng 20 lần search, luna khoảng 24k với khoảng 4 lần search. Ling tìm kiếm dai dẳng hơn nhiều; luna dừng sớm và trả lời "không xác định được".

## 3. Diễn biến tiến hóa và nhận xét từng baseline

### B1 Meta-Harness

Tìm được bản tốt hơn H0 trên val ở cả ba benchmark, và bản đó cũng cao nhất hoặc gần cao nhất trên test:

- **ALFWorld:** vòng 2 thắng (val 80%) với gợi ý lấy và đặt từng vật một cho tác vụ cần nhiều vật. Loại "two obj" đạt 13/13 (H0 10/13).
- **AppWorld:** vòng 1 thắng (val 73,3%) với hướng dẫn chung: xác định yêu cầu, hành động theo bằng chứng quan sát được, kiểm tra hậu điều kiện trước khi gọi `complete_task`.
- **BrowseComp-Plus:** vòng 2 ưu tiên đọc toàn văn tài liệu (val 26,7%). Vòng 3 **từ chối đáp án "bỏ cuộc" khi còn bước** và buộc agent tìm tiếp (val 30%). Thay đổi này nhắm đúng điểm yếu lớn nhất của luna; số lần search tăng từ 4,1 lên 5,5 và độ chính xác test đạt 28%.

Điểm yếu vẫn như với ling: val chỉ 30 tác vụ nên nhiễu. Ví dụ AppWorld vòng 5 rơi xuống 60% mà không rõ do thay đổi hay do ngẫu nhiên. Các bản thắng đều là những thay đổi nhỏ, dạng thêm câu hướng dẫn.

### B2 ModularRSI

**Không có đề xuất nào được mở trong cả 15 vòng** (3 benchmark × 5 vòng), nên harness cuối là H0. Nguyên nhân nằm ở bước điều tra "module nào là thủ phạm": với mỗi tác vụ thất bại, model phải chỉ ra rằng sửa một module cụ thể sẽ biến lần fail thành pass. Luna gần như luôn trả lời "không":

| benchmark | finding | là thủ phạm (luna) | thủ phạm và sửa được ngay (luna) | thủ phạm và sửa được ngay (ling) |
|---|---|---|---|---|
| ALFWorld | 85 | 2 | 1 (bị chuyển sang module khác) | 9 / 145 |
| AppWorld | 160 | 1 | 1 | 31 / 245 |
| BrowseComp-Plus | 215 | 0 | 0 | 25 / 245 |

Các ghi chú của luna đều có dạng: "Chỉ có lượt thất bại, không có lượt thành công để đối chiếu, nên không xác định được điểm phân kỳ; thay đổi module này sẽ không giúp tìm ra đáp án." Luna từ chối ngay cả trường hợp agent bỏ cuộc sớm trên BrowseComp-Plus, dù đó chính là điểm B1 sửa thành công.

Đây không phải lỗi mã: cổng kiểm soát nhiều tầng của ModularRSI làm đúng thiết kế. Nhưng nó cho thấy B2 rất nhạy với mức độ "dễ dãi" của model điều tra. Ling dễ dãi nên B2 đề xuất nhiều và gây hại trên ALFWorld; luna khắt khe nên B2 đứng yên. Tôi giữ nguyên prompt gốc, không nới tiêu chí.

### B3 MemoHarness

Controller viết lại bundle ở mọi vòng, và canary gần như luôn cho qua. Ngoại lệ là AppWorld vòng 4 và 5, bị từ chối vì reward giảm 0,5. Bundle được chọn theo điểm train:

- **ALFWorld:** vòng 4 (train 90%) với chiến lược tìm theo vị trí khả dĩ, ghi nhớ chỗ đã tìm, xác nhận bước chuẩn bị (làm nóng, làm lạnh, rửa) trước khi đặt vật. Kết quả test 94%, thắng H0 có ý nghĩa thống kê. Đây là kết quả tốt nhất của cả lần chạy.
- **AppWorld:** vòng 2 (train 83,3%) với hướng dẫn trích yêu cầu chính xác, duyệt hết các trang kết quả, kiểm tra trạng thái cuối. Test 75,8%, gần bằng H0.
- **BrowseComp-Plus:** vòng 2 (train 26,7%, trên 30 tác vụ train) với chiến lược tách bước xác định ứng viên và bước kiểm chứng. Test chỉ 21%, thấp hơn H0. Train 30 tác vụ với tỉ lệ đúng thấp quá nhiễu để chọn đúng bundle.

Nhược điểm: tốn token nhất, gấp khoảng 1,6–2,2 lần H0.

### Nhận xét chung

1. Với một model mạnh, mức tăng do tiến hóa harness nhỏ so với nhiễu. Chỉ 1/9 so sánh với H0 có ý nghĩa thống kê. Muốn phân biệt các baseline cần nhiều seed hoặc tập test lớn hơn.
2. Baseline nào thắng phụ thuộc vào model. Báo cáo chỉ với một model dễ dẫn đến kết luận sai.
3. B1 (sửa mã tự do, chọn trên val) ổn định nhất qua cả hai model: luôn ở top 2 và không bao giờ làm hại có ý nghĩa.

## 4. Lỗi phát hiện và đã sửa trong lần chạy này

| # | lỗi | ảnh hưởng | sửa |
|---|---|---|---|
| 1 | `llm.py` gửi `reasoning.enabled` và `tool_choice` lồng theo kiểu OpenRouter tới gateway OpenAI-compatible | HTTP 400; ép gọi tool bị bỏ qua | dùng `reasoning_effort` và `tool_choice` phẳng khi base URL không phải OpenRouter (`96edb85`) |
| 2 | gọi `/generation` để tra giá trên gateway | thêm khoảng 5 giây mỗi lệnh gọi | gateway không tính giá: chi phí 0, không tra cứu |
| 3 | lỗi 429 dạng "reset after 1m 48s" không được phân tích | chờ mặc định 300 giây hoặc thất bại sau 5 lần thử | đọc thời gian reset và ngủ đúng khoảng đó, không tính vào số lần thử (`15ca649`) |
| 4 | B1 `extract_json` lấy nhầm một dict `config_schema` trong code của câu trả lời phân tích | 3/5 vòng B1 BrowseComp-Plus mất phần phân tích | `extract_json(..., key="candidates")`; chạy lại B1 BrowseComp-Plus từ đầu (bản dở lưu ở `results/medium_luna/aborted_jsonparse/`) |
| 5 | B1 gate không bắt được file `.py` không đăng ký variant nào | thay đổi "chết" vẫn được đánh giá | đánh dấu "registers no variant" |
| 6 | B2 cho phép ghi đè tên variant đã có | variant cũ bị thay thế âm thầm | regex loại tên đã tồn tại |
| 7 | **ALFWorld rò đĩa:** textworld/fast_downward chép một bản `libdownward.so` (32 MB) cho mỗi env và không bao giờ giải phóng; file đã xóa vẫn chiếm đĩa đến khi process thoát | 82 episode test lỗi ENOSPC (B1 28, B2 8, B3 46), kết quả ban đầu 66/83/52% | tái sử dụng các bản thư viện qua pool trong `benchmarks/alfworld/adapter.py` (`dlclose` gây segfault khi nạp lại cùng game); chạy lại đúng các episode lỗi bằng `scripts/redo_test_errors.py` với harness cuối đã đóng băng (`06032ff`) |
| 8 | B3 `bank.save("bank.json")` ghi pickle rồi ghi đè bằng JSON vào cùng file | không nạp lại được experience bank | lưu `bank.pkl` và `bank.json`; thêm `BM25ExperienceBank.from_snapshot` (dựng lại khớp hoàn toàn với bản gốc) |
| 9 | `analyze_medium.py` cố định tên model ling và đọc `spend.json` của ling | báo cáo luna ghi sai model và sai chi phí proposer | hỗ trợ `RESULTS_SUFFIX` |

Lỗi 7 không xảy ra trong lần chạy ling (không có episode lỗi ENOSPC), nên `docs/medium_results.md` không bị ảnh hưởng. Sau khi chạy lại, không còn episode lỗi hạ tầng nào trong `results/medium_luna/`.

Tiến trình B3 AppWorld treo ở bước thoát sau khi đã ghi xong kết quả (chỉ còn 1 luồng, chiếm CPU), nên phải kill thủ công. Vì vậy `/root/bench/luna_appworld.out` ghi "FAILED b3", nhưng kết quả trong `baseline_runs.jsonl` đã đầy đủ. Tôi chưa tìm ra nguyên nhân; nhiều khả năng do phần dọn dẹp server AppWorld.

Ghi chú nhỏ, chưa sửa vì không ảnh hưởng: `baselines/b3_memo.py` vẫn ghi `MODEL = "inclusionai/ling-3.0-flash"`, nhưng `ChatShim` bỏ qua tham số model nên mọi lệnh gọi đều đi tới model cấu hình trong `.env`.

## 5. Dữ liệu

- `results/medium_luna/*.jsonl`: bản ghi từng episode (H0 train/val/test; B1/B2/B3 tiến hóa và test).
- `results/medium_luna/baseline_runs.jsonl`: dòng tóm tắt mỗi baseline. Với ALFWorld, dòng cuối là sau khi chạy lại các episode lỗi (`redo_test_errors`).
- `results/medium_luna/runs/<method>/<bench>/`: workspace tiến hóa (log, candidate, bundle, bank).
- `results/medium_luna/logs/`: log từng tiến trình, gồm cả `alfworld_<method>_redo.log`.
- Trajectory và thư mục `runs/` lớn không được commit (gitignore), giống lần chạy ling.

## 6. B4 – repertoire cơ chế có cổng kiểm định (ý tưởng v2, `baselines/b4_repertoire.py`)

Cùng model luna, cùng protocol medium (5 vòng, 50 train × 3 roll của H0, 30 val, 100/99 task test), cùng bản ghi H0 dùng chung.
B4 thêm các cơ chế khai báo `precondition -> action` (guidance / inject / annotate_obs / reject_finish) vào vòng ReAct của H0;
mỗi vòng: gắn nhãn failure mode từ tín hiệu hành vi → blind/hindsight report → đề xuất 2 nhánh (structural + guidance)
→ cổng khái quát hóa (lint) → sàng lọc từng ứng viên trên 10 task mục tiêu + 6 task "an toàn" (ghép cặp với H0)
→ gộp R³ và kiểm định trên val. Thiết kế: `docs/idea_v2.md`.

| Benchmark (test) | H0 | B1 | B2 | B3 | **B4** | B4 vs H0 (thắng/thua, sign test) | B4 vs B1 |
|---|---|---|---|---|---|---|---|
| BrowseComp-Plus acc (100) | 24 | 28 | 23 | 21 | **33** | +13/−4, p = 0,05 | +11/−6, p = 0,33 |
| AppWorld TGC (99) | 74,7 | **77,8** | 74,7 | 75,8 | 71,7 | +4/−7, p = 0,55 | +5/−11, p = 0,21 |

Chi phí: luna qua 9router miễn phí ($0). B4 dùng nhiều episode hơn B1 (BCP 410, AppWorld 469 episode tiến hóa + test),
vì mỗi ứng viên được sàng lọc riêng trên 16 task train.

**BrowseComp-Plus.** Bộ cuối {m1, m2} được chọn ngay vòng 1 (val 0,13 → 0,43). m1 là `reject_finish` khi câu trả lời
mang tính "không xác định được" mà vẫn còn bước (kích hoạt ở 70/100 task test); m2 là guidance về chiến lược tìm kiếm.
Đây đúng là failure mode chính của H0 trên luna (75% câu trả lời bị hedge, không câu hedge nào đúng). Vòng 2–5 đều nhắm
"early_stop"; vài ứng viên qua sàng lọc nhưng không cải thiện val nên không được gộp. Đây là kết quả tốt nhất trên BCP
và là cải thiện duy nhất so với H0 có ý nghĩa thống kê (p = 0,05).

**AppWorld.** Bộ cuối {m1 annotate_obs khi observation dài, m2 guidance kiểm tra đầy đủ trước khi kết thúc,
m6 guidance dùng ít tool call nhất}. Val tăng 0,70 → 0,80 → 0,833 nhưng test giảm 3 điểm so với H0 (không có ý nghĩa thống kê).
Phân tích pool (`runs/b4/appworld/pool.json`):
- Cổng "không gây hại" quá lỏng: m2 được nhận dù dS = −0,167 trên task an toàn (ngưỡng hiện tại cho phép tổng −1 trên 6 task);
  m7, m10 cũng có dS âm. Trên AppWorld H0 đã giải 75%, nên tác hại lên task dễ quan trọng hơn lợi ích trên task khó.
- Val 30 task quá nhỏ cho chênh lệch 1–4 task; chọn theo `C.better` (chỉ cần lớn hơn) nên dễ overfit val.
  Đây cũng là vấn đề chung của B1–B3 (đã ghi ở mục trên), nhưng B4 gộp tới 3 cơ chế.
- Hai guidance m2, m6 kích hoạt ở mọi task (precondition True), tức là thay đổi toàn cục, đúng loại thay đổi mà
  ý tưởng v2 khuyên hạn chế.

**Đề xuất sửa (khái quát, chưa chạy lại):** (1) cổng an toàn chặt hơn: loại ứng viên nếu dS < 0 (hoặc LCB của dS < 0),
nhất là với guidance; (2) chỉ gộp khi val tăng ≥ 2 task hoặc LCB ghép cặp > 0, thay cho "lớn hơn"; (3) với benchmark mà H0
đã mạnh, ưu tiên cơ chế có precondition hẹp thay cho guidance toàn cục; (4) tăng số task an toàn khi sàng lọc.

**Lỗi pipeline phát hiện khi chạy debug** (đã sửa): `Recorder.note()` trùng tham số `kind` khi log cơ chế kích hoạt
(đổi thành `mkind`); container khởi động lại làm mất pyserini/pyjnius và appworld (cài lại; adapter BCP tìm fatjar
cả trong `dist-packages`; AppWorld chạy bằng venv Python 3.12 vì SQLAlchemy cũ không build trên Python 3.13);
chế độ `--debug` giờ chỉ chạy 1 vòng. Calibration: blind confidence của luna không phân biệt được run đúng/sai
(BCP: 0,35 với run đúng, 0,43 với run sai) nên chỉ được ghi lại, không dùng làm tín hiệu chọn.

## 7. B4 v2 – cổng chặt hơn (chạy lại cả hai benchmark)

Thay đổi so với v1 (đều là nguyên tắc chung, `baselines/b4_repertoire.py`):
1. **Ngân sách gây hại theo phạm vi tác động:** cơ chế luôn bật (guidance hoặc precondition `True`) không được làm hỏng
   task an toàn nào; cơ chế có điều kiện được phép hỏng tối đa 1 (nhiễu). Số task an toàn khi sàng lọc 6 → 10.
2. **Gộp theo biên ghép cặp trên val:** số task thắng − số task thua so với bộ hiện tại ≥ 2, thay cho "val cao hơn".
3. Proposer được dặn ưu tiên precondition hẹp; guidance chỉ dùng cho lời khuyên không viết được thành điều kiện.

Kết quả v1 giữ ở `results/medium_luna/b4v1_*.jsonl`, `runs/b4v1/`; v2 ở `b4_*.jsonl`, `runs/b4/`.

| Test (luna) | H0 | B1 | B2 | B3 | B4 v1 | **B4 v2** | v2 vs H0 | v2 vs B1 | v2 vs v1 |
|---|---|---|---|---|---|---|---|---|---|
| BrowseComp-Plus acc (100) | 24 | 28 | 23 | 21 | **33** | 28 | +9/−5, p = 0,42 | +7/−7 | +6/−11, p = 0,33 |
| AppWorld TGC (99) | 74,7 | 77,8 | 74,7 | 75,8 | 71,7 | **78,8** | +9/−5, p = 0,42 | +6/−5 | +12/−5, p = 0,14 |

- **AppWorld:** bộ cuối chỉ còn **một** cơ chế có điều kiện: m3 `inject` khi `n_errors >= 3 and steps_left > 1`
  (nhắc dùng chi tiết lỗi để sửa cách làm và tiếp tục; kích hoạt ở 87/99 task test). Các guidance luôn bật bị cổng mới
  loại vì làm hỏng task H0 luôn giải (m4) hoặc không thắng đủ trên val. Test từ 71,7 (v1) lên 78,8, cao nhất trong
  các phương pháp, và không còn bị overfit val (val 0,767 ≈ test 0,788).
- **BrowseComp-Plus:** cả v1 và v2 đều chọn {reject_finish khi trả lời hedge, guidance tìm kiếm} ở vòng 1 và không gộp
  thêm gì; v2 đạt 28 thay vì 33. Cổng mới không ảnh hưởng vòng 1 (cả hai đều qua), nên chênh lệch đến từ cách proposer
  diễn đạt cơ chế và nhiễu (+6/−11, p = 0,33).
- Không có khác biệt nào có ý nghĩa thống kê ở mức 0,05 với 100 task; B4 v2 là phương pháp duy nhất không thua H0 trên
  cả hai benchmark và đứng đầu/ngang đầu ở cả hai.

**Nhận xét về ý tưởng.** (1) Cơ chế có điều kiện hẹp tổng quát tốt hơn guidance toàn cục: lợi ích nằm ở các episode mà
precondition đúng, còn các episode khác gần như không bị đụng tới. (2) Với model mạnh trên benchmark mà H0 đã cao, rủi ro
chính là làm hỏng task dễ, nên ngân sách gây hại phải phụ thuộc phạm vi kích hoạt. (3) Val 30 task là nút thắt: biến
động giữa hai lần chạy cùng cấu hình (BCP 33 vs 28) cỡ bằng hiệu ứng cần đo; muốn kết luận chắc cần nhiều seed hoặc val lớn hơn.

## 8. B4 v3 (sàng lọc cận biên, đóng băng mode, dừng sớm, chọn lại 2 lượt val)

| | BCP acc | AppWorld TGC |
|---|---|---|
| H0 | 24 | 74.7 |
| B1 | 28 | 77.8 |
| B4 v1 | 33 | 71.7 |
| B4 v2 | 28 | 78.8 |
| **B4 v3** | **29** | **80.8** |

- Ghép cặp trên test, v3 so với H0: AppWorld 8 thắng / 2 thua (sign test p = 0.11); BCP 12/7 (p = 0.36). So với v2: AppWorld 7/5, BCP 7/6.
- Bộ cuối mỗi benchmark là 1 cơ chế có điều kiện:
  - AppWorld: `inject` khi `n_errors >= 1 and err_streak == 0 and step_frac < 0.5 and steps_left > 2`, tức là gợi ý khôi phục lỗi khi còn nhiều ngân sách. Cơ chế kích hoạt trên 99/99 task test.
  - BCP: `reject_finish` khi câu trả lời né tránh, đã search ít nhất 3 lần và còn bước. Kích hoạt trên 66/100 task.
- Dừng sớm: BCP dừng sau vòng 3, AppWorld sau vòng 4. Chi phí ngoài test: BCP 268 episode (v2: 290). AppWorld 390 episode (v2: 320) do phải chạy lại bộ mới trên train để làm mốc so sánh và chạy val lượt 2.
- Chọn lại cuối: ở cả hai benchmark, bộ hai cơ chế không vượt được bộ một cơ chế qua hai lượt val (AppWorld −2, BCP +1), nên bộ một cơ chế được giữ.
- So sánh kích hoạt / không kích hoạt bị lệch do chọn mẫu: m1 trên BCP chỉ kích hoạt ở task khó (8/66 đúng so với 21/34). Chỉ số này cần được so với H0 trên cùng task trước khi dùng làm bằng chứng.
- Hạn chế: mỗi phiên bản mới chạy 1 seed, và chưa có kết quả nào đạt mức có ý nghĩa thống kê.
