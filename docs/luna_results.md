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

## 9. B4 v3, 2 seed (thêm `MIN_ROUNDS = 3`)

Lần chạy seed 1 đầu tiên (`b4s1a_*`) dừng sau vòng 2 mà không gộp được cơ chế nào, nên test chỉ là H0 chạy lại: BCP 26, AppWorld 77,8. Lần này cho thấy chạy lại H0 đã lệch 2–3 điểm chỉ do nhiễu. Đã thêm luật phải chạy ít nhất 3 vòng mới được dừng sớm, rồi chạy lại seed 1.

| | H0 | seed 0 | seed 1 | Thắng/thua so với H0, gộp 2 seed |
|---|---|---|---|---|
| BCP | 24 | 29 | 28 | 22 / 13 (p = 0,18) |
| AppWorld TGC | 74,7 | 80,8 | 81,8 | 17 / 4 (p = 0,007) |

- Hai seed độc lập tìm ra **cùng loại cơ chế**:
  - AppWorld: `inject` khi đã có nhiều lỗi tool (gợi ý khôi phục, kiểm tra việc còn lại).
  - BCP: `reject_finish` khi câu trả lời né tránh mà vẫn còn bước.
  Precondition khác nhau về ngưỡng nhưng cùng nguyên tắc. Đây là bằng chứng cơ chế tìm được tổng quát, không phải may rủi.
- So với H0 trên chính các task có cơ chế kích hoạt (seed 1): AppWorld 7 thắng / 1 thua trên 80 task, BCP 4 thắng / 2 thua trên 65 task. Phép so kích hoạt / không kích hoạt thô cho kết quả ngược (BCP 4/65 so với 24/35), vì cơ chế chủ yếu kích hoạt trên task khó.
- Lưu ý về p-value: hai seed dùng chung kết quả H0 trên test nên không hoàn toàn độc lập.

## 10. B4 v3 so với B1, mỗi bên 2 seed

| | H0 | B1 (seed 0 / 1) | B4 v3 (seed 0 / 1) | B4 so với B1, ghép theo seed (thắng/thua) |
|---|---|---|---|---|
| AppWorld TGC | 74,7 | 77,8 / 77,8 | 80,8 / 81,8 | 13 / 6 (p = 0,17) |
| BCP | 24 | 28 / 19 | 29 / 28 | 20 / 10 (p = 0,10) |
| Gộp 2 benchmark | | | | 33 / 16 (p = 0,02) |

- B4 cao hơn B1 trên cả 4 cặp (benchmark × seed). Riêng từng benchmark thì chưa có ý nghĩa thống kê, nhưng gộp lại có (p = 0,02).
- B4 ổn định hơn: trên BCP, B1 dao động 28 → 19 giữa hai seed, còn B4 chỉ 29 → 28.

## 11. Ablation v3 vs v4 (mode do LLM tìm + graph), BCP, seed 0

Chạy lại cả hai cấu hình cùng seed, cùng H0 luna (`scripts/run_b4_cmp.py`, tag `b4v3cmp` / `b4v4cmp`).

| cấu hình | mode được chọn | bộ cuối | val | test |
|---|---|---|---|---|
| H0 | – | – | – | 24% |
| v3 (`B4_LLM_MODES=0`) | `early_stop` (luật) | m3: `reject_finish` khi `is_finish and answer_hedged and n('search') >= 3 and steps_left > 1` | 0.267 | 24% |
| v4 (`B4_LLM_MODES=1`) | `weak_search_abandonment` (LLM gom cụm) | m2: `guidance` luôn bật, "đổi manh mối khi kết quả lặp/không liên quan" | 0.200 | 23% |

Ghép cặp trên 100 task test: v4 vs H0 7W/8L, v3 vs H0 8W/8L, v4 vs v3 8W/9L (sign test p=1.0 cả ba).

**Nhận xét**
- Không cấu hình nào hơn H0 ở lần chạy này. Lần chạy v3 seed 0 trước (§8) đạt 29% với một cơ chế cùng loại; chênh lệch giữa hai lần chạy cùng cấu hình (24% vs 29%) lớn hơn chênh lệch v3/v4, nên trên BCP kết quả 1 seed không đủ để so v3 với v4.
- Mode do LLM tìm ra cụ thể và dễ hiểu hơn (`weak_search_abandonment` 9 run, `unsupported_candidate_commitment` 5 run, mode sau được đánh dấu không sửa được bằng harness), nhưng proposer v4 vẫn đề xuất cùng loại cơ chế như v3. Ứng viên `inject` của v4 vòng 1 không kích hoạt lần nào (precondition quá hẹp) → cần P3 (precondition hai tầng).
- Val 30 task không phân biệt được: m2 vào bộ với dT=+0.067 trên sàng lọc nhưng test không đổi.
- Việc cần làm tiếp: chạy thêm seed (≥2) cho cả hai, và chạy AppWorld, trước khi kết luận về P1/P2.

## 12. B4 v5 (precondition hai tầng, kiểm tra trước bằng replay, tính điểm trên task có kích hoạt), BCP, 2 seed

**Thay đổi so với v4** (nhánh `claude-2/b4-v4-improve`; tắt bằng `B4_V5=0 B4_LLM_CHECK=0`):
- **Precondition hai tầng (idea_v3 P3):** cơ chế có thể kèm `llm_check`, một câu hỏi yes/no chỉ được hỏi khi tầng tín hiệu đúng, tối đa 3 lần mỗi episode.
- **Kiểm tra trước bằng replay:** trước khi sàng lọc, precondition được chạy lại trên trajectory đã lưu của harness hiện tại.
  - Đếm số run thất bại mục tiêu và số run thành công mà nó sẽ kích hoạt.
  - Nếu dự đoán là 0, proposer được sửa 1 lần. Vẫn 0 thì loại, không tốn episode.
- **Tính điểm chỉ trên task có kích hoạt:** cơ chế có cổng không đổi gì cho tới khi kích hoạt. Vì vậy dT/dS khi sàng lọc và margin khi gộp trên val chỉ tính trên task mà cơ chế kích hoạt; task không kích hoạt chỉ là nhiễu.

**Thiết lập**
- H0 mới cho train/val (`results/medium_luna5`, cùng `h0_hash` `7afc5eefa6e3`): train 19,3%, val 26,7%.
- H0 test lấy lại từ `medium_luna` (24%).
- Bốn run song song qua `scripts/run_b4_cmp.py`, mỗi run 1 tag:
  - v4: `b4v4c` (seed 0), `b4v4cs1` (seed 1);
  - v5: `b4v5` (seed 0), `b4v5s1` (seed 1).

| run | bộ cuối | val | test | vs H0 (ghép cặp) | task kích hoạt: W/L | task không kích hoạt: W/L |
|---|---|---|---|---|---|---|
| H0 | – | 0.267 | 24% | – | – | – |
| v4 s0 | (rỗng, dừng sau vòng 3) | 0.267 | 18% | 5W/11L | – | 5W/11L |
| v4 s1 | (rỗng; m3, m4 qua sàng lọc nhưng thua trên val) | 0.267 | 23% | 9W/10L | – | 9W/10L |
| v5 s0 | (rỗng; m6 qua sàng lọc nhưng thua trên val) | 0.267 | 27% | 8W/5L | – | 8W/5L |
| v5 s1 | m1: `reject_finish` khi `is_finish and answer_hedged and n('search') >= 2 and steps_left > 0` | 0.367 | **33%** | 14W/5L (p=0.06) | 61 task: 5W/3L (p=0.73) | 39 task: 9W/2L |

Bảng do `python scripts/b4_paired.py results/medium_luna5 browsecomp_plus b4v4c b4v4cs1 b4v5 b4v5s1` sinh ra.

**Nhận xét**
- **Nhiễu test của BCP rất lớn.** Ba run có bộ rỗng dùng đúng harness H0 nhưng được 18%, 23% và 27% (H0 gốc 24%). Hai run cùng harness có thể chênh 4W/13L (p=0.05).
  - Hệ quả: một run 1 seed vượt H0 vài điểm không chứng minh được gì.
  - Từ nay nên báo cáo kèm cột tách task có/không kích hoạt.
- **33% của v5 s1 phần lớn không do m1.**
  - Trên 39 task m1 không kích hoạt, episode giống H0 trừ nhiễu lấy mẫu, nhưng vẫn được 9W/2L.
  - Trên 61 task m1 kích hoạt, chỉ được 5W/3L.
  - Hiệu ứng có thể quy cho m1 là khoảng +2 task/100, chưa có ý nghĩa thống kê.
- **Cơ chế được chọn ổn định qua các lần chạy:** `reject_finish` khi trả lời lấp lửng sau vài lần search.
  - Cùng loại với v3 (§8, §11), v4 s1 (m3) và v5 s0 (m3).
  - Mode do LLM gom cụm cũng ổn định: `weak_search_abandonment` / `unproductive_search_abandonment`.
- **Kiểm tra trước bằng replay hoạt động đúng.**
  - v5 s0 m5 (`inject` khi `steps_left == 1 and n_actions == 0`) được dự đoán kích hoạt 0/121, vẫn 0 sau khi sửa, nên bị loại mà không tốn episode sàng lọc.
  - Với v4, loại lỗi này chỉ lộ ra sau khi đã chạy xong sàng lọc ("never fired", v4 s1 m5).
  - Dự đoán khớp thực tế: m1 của v5 s1 dự đoán 31/35 run mục tiêu, 0/24 run thành công; khi sàng lọc kích hoạt 10/10 task mục tiêu, 0 task an toàn.
- **`llm_check` ít được proposer dùng:** 1/12 ứng viên v5 (v5 s0 m1).
  - Ứng viên đó hỏi 18 lần (12 YES, 6 NO). Tầng 1 một mình được dự đoán kích hoạt trên 13/24 run thành công (54%); khi sàng lọc, có thêm tầng 2 thì chỉ kích hoạt trên 2/8 task an toàn được lấy mẫu.
  - Nhưng vẫn không cải thiện task mục tiêu. Chưa đủ dữ liệu để đánh giá P3.
- **Guidance luôn bật** (tầng 1 = `True`, 12 ứng viên ở 4 run):
  - 9 bị loại khi sàng lọc, trong đó 6 vì làm hỏng task H0 luôn giải được;
  - 3 qua sàng lọc nhưng không vào bộ cuối (thua trên val).
- **Replay còn sửa được precondition:** v5 s1 m5 (`inject`) được proposer sửa sau kiểm tra trước, rồi qua sàng lọc (dT=+0.1, nhưng dS=−0.167), và không vào bộ cuối.
- **Chi phí:** qua 9router (Codex OAuth, `cx/gpt-6-luna`) các lời gọi được ghi `unpriced_gateway` ($0).

**Việc tiếp theo**
- Tăng số seed hoặc dùng 2 lần lặp test cho mỗi run để giảm nhiễu trước khi so v4/v5.
- Báo cáo test theo cột có/không kích hoạt.
- Khuyến khích proposer dùng `llm_check` cho `inject` (đang ít được chọn).
- Chạy AppWorld (cần `aw-venv` Python 3.12 và dữ liệu appworld).

## 13. B4 v7 (sửa thành phần bằng code + rẽ nhánh tại điểm phân kỳ + LLM tham gia duyệt), BCP, seed 0

Run `b4v7d` (`results/medium_luna5/b4v7d_browsecomp_plus.jsonl`, log `results/medium_luna5/logs/b4v7d.log`).
Khác v5/v6: ứng viên không còn là luật `precondition -> inject/reject` mà là **một variant code mới của một slot**
(`tool_policy`, `context_mgmt`, `verifier`, `agent_loop`) kèm giả thuyết hành vi đo được. Precondition không do
proposer khai mà được **đo**: phát lại run đã lưu dưới harness mới, bước đầu tiên request khác đi là điểm rẽ nhánh
(`baselines/b4_diff.py`). Không có prompt/hook được chèn.

**Quy trình mỗi vòng** (`baselines/b4_comp.py`): 5 giả thuyết → code cho 3 ứng viên → cổng (tĩnh, tổng quát hoá,
phát lại khô phải chạm ≥ 1 run; 2 lần viết) → thăm dò hành vi (16 nhánh) → sàng lọc kết quả (64 nhánh) → 3 phiếu LLM
duyệt (adopt/reject/revise, lợi ích = thành công hoặc hiệu quả) → xác nhận trên val (3 lần lặp) → gộp tối đa 1 ứng viên.

**Kết quả test (100 task)**

| Hệ | Test | So với H0 (từng task) |
|---|---|---|
| H0 | 24% | – |
| B1 | 28% | +10 / −6, p = 0.45 |
| B2 | 23% | – |
| B3 | 21% | – |
| **B4 v7, chạy lại toàn bộ** | **33%** | **+15 / −6**, sign test hai phía p ≈ 0.08 |
| B4 v7, ước lượng rẽ nhánh (k = 2) | 36% | task +20 / −5 (p = 0.002); nhánh 29W / 5L trên 200 |

- Hai cách đo cùng hướng; lần chạy lại toàn bộ là một mẫu độc lập (33%), ước lượng rẽ nhánh là trung bình 2 lần (35%, 37%).
- Chi phí: 166k token và 15.7 bước mỗi task, so với 24k token và 5.6 bước của H0 (khoảng 7 lần token).
- Mới 1 seed. Chưa đủ để khẳng định hơn B1 một cách có ý nghĩa thống kê.

**Harness cuối: 4 sửa đổi do pipeline tự tìm**

| Vòng | Ứng viên | Slot | Tác dụng đo được | Train (nhánh) | Val |
|---|---|---|---|---|---|
| 1 | c2 `delay_early_finish` | tool_policy | ẩn finish tới khi đã dùng 2 tool khác nhau; n_actions 4.4 → 13.7 | 4W / 0L của 64 | 4W / 2L của 90 |
| 2 | c5 `compact_old_observations` | context_mgmt | token 289k → 131k (gộp vì hiệu quả) | 5W / 0L của 64 | 5W / 1L của 90 |
| 3 | c9 `dedupe_old_results` | context_mgmt | token 209k → 83k trên run bị chạm (cover 0.1) | 0W / 0L của 30 | 1W / 0L |
| 5 | c20 `cap_unexecuted_call_waste` | agent_loop | bước mất vào lời gọi không được thực thi 6.3 → 0 | 4W / 0L của 64 | đồng ý |

Ước lượng train 19.3% → 30.7%; val in ra 30.0% (chỉ dùng nhánh k = 0, xem "Hạn chế").

**20 ứng viên qua 5 vòng**
- 4 được gộp (bảng trên).
- 4 bị loại dù hành vi đổi đúng dự đoán: c3 (hội đồng từ chối: 2W/0L không đủ tin, chi phí tăng); c15 rút gọn kết
  quả search (3W/5L); c18 và c19 cho finish sớm hơn (0W/7L và 1W/4L trên 40).
- 12 hỏng ở code: không dựng được, không chạm run nào (dead code), hoặc không gây ra hành vi dự đoán.

**Bài học**
- **Rẽ nhánh loại được sửa đổi "hợp lý nhưng có hại".** c18/c19 làm đúng điều dự đoán nhưng thua rõ; nghĩa là việc c2
  buộc tìm thêm trước khi trả lời có ích thật, dù nó để 78/150 run train kết thúc không có câu trả lời.
- **Facts đưa cho proposer phải đúng.** Bản đầu của `_endings` nói các run không trả lời "dừng trước ngân sách bước";
  thực ra cả 78 run dùng hết ngân sách, mất trung vị 6 bước vào lời gọi finish bị từ chối. Bốn ứng viên agent_loop
  (c6, c10, c14, c16) nhắm sai và chết. Sau khi sửa facts (`loop_frac`, `unexecuted_calls`), vòng 5 đề xuất ngay c18–c20
  và c20 được gộp.
- **Implementer cần thấy hình dạng dữ liệu thật**, không phải nội dung: cấu trúc kết quả tool (`obs_shapes`), dạng
  câu trả lời không kèm tool call (`reply_shapes`), code của các variant đã gộp ở slot khác. Thiếu chúng thì code đoán
  tên field / thẻ markup và thành dead code (c8, c14).
- **Các sửa đổi trong lúc chạy đều là sửa pipeline tổng quát** (prompt implementer, facts, cache), không có ID task,
  tên tool hay nội dung benchmark. Tuy vậy chúng được thêm giữa run sau khi xem lỗi, và c14 được cho viết lại hai lần;
  một seed mới chạy từ đầu bằng pipeline cuối mới là phép đo sạch.

**Hạn chế đã biết**
- Điểm val in sau khi gộp chỉ dùng nhánh k = 0 của mỗi run val (quyết định gộp thì dùng cả 3).
- 60% ứng viên hỏng ở khâu viết code: nút thắt hiện tại là implementer, không phải proposer hay khâu đánh giá.
- Chi phí token tăng khoảng 7 lần so với H0; chưa có ràng buộc chi phí trong tiêu chí gộp theo "thành công".

**Hạ tầng thêm trong đợt này**
- Resume: cache tuần tự các lời gọi `b4:` (đuôi lệch được cắt khỏi file), nhánh đã chạy đọc lại từ jsonl, kết quả phát
  lại khô được lưu theo hash code của hai harness (resume từ ~80 phút còn vài phút).

## 14. B4 v7, seed 1 chạy sạch từ đầu (`b4v7e`), BCP

Chạy bằng pipeline cuối cùng, không sửa gì giữa chừng (chỉ resume sau giới hạn 2 giờ của tác vụ nền). Cùng H0, cùng giao thức MEDIUM.

| Run | Sửa đổi được gộp | Test (chạy lại toàn bộ) | So với H0 từng task | Ước lượng rẽ nhánh (k = 2) | Token / task | Bước / task |
|---|---|---|---|---|---|---|
| H0 | – | 24% | – | – | 24k | 5.6 |
| v7 seed 0 (`b4v7d`) | 4 (c2, c5, c9, c20) | 33% | +15 / −6, p = 0.078 | 36%, task +20 / −5 | 166k | 15.7 |
| v7 seed 1 (`b4v7e`) | 1 (c3 `verifier/verify_answer_evidence`) | 32% | +12 / −4, p = 0.077 | 31%, task +12 / −3 (p = 0.018) | 151k | 10.9 |

- **Diễn biến seed 1:** vòng 1 gộp c3 (val 26.7%; trên đủ 3 nhánh 28.9%). Vòng 2 và 3 không nhận ứng viên nào (1 REFUTED, 3 DEAD CODE, 5 INEFFECTIVE; c2 SUPPORTED trên train nhưng không được chọn gộp), nên pipeline dừng sớm theo quy tắc "2 vòng không gộp". 10 ứng viên: 1 gộp.
- **Hai seed cho kết quả test gần nhau (33% và 32%) dù harness cuối khác nhau.** Điểm chung của hai harness là buộc agent làm việc lâu hơn trước khi chấp nhận câu trả lời (seed 0: hoãn kết thúc sớm; seed 1: kiểm tra bằng chứng của câu trả lời). 8 task sai ở H0 đều đúng ở cả hai seed.
- **Thống kê:** từng seed riêng chưa đạt p < 0.05 (≈ 0.08). Gộp hai seed theo task (trung bình 2 lần chạy so với 1 lần chạy H0): 19 task tốt hơn, 8 kém hơn, p = 0.052. So sánh này dùng chung một lần chạy H0 cho cả hai seed, và H0 từng dao động 18–27% giữa các lần chạy, nên kết luận hợp lý là "cải thiện khoảng 8 điểm, nhất quán qua 2 seed, chưa khẳng định chắc về thống kê".
- **Chi phí:** cả hai seed tốn gấp 6–7 lần token của H0.
- **Điểm yếu lộ rõ ở seed 1:** 9/10 ứng viên hỏng ở khâu code (không đổi hành vi hoặc đổi sai hướng), tức khâu viết code vẫn là chỗ nghẽn; và quy tắc dừng sớm cắt run sau 3 vòng.

## 15. B4 v7 + bản đồ nhân quả của sổ kết quả (`baselines/b4_graph.py`, `B4_CGRAPH=1`), BCP, seed 1 (`b4v7g`)

**Thêm gì.** Một view dẫn xuất từ `ledger.json` (không phải nguồn dữ liệu mới), dựng lại mỗi vòng, ghi ra `graph.json`, đưa vào prompt đề xuất giả thuyết:
- **A. hành vi → kết quả:** mỗi đặc trưng mà một sửa đổi làm thay đổi rõ, kèm thắng/thua gộp của các sửa đổi đã gây ra nó. Các đặc trưng do đúng cùng một tập sửa đổi gây ra được gộp thành một nút (thí nghiệm không tách được chúng).
- **B. ý tưởng còn mở:** giả thuyết mà hành vi dự đoán chưa từng được tạo ra (NOT BUILT, DEAD CODE, INEFFECTIVE), kèm lý do hỏng. Người viết code cũng nhận các lần hỏng trước của cùng hành vi.
- **C. tác dụng phụ của sửa đổi đã gộp:** thay đổi ngoài mục tiêu, còn tồn tại hay đã được sửa đổi sau đưa về.
- `B4_CGRAPH=0` cho lại pipeline cũ. Test: `tests/test_b4_graph.py` (4).

**Kết quả** (mọi thiết lập khác như §14):

| Run | Sửa đổi được gộp | Ứng viên vòng 2–3 tạo được hành vi dự đoán | Test (chạy lại toàn bộ) | So với H0 | Ước lượng rẽ nhánh | Token / task |
|---|---|---|---|---|---|---|
| H0 | – | – | 24% | – | – | 24k |
| seed 1, không graph (`b4v7e`) | c3 `verifier/verify_answer_evidence` (vòng 1) | 1 / 7 | 32% | +12 / −4 | 31% | 151k |
| seed 1, có graph (`b4v7g`) | c4 `agent_loop/inspect_before_finish` (vòng 1) | 1 / 10 | 22% | +7 / −9 | 26% (task +3 / −0) | 54k |

**Đọc kết quả**
- **Lượt chạy này không cho thấy graph có ích, và cũng không đo được graph có hại trên test.** Khác biệt test (32% so với 22%) đến từ vòng 1, khi sổ còn rỗng nên hai cấu hình giống hệt nhau: hai lượt chạy gộp hai sửa đổi khác nhau, và c4 yếu hơn hẳn (train 2 thắng / 0 thua trên 64 nhánh, val 1 / 0). Đây là độ dao động giữa các lần chạy của chính pipeline, lớn hơn mọi hiệu ứng của graph.
- **Ở vòng 2–3, nơi graph có nội dung, tỉ lệ ứng viên hỏng ở code không đổi** (9/10 so với 6/7). Proposer có dùng graph (phân tích vòng 2 nhắc đúng hai hướng có lợi và tránh cách đã thất bại), nhưng chỗ nghẽn là bước viết code: 5 DEAD CODE, 2 NOT BUILT (ghi cứng tên tool), 4 INEFFECTIVE trên 14 ứng viên.
- **Tiêu chí gộp còn lỏng với lợi ích nhỏ:** c4 được gộp với tổng 3 thắng / 0 thua trên 121 nhánh train + val (p = 0.125, vừa qua ngưỡng 0.15); chạy lại toàn bộ trên test cho 7 thắng / 9 thua. Ước lượng rẽ nhánh (26%) và chạy lại toàn bộ (22%) chênh nhau 4 điểm, đúng cỡ nhiễu ±5 đã biết.
- **Hệ quả cho ba lượt v7:** test 33%, 32%, 22%. Kết luận "cải thiện khoảng 8 điểm, nhất quán" ở §14 phải hạ xuống: 2 trên 3 lượt hơn H0, 1 lượt không hơn; trung bình 29%.

## 16. B4 v7: vòng sửa code có phản hồi, tiêu chí gộp chặt hơn, đủ 5 vòng — BCP, seed 1 (`b4v7h`)

**Sửa gì** (`baselines/b4_comp.py`, test ở `tests/test_b4_build.py`)
- **Khâu viết code:** 4 lần thử thay vì 2 (`B4_IMPL_TRIES`); mỗi lần sửa được xem file trước và lý do bị loại. Sửa đổi "không đổi gì" được chạy lại trên 12 run dài nhất dưới line trace, báo hàm không được gọi và câu lệnh không bao giờ chạy (chỉ nhánh do chính sửa đổi thêm vào). Sửa lại vì hành vi không xuất hiện: kèm các hiệu ứng đo được và code trước.
- **Tiêu chí gộp vì tăng thành công:** val không thua ròng, và bằng chứng gộp train + val phải hơn ít nhất 3 thắng và qua sign test p ≤ 0.1 (`B4_MERGE_ALPHA`); bỏ ngoại lệ "fork cuối". Ngưỡng được chọn sau khi đã thấy c4 của `b4v7g` (3/0) không giúp gì trên test.
- **Xác nhận theo độ mạnh bằng chứng train**; sau một lần gộp, ứng viên đã được nhận ở slot khác được ghép lên harness mới và xác nhận tiếp (`B4_MULTI_MERGE`).
- **Bỏ dừng sớm** (`B4_EARLY_STOP=1` để bật lại).

**Kết quả** (seed 1, cùng H0, cùng model)

| Lượt | Gộp | Test chạy lại | So H0 từng bài | Ước lượng nhánh | Token/bài |
|---|---|---|---|---|---|
| H0 | – | 24% | – | – | 24k |
| `b4v7e` (không graph, dừng vòng 3) | c3 verifier | 32% | +12/−4 | 31% | 151k |
| `b4v7g` (graph, dừng vòng 3) | c4 agent_loop | 22% | +7/−9 | 26% | 54k |
| `b4v7h` (bản này, 5 vòng) | c9 context_mgmt (vì hiệu quả) | 21% | +4/−7 | 26.5%, bài +7/−4 | 18k |

**Khâu viết code** (ứng viên không qua được khâu code / tổng số)

| | NOT BUILT + DEAD CODE | Chạy được nhưng không gây hành vi | Đo được giả thuyết |
|---|---|---|---|
| `b4v7e` | 3/10 | 4/10 | 3/10 |
| `b4v7g` | 7/14 | 4/14 | 3/14 |
| `b4v7h` | 4/18 (vòng 1–4: 1/13) | 6/18 | 8/18 |

**Đọc kết quả**
- **Khâu viết code tốt lên rõ:** 8 trên 18 giả thuyết được đo thật (trước: 3). 3 DEAD CODE còn lại đều ở vòng 5 và ít nhất một cái (sửa lệnh gọi sai định dạng) có điều kiện không hề xảy ra trong các run đã lưu: lỗi của ý tưởng, không phải của code.
- **Nhưng không có sửa đổi nào làm tăng tỉ lệ đúng.** 5 giả thuyết bị bác (hành vi xuất hiện, thành công không tăng), 3 không kết luận được. Sửa đổi duy nhất được gộp (c9) là vì giảm token: test 21% so với 24% của H0 (+4/−7, trong vùng nhiễu), token/bài giảm 25%.
- **Tiêu chí gộp mới làm đúng việc:** không sửa đổi nào có lợi ích nhỏ lọt qua với lý do "tăng thành công".
- **Một lỗi cổng kiểm tra làm mất ứng viên đáng chú ý nhất.** c2 (verifier, hoãn chấp nhận câu trả lời còn do dự — cùng họ với c3 đã cho 32% ở `b4v7e`) bị loại 4 lần vì một regex dài 468 ký tự: người viết đã chia thành các đoạn ngắn nối liền nhau nhưng `ast` gộp lại thành một hằng. Đã sửa: mẫu truyền thẳng vào `re` không tính là văn bản hướng dẫn. Lượt `b4v7h` chạy với cổng còn lỗi.
- **Điều còn thiếu là ý tưởng tốt, không phải code chạy được.** Bốn lượt v7 cho test 33%, 32%, 22%, 21%; hai lượt tốt đều nhờ một sửa đổi ở verifier/kiểm chứng câu trả lời tìm thấy ở vòng 1–2. Pipeline chưa tìm lại được hướng đó một cách ổn định.

## 17. B4 v7 + kiểm tra tiền điều kiện trên run đã lưu — BCP, seed 1 (`b4v7i` dở dang, `b4v7j` đủ 5 vòng)

**Sửa gì** (`baselines/b4_comp.py`, `baselines/b4_diff.py`, `baselines/common.py`, test ở `tests/test_b4_build.py`)
- **Tiền điều kiện (`when`) cho mỗi giả thuyết** (`B4_WHEN`, `B4_WHEN_MIN`): người đề xuất phải viết một biểu thức trên các đặc trưng từng bước của trajectory (`STEP_FEATURES`: bước, kích thước kết quả, lỗi, gọi lặp, câu trả lời còn do dự, …) mô tả tình huống mà sửa đổi nhắm tới. Trước khi viết code, biểu thức được đo trên 150 run H0 train đã lưu; giả thuyết bị loại nếu tình huống xuất hiện ở dưới 5% số run. Người đề xuất được xem bảng tần suất nền của các đặc trưng (chia theo run đúng/sai).
- **Bốn bản sửa sau `b4v7i`** (commit 2fb393c): (1) luật "số dài" của cổng khái quát hoá nêu rõ hằng nào vi phạm và bỏ qua số đã có trong harness; (2) run thử offline có đủ câu trả lời giả cho sửa đổi kéo dài vòng lặp; (3) tách `no_call_replies` (model trả lời không gọi tool) khỏi `refused_calls` (finish bị từ chối); (4) **token của nhánh giờ tính cả phần phát lại** — trước đó nhánh chỉ tính token sau điểm rẽ, nên mọi so sánh token nhánh/gốc ở §13–§16 đều thiên về phía "tiết kiệm" (ví dụ c9 của `b4v7h`: val báo 27k→15.7k, test chạy lại thật là 24k→18k).

**Tần suất nền trên 150 run H0 train:** câu trả lời cuối còn do dự ở 88% run sai và 0% run đúng; không có lỗi tool, không có lệnh gọi lặp, không có run bỏ trả lời; run dùng 3–5 trên 25 bước.

**Kết quả**

| Lượt | Ứng viên | Gộp | Test chạy lại |
|---|---|---|---|
| H0 | – | – | 24% |
| `b4v7i` (tiền điều kiện, cổng cũ; bị dừng ở vòng 4 do giới hạn 2 giờ, chưa chấm test) | 12 | vòng 1: c2 verifier/từ chối finish còn do dự (train 5 thắng/0 thua trên 64 nhánh, val xác nhận; token/run trên nhánh bị chạm ~24k→250k) | – |
| `b4v7j` (tiền điều kiện + bốn bản sửa, chạy lại từ đầu) | 17 | **không gộp gì** | **24% (= H0)** |

`b4v7j` theo ứng viên: 8 INEFFECTIVE (code chạy nhưng không gây hành vi dự đoán), 3 INCONCLUSIVE, 1 REFUTED, 2 NOT CONFIRMED trên val (c8 giảm token; c13 3 thắng/0 thua train), 2 DEAD CODE, 1 NOT BUILT.

**Đọc kết quả**
- **Kiểm tra tiền điều kiện làm đúng một việc:** nó đưa đặc trưng phân biệt mạnh nhất (câu trả lời còn do dự: 88% run sai, 0% run đúng) ra trước mắt người đề xuất, và ở cả hai lượt ý tưởng verifier được đề xuất ngay vòng 1.
- **Nhưng nó không chọn giả thuyết theo độ phân biệt.** Ở `b4v7j`, 9/17 giả thuyết dùng tiền điều kiện luôn đúng (`result_chars > 8000` 7 lần, `step >= 1`, …): qua ngưỡng 5% nhưng không nói gì về run sai. Ngưỡng tối thiểu loại được ý tưởng "không bao giờ xảy ra", không loại được ý tưởng "lúc nào cũng xảy ra".
- **Cùng một ý tưởng, hai bản cài đặt, hai kết cục.** c2 ở `b4v7i` từ chối kiên trì (5 thắng/0 thua, tốn gấp 10 token); c2 ở `b4v7j` chỉ từ chối một lần và chỉ chạm 18 run trong khi tiền điều kiện đúng ở 106 run (1 thắng/0 thua trên 36 nhánh) → không kết luận được và bị bỏ. Pipeline đo được khoảng cách "tiền điều kiện đúng ở 106 run, code chạm 18" (`when_touched`) nhưng chưa dùng nó để yêu cầu viết lại.
- **Kết quả phụ thuộc may rủi của khâu viết code**, không ổn định qua các lượt: năm lượt v7 đủ vòng cho test 33%, 32%, 22%, 21%, 24%.
- **Việc nên làm tiếp (chưa làm):** (a) khi code chạm ít run hơn hẳn số run có tiền điều kiện, trả lại cho người viết sửa; (b) xếp hạng/ưu tiên giả thuyết theo độ phân biệt (tỉ lệ ở run sai trừ tỉ lệ ở run đúng), không chỉ ngưỡng tối thiểu; (c) không áp luật "số dài" lên chuỗi mô tả trong `reg.register` (model không bao giờ thấy chuỗi này; c11 mất vì nó).

## 18. B4 v7 + ba cải tiến sau §17 (viết lại khi sửa đổi chạm ít run, ưu tiên theo độ phân biệt, nới luật số dài) — BCP, seed 1 (`b4v7k`)

**Sửa gì** (`baselines/b4_comp.py`, test ở `tests/test_b4_build.py`, 15 test)
- **(a) Viết lại khi sửa đổi chạm quá ít run** (`B4_REACH_MIN`=0.5, `B4_REACH_TRIES`=2): sau khi code qua các cổng, số run đã lưu mà nó thật sự thay đổi được so với số run có tiền điều kiện. Nếu dưới một nửa, người viết nhận phản hồi "sửa đổi đúng nhưng hẹp: chạm X trên N run" và viết lại; bản chạm rộng nhất được giữ.
- **(b) Ưu tiên giả thuyết theo độ phân biệt** (`B4_WHEN_DISC`=0.2): độ phân biệt = tỉ lệ run sai có tình huống − tỉ lệ run đúng có tình huống. Giả thuyết có độ phân biệt ≥ 0.2 được viết code trước, ≤ −0.2 xếp cuối. Bảng tần suất nền cho người đề xuất nay ghi rõ hai tỉ lệ này.
- **(c) Luật "số dài"** bỏ qua chuỗi mô tả trong `reg.register(...)` (model không bao giờ thấy chuỗi này).
- **(d) Phát hiện trong lúc chạy thử:** bản viết lại của (a) vẫn chỉ chạm 11/150 run, vì người viết phải tự đoán pipeline đo "câu trả lời còn do dự" thế nào (regex của họ khớp 3 trên 37 câu mà pipeline đánh dấu). Đã thêm **định nghĩa cách đo của từng đặc trưng** vào prompt viết code và vào phản hồi "chạm ít". Lượt `b4v7k` chạy lại từ đầu với bản này.

**Kết quả theo vòng** (thắng/thua = số nhánh train đổi từ sai→đúng / đúng→sai, trên 64 nhánh)

| Vòng | Ứng viên | Kết cục |
|---|---|---|
| 1 | c1 tool_policy | INEFFECTIVE |
| 1 | **c2 verifier/reject_hedged_finish** — chạm 43% run, 6 thắng/0 thua (p=0.016), hành vi đúng dự đoán | **GỘP** (val xác nhận; train 23.3%, val 30.0%) |
| 1 | c3 agent_loop | DEAD CODE |
| 1 | **c4 context_mgmt/trim_long_history** — chạm 88% run, 5 thắng/0 thua (p=0.031), hành vi **ngược** dự đoán (token/run 23.8k→72.7k) | **GỘP** (val xác nhận; train 25.3%, val 33.3%) |
| 2 | c5 tool_policy (3/0), c6 context_mgmt, c7 agent_loop (2/0) | c5 không được val xác nhận; INEFFECTIVE; INCONCLUSIVE |
| 3 | c8 agent_loop (3/0), c9 context_mgmt (4/2), c10 tool_policy (0/0) | NOT CONFIRMED; INCONCLUSIVE; REFUTED |
| 4 | c11 tool_policy (0/0), c12 tool_policy (3/8), c13 agent_loop (0/4) | cả ba REFUTED |
| 5 | c14 agent_loop (2/0), c15 agent_loop (0/0) | INCONCLUSIVE; REFUTED |

**Test (100 bài)**

| | Test chạy lại | Thắng/thua theo bài so với H0 | Ước lượng nhánh | Token/bài | Bước/bài |
|---|---|---|---|---|---|
| H0 | 24% | – | – | 24k | 5.6 |
| `b4v7k` = H0 + c2 + c4 | **36%** | **+16/−4** (dấu, hai phía p=0.012) | 33.5%, bài +14/−2 (p=0.002) | **72k** | 14.5 |

**Đọc kết quả**
- **Đây là kết quả test cao nhất của v7** (các lượt đủ vòng trước: 33%, 32%, 22%, 21%, 24%), và là lượt đầu tiên mà ước lượng nhánh lẫn chạy lại đầy đủ đều khác H0 có ý nghĩa thống kê. H0 chạy lại dao động 18–27%, nên 36% nằm ngoài vùng nhiễu, nhưng vẫn chỉ là một seed.
- **Cải tiến (a)+(d) là thứ tạo khác biệt.** Cùng ý tưởng "từ chối câu trả lời còn do dự": `b4v7j` chạm 18 run và bị bỏ (1 thắng/0 thua); bản chạy thử `b4v7k` đầu chạm 11 run; sau khi người viết được cho biết cách đo, chạm 65 run, 6 thắng/0 thua, được gộp ngay vòng 1.
- **Cái giá: token gấp 3, số bước gấp 2.6.** Cả hai sửa đổi đều làm agent tìm kiếm lâu hơn thay vì bỏ cuộc sớm. c4 được đề xuất để *giảm* ngữ cảnh nhưng hành vi đo được là ngược lại (nhánh dài hơn); pipeline ghi nhận "hành vi KHÔNG như dự đoán" và vẫn gộp vì kết quả tăng ở cả train lẫn val. Tức là lợi ích của c4 không đến từ cơ chế mà giả thuyết nêu; phần đóng góp riêng của c4 so với "cho agent chạy lâu hơn" chưa được tách.
- **Chưa so với một H0 được ép chạy lâu tương đương.** H0 tự dừng ở ~5.6 bước trên ngân sách 25 bước, nên phần tăng không phải do nới ngân sách; nhưng một phép so cùng chi phí (ví dụ H0 với lời nhắc "tiếp tục tìm") là đối chứng còn thiếu.
- **(b) đưa ra tình huống mới nhưng chưa tình huống nào thắng:** sau khi c2+c4 được gộp, các đặc trưng mới xuất hiện (kết quả trùng lặp, chuỗi dài cùng một tool, run hết bước chưa trả lời: 21% run sai, 0% run đúng). Các ứng viên vòng 2–5 nhắm vào đó đều gây đúng hành vi nhưng không tăng thành công (5 REFUTED, 3 INCONCLUSIVE, 2 không được val xác nhận; 1 INEFFECTIVE).
- **Vận hành:** lượt này bị gián đoạn hai lần bởi giới hạn 2 giờ của tiến trình nền và một lần ~2.5 giờ do tài khoản model hết hạn mức; mỗi lần đều chạy tiếp từ điểm lưu (kết quả các vòng đã xong được phát lại, không chạy lại).

## 19. B4 v7 chạy một lượt trên nhiều benchmark — seed 0 (`b4v7l`)

Cùng code với §18 (không đổi pipeline), seed 0, giao thức MEDIUM. ALFWorld được bỏ khỏi lượt chạy giữa chừng theo yêu cầu.

**Tổng hợp**

| Benchmark | H0 (test) | B4 v7 (test) | Sửa đổi được gộp | Ghi chú |
|---|---|---|---|---|
| BrowseComp-Plus (100 bài) | 24% | **39%** | c1 verifier/reject_hedged_finish (vòng 1), c6 agent_loop/bound_no_call_retries (vòng 2) | đủ 5 vòng; token/bài 24k → 233k |
| AppWorld (99 bài) | 55.6% (55/99) | 55.6% (= H0) | không có | đủ 5 vòng, 21 ứng viên đều bị loại |
| ALFWorld (100 bài) | 91% | chưa có | không có (tới lúc dừng) | dừng ở vòng 3/5; 7 ứng viên đã chấm đều bị loại |

**BrowseComp-Plus — so từng bài trên test** (thắng/thua = số bài B4 đúng mà bên kia sai / ngược lại; kiểm định dấu hai phía)

| So với | Test | Token/bài | Thắng/thua | p |
|---|---|---|---|---|
| `b4v7l` | 39% | 233k | – | – |
| H0 (lượt này) | 24% | 24k | 17/2 | 0.0007 |
| B1 seed 0 | 28% | 49k | 14/3 | 0.013 |
| B1 seed 1 | 19% | 21k | 21/1 | <0.001 |
| B2 | 23% | 23k | 19/3 | 0.0009 |
| B3 | 21% | 39k | 20/2 | 0.0001 |

Ước lượng nhánh trên test: 35.5% (bài +16/−0), sửa đổi chạm 69/100 bài, toàn bộ ở cuối run (lúc agent định kết thúc).

Theo vòng: vòng 1 gộp c1 (chạm 71% run, 6 thắng/0 thua, p=0.016; val 30.0%); vòng 2 gộp c6 vì **tiết kiệm** chứ không vì đúng hơn (token nhánh 542k → 339k, 0 thắng/0 thua; val giữ 30.0%); vòng 3–5 không gộp gì (3 INEFFECTIVE; 1 REFUTED + 2 INEFFECTIVE; 2 DEAD CODE + 1 INEFFECTIVE).

**AppWorld** — vòng 1: 2 REFUTED, 1 DEAD CODE, 1 INEFFECTIVE; vòng 2: 3 INEFFECTIVE, 1 DEAD CODE, 1 NOT BUILT; vòng 3: 3 INEFFECTIVE, 1 DEAD CODE; vòng 4: 2 INEFFECTIVE, 1 REFUTED, 1 DEAD CODE; vòng 5: 2 INEFFECTIVE, 1 DEAD CODE, 1 HARMFUL. Tổng 21 ứng viên: 11 INEFFECTIVE, 5 DEAD CODE, 3 REFUTED, 1 HARMFUL, 1 NOT BUILT. Harness cuối = H0 nên test không chạy lại.

**Đọc kết quả**
- **BCP: cao nhất từ trước tới nay (39%), lần thứ hai liên tiếp thắng rõ H0 và cả B1–B3** (lượt trước 36%, seed 1). Cùng một ý tưởng thắng ở cả hai seed: không cho kết thúc bằng câu trả lời còn lấp lửng.
- **Nhưng đắt gấp ~10 lần token** (233k so với 24k; lượt trước 72k vì có gộp thêm sửa đổi cắt lịch sử). Số bước 5.6 → 14.0. Vẫn chưa có đối chứng "H0 bị ép tìm lâu tương đương", nên chưa tách được phần lợi do ý tưởng với phần lợi do tìm lâu hơn.
- **Lỗi đo ở bước chấm, cần sửa:** với c6, 12 nhánh thực ra là 6 nhánh lặp lại hai lần với số token giống hệt nhau (các lượt lặp k không độc lập khi model trả lời y hệt). p=0.0002 của "token giảm" vì thế bị thổi phồng; c6 được gộp trên bằng chứng yếu hơn con số báo ra. Cần gộp các nhánh trùng trước khi kiểm định.
- **AppWorld và ALFWorld: pipeline không tìm ra sửa đổi nào.** Ở AppWorld hơn nửa số ứng viên (11/21) chạy được nhưng không làm hành vi đổi theo hướng dự đoán, 5/21 là code không bao giờ được chạy tới. Tức là khâu "đề xuất + viết code" chưa khái quát sang benchmark có công cụ là API: các giả thuyết rút ra được trên BCP (kết thúc sớm, câu trả lời lấp lửng) không có tương ứng rõ ở đây. ALFWorld thì H0 đã 91% nên gần như không còn chỗ.
- **H0 AppWorld của lượt này thấp hơn hẳn lượt cũ: 55/99 so với 74/99** (`results/medium_luna/h0_appworld.jsonl`; theo bài: 24 bài chỉ lượt cũ đúng, 5 bài chỉ lượt mới đúng; train 91/150 so với 108/150). Cùng harness, cùng tên model; khác nhau ở môi trường AppWorld cài mới trong phiên này và thời điểm gọi model. Chưa rõ nguyên nhân. Vì vậy **không so được B4 lượt này với B1–B3 cũ trên AppWorld** (B1 77/99, B2 74/99, B3 75/99 đều đo trong môi trường cũ).
- **Vận hành:** một lần model hết hạn mức ~3 giờ khi chạy ba việc song song; nhiều lần chạm giới hạn 2 giờ của tiến trình nền, mỗi lần nối lại từ kết quả đã lưu.

## 20. Ba việc kiểm tra sau §19: H0 AppWorld tụt điểm, lỗi đếm trùng, đối chứng cùng chi phí

### 20.1 Vì sao H0 AppWorld tụt từ 74/99 xuống 55/99

**Kết luận: nguyên nhân nằm ở phía model đang được phục vụ (mức "suy nghĩ" trước khi trả lời), không phải môi trường AppWorld hay harness.**

| Giả thuyết | Cách kiểm tra | Kết quả |
|---|---|---|
| Môi trường AppWorld cài mới bị hỏng (lệch phiên bản thư viện) | `appworld verify tests`; `appworld verify tasks` (chạy lời giải mẫu) | 1553 + 138 bài tự kiểm tra đều qua; 147/147 lời giải mẫu đúng → **loại** |
| Chạy song song làm hỏng trạng thái | đọc mã | AppWorld luôn chạy tuần tự → **loại** |
| Harness khác | `h0_hash` | giống hệt → **loại** |
| Lỗi hạ tầng | đếm lỗi | 0 lỗi; các bài sai đều là "làm xong nhưng sai" → **loại** |
| Model trả lời khác trước | H0 trên 50 task train, ghim mức suy nghĩ `high` (`LLM_REASONING_EFFORT=high`, kết quả ở `results/medium_luna5_high/`) | **40/50**; mặc định hiện nay 30.3/50 (trung bình 3 lượt); lượt cũ 36.0/50 |

Harness không gửi mức suy nghĩ nào nên dùng mặc định của gateway. Cùng 50 task, chỉ đổi mức suy nghĩ đã chênh ~10 bài, lớn hơn cả khoảng tụt cần giải thích (~6 bài). Token mỗi lần gọi: cũ 6455, nay 6046, ghim `high` 7092 — lượt cũ nằm giữa hai mức hiện nay, đúng như điểm số. Tôi **không chứng minh được** chính xác mặc định đã đổi lúc nào (không còn trajectory cũ trong máy này); đây là giải thích khớp nhất với số liệu.

Hệ quả: (a) không so AppWorld chéo giữa `results/medium_luna/` và `results/medium_luna5/`; (b) so sánh trong cùng `medium_luna5` (B4 = H0 = 55/99) vẫn hợp lệ; (c) muốn kết quả lặp lại được thì nên ghim mức suy nghĩ khi chạy, thay vì để mặc định.

### 20.2 Sửa lỗi đếm trùng nhánh

Khi một sửa đổi chỉ làm run **kết thúc sớm hoặc cắt bớt** (không phát sinh lần gọi model mới), nhánh hoàn toàn do run đã lưu quyết định; chạy lặp nhánh đó (k = 0, 1, 2) cho ra đúng một kết quả, nhưng trước đây mỗi lần lặp được tính là một mẫu độc lập trong kiểm định dấu.

Sửa: `b4_branch.distinct()` chỉ giữ lần đầu của các nhánh lặp không gọi model; dùng trong `tally` (thắng/thua), `behaviour_shift` và `effects`. `b4_diff` ghi thêm cờ `live`; bản ghi cũ suy ra từ `tokens == tokens_replayed`. Nhánh lặp **có** gọi model vẫn tính riêng. Test mới: `tests/test_b4_branch.py::test_repeats_without_a_model_call_are_one_sample` (93 test qua).

Tính lại trên `b4v7l` (BCP): chỉ c6 bị ảnh hưởng — train 12 nhánh → 6 mẫu (p của "token giảm" 0.0002 → 0.016), val 6 nhánh → **2 mẫu**, không đủ ngưỡng xác nhận (cần chênh ≥ 3). **Với cách đếm đúng, c6 không được gộp.** c1 (sửa đổi tạo ra phần tăng điểm) không đổi: 6 thắng/0 thua trên 64 mẫu. Kết quả test 39% không đổi về bản chất vì c6 không thắng/thua bài nào, chỉ giảm token.

### 20.3 Đối chứng cùng chi phí trên BrowseComp-Plus

Đối chứng (`baselines/controls/min_steps_finish.py`, `scripts/run_control.py`): H0 + một verifier **từ chối mọi lần kết thúc trước bước N**, bất kể câu trả lời nói gì, với đúng câu nhắc trung tính mà c1 dùng. Nó không có "ý tưởng" nào về lúc nào cần tìm thêm; chỉ ép tìm lâu.

| Harness | Test | Bước/bài | Token/bài | So từng bài với B4 (B4 thắng/thua) |
|---|---|---|---|---|
| H0 | 24% | 5.5 | 24k | 18/3 (p=0.001) |
| Đối chứng N=11 | 36% | 15.3 | 215k | 10/7 (p=0.63) |
| **B4 `b4v7l`** | **39%** | 14.0 | 233k | – |
| Đối chứng N=14 | 40% | 17.8 | 289k | 7/8 (p=1.0) |

Đối chứng N=11 so với H0: 15/3 (p=0.008); N=14 so với H0: 19/3 (p=0.001).

**Đọc kết quả:** phần tăng 24% → 39% của B4 trên BCP **gần như hoàn toàn do tìm lâu hơn**. Một luật mù "chưa đến bước N thì chưa được kết thúc" đạt 36–40% ở mức chi phí 215–289k token, kẹp hai bên điểm của B4 (39% ở 233k); không có khác biệt nào giữa B4 và hai đối chứng vượt nhiễu. Ý "chỉ ép tìm tiếp khi câu trả lời còn lấp lửng" của c1 không cho thấy lợi thế đo được so với ép mù ở cùng chi phí.

Điều này không phủ nhận việc pipeline tự tìm ra được một sửa đổi làm tăng điểm thật so với H0 và B1–B3; nhưng "tính mới" của sửa đổi đó yếu: nó tương đương một nút vặn ngân sách. Muốn chứng minh pipeline tìm ra ý tưởng thật sự thì từ nay mọi kết quả cần so với **đường đối chứng cùng chi phí** này, không chỉ với H0.

### 20.4 Ghim mức suy nghĩ: `cx/gpt-6-luna-low`

Đọc mã 9router (v0.5.111, phần Codex): mức suy nghĩ của luna được chọn theo thứ tự (1) `reasoning_effort` trong request, (2) **hậu tố tên model** `-none|-minimal|-low|-medium|-high|-xhigh` (gateway cắt hậu tố rồi gửi mức đó), (3) mặc định — với luna là **`medium`**. Với luna, `none`/`minimal` bị nâng thành `low`.

Kiểm tra bằng một câu tính nhẩm: `cx/gpt-6-luna` và `-medium`, `-high` trả lời đúng với ~90–100 token; `-low` trả lời ngay 5 token và sai. Nếu request có `reasoning_effort` thì nó thắng hậu tố.

Hệ quả:
- **Mọi kết quả trong `results/medium_luna5/` cho tới §20.3 chạy ở mặc định = `medium`.**
- Từ đây ghim **`LLM_MODEL=cx/gpt-6-luna-low`** trong `.env` (theo yêu cầu). Trường `model` của mỗi bản ghi sẽ mang hậu tố, nên phân biệt được với các lượt cũ.
- Harness và pipeline không gửi `reasoning_effort`; ngoại lệ duy nhất là lần thử lại khi câu trả lời rỗng (`fallback_no_reasoning`, gửi `none` → gateway đổi thành `low`), khớp với mức ghim. Không đặt `LLM_REASONING_EFFORT` (chỉ để chẩn đoán) vì nó sẽ thắng hậu tố.
- Kết quả ở `low` **không so được** với H0/B1–B3/B4 đã có (đều ở `medium`): cần chạy lại H0 ở `low` trước khi so bất cứ thứ gì.

## 21. Chạy lại một lượt ở mức suy nghĩ `low` (`cx/gpt-6-luna-low`), seed 0 (`b4v7m`)

Cùng code với §20 (gồm sửa lỗi đếm trùng §20.2), giao thức MEDIUM, kết quả ở `results/medium_luna5low/`. Chạy lại H0, B4 v7 và (trên BCP) hai đối chứng cùng chi phí của §20.3. ALFWorld đã bỏ khỏi benchmark; B1–B3 không chạy lại ở mức này. Mọi so sánh dưới đây là **trong cùng mức `low`**; không so chéo với các mục trước (mức `medium`).

### 21.1 BrowseComp-Plus

H0 ở `low`: train 8/50, 7/50, 8/50 (3 lượt), val 7/30, test 20/100 (ở `medium`: test 24/100).

| Harness | Test | Bước/bài | Token/bài | So từng bài với B4 (B4 thắng/thua) |
|---|---|---|---|---|
| H0 | 20% | 5.7 | 26k | 15/2 (p=0.002) |
| Đối chứng N=11 | 32% | 16.1 | 237k | 8/7 (p=1.0) |
| **B4 `b4v7m`** | **33%** | 14.3 | 238k | – |
| Đối chứng N=14 | 35% | 17.9 | 287k | 9/11 (p=0.82) |

Đối chứng so với H0: N=11 14/2 (p=0.004), N=14 16/1 (p<0.001). Ước lượng nhánh trên test của B4: 29.5% (bài +15/−0), chạm 70/100 bài.

Theo vòng: vòng 1 gộp **c2** `agent_loop/defer_hedged_finish` và **c3** `verifier/hedge_verification` (mỗi cái 7 thắng/0 thua trên 64 nhánh, p=0.008; val 23.3% → 43.3%). Hai cái là **cùng một ý** đặt ở hai chỗ khác nhau: khi câu trả lời cuối còn lấp lửng ("không xác định được") mà còn bước thì không nhận, bắt tìm tiếp. Vòng 2–5 không gộp gì. Trong 16 ứng viên của vòng 2–5: 3 bị chặn ở cổng khái quát vì ghi cứng tên công cụ `search`, 1 không qua bước kiểm tra build; 3 là code không bao giờ chạy tới; 5 không làm hành vi đổi như dự đoán; 2 làm hành vi đổi nhưng điểm giảm; 1 làm hành vi đổi nhưng lợi quá nhỏ so với nhiễu (5 thắng/2 thua); 1 thắng 7/thua 2 trên train nhưng hành vi không đổi như dự đoán nên không được xác nhận.

**Đọc kết quả:** lặp lại đúng §20.3 ở mức suy nghĩ khác. B4 tìm lại đúng ý tưởng cũ (từ chối câu trả lời lấp lửng), thắng H0 rõ ràng, nhưng **không hơn một luật mù "chưa đến bước N thì chưa được nộp" ở cùng chi phí** (237k so với 238k token, 32% so với 33%). Cổng khái quát đã chặn đúng các sửa đổi ghi cứng tên công cụ.

### 21.2 AppWorld

H0 ở `low`: train 35/50, 27/50, 33/50 (3 lượt), val 21/30, test **47/99** (14.3 bước, 83k token mỗi bài). Ở `medium` (§19) test là 55/99.

B4 `b4v7m`: đủ 5 vòng, **không gộp sửa đổi nào**, harness cuối = H0, test 47/99 (= H0).

| Vòng | Ứng viên | Kết quả |
|---|---|---|
| 1 | c1 phá vòng lặp hành động, c2 giữ kết quả lớn, c3 thử lại khi model trả lời mà không gọi công cụ | c1 hành vi đổi nhưng điểm giảm (2/5); c2 không đổi hành vi; c3 thắng 7/thua 2 trên train, LLM duyệt "nhận", nhưng val 0/2 → không xác nhận |
| 2 | c4 giữ nguyên kết quả công cụ lớn, c5 bỏ kết quả trùng khỏi ngữ cảnh, c6 | c4 điểm giảm (3/11); c5 điểm giảm mạnh (0/25); c6 code không chạy tới |
| 3 | c7, c8, c9 | c7, c9 không đổi hành vi; c8 10/9 (nhiễu) |
| 4 | c10, c11 gắn nhãn lỗi gần nhất cạnh lời gọi gây lỗi, c12 | c11 hành vi đổi như dự đoán, 8/3 trên train, LLM duyệt "nhận", nhưng **trên val không có nhánh nào bị chạm** → không xác nhận; c12 12/8 (nhiễu), LLM duyệt "bỏ" vì tốn token hơn; c10 không đổi hành vi |
| 5 | c13–c16 | 2 code không chạy tới; 2 không đổi hành vi (0/3, 1/5) |

Tổng 16 ứng viên: 6 không đổi hành vi, 3 code không chạy tới, 3 hành vi đổi nhưng điểm giảm, 2 nhiễu, 2 có dấu hiệu tốt trên train nhưng không qua val.

**Đọc kết quả:**
- Giống §19 (mức `medium`): pipeline **không tìm được sửa đổi nào cho AppWorld**. Tín hiệu tốt nhất là c3 và c11, cả hai đều về **xử lý lỗi/phản hồi** (thử lại khi không có lời gọi công cụ; gắn lỗi vào đúng lời gọi gây ra nó), nhưng mẫu nhỏ và không lặp lại trên val.
- c5 là ví dụ pipeline đề xuất **ngược với bằng chứng quan sát** của chính nó (số liệu cho thấy run thành công dùng nhiều token hơn, điểm −0.69, mà ứng viên vẫn đi theo hướng giảm token) và bị bác mạnh (0/25). Khâu đề xuất nên chặn sớm những giả thuyết có điểm quan sát âm.
- Không có đối chứng cùng chi phí cho AppWorld, vì B4 = H0 nên không có gì để so.

### 21.3 Tóm tắt lượt `low`

| Benchmark | H0 test | B4 test | Đối chứng cùng chi phí | Sửa đổi được gộp |
|---|---|---|---|---|
| BrowseComp-Plus | 20% (26k tok) | 33% (238k tok) | N=11: 32% (237k); N=14: 35% (287k) | c2 + c3, cùng ý "không nhận câu trả lời lấp lửng" |
| AppWorld | 47/99 | 47/99 (= H0) | – | không có |

Mức `low` hạ điểm H0 ở cả hai benchmark so với `medium` (BCP 24 → 20; AppWorld 55 → 47), nhưng **kết luận về B4 không đổi**: trên BCP lợi ích đến từ việc tìm lâu hơn, ngang luật mù cùng chi phí; trên AppWorld không tìm ra gì.

## 22. B4 v7 + công cụ harness + giao loại sửa mỗi vòng, 3 vòng — BCP, seed 0 (`b4v7p`)

Mức `low`, giao thức MEDIUM như §21. Code lúc bắt đầu: commit 998fe66. Thay đổi so với §21:
- thêm loại sửa "harness tool" (công cụ mới do harness tự trả lời bằng code, không gọi môi trường);
- mỗi vòng giao 5 loại sửa ít thử nhất trong 12 loại, 3 loại đầu là loại lớn;
- prompt đề xuất có 7 câu hỏi gợi ý và thêm trường `novelty`.

Ba bản sửa pipeline (quote_tools, gửi lại ý bị loại để sửa, hoãn thay vì bỏ khi một chỗ sửa đã đủ ý) được làm sau khi lượt chạy bắt đầu. Lượt chạy được tiếp tục bằng đúng code lúc bắt đầu, nên **không** có ba bản sửa này.

| Harness | Test | Bước/bài | Token/bài | So từng bài với `b4v7p` (b4v7p thắng/thua) |
|---|---|---|---|---|
| H0 | 20% | 5.7 | 26k | 14/1 (p=0.001) |
| Đối chứng N=11 | 32% | 16.1 | 237k | 7/6 (p=1.0) |
| B4 `b4v7m` (§21) | 33% | 14.3 | 238k | 5/5 (p=1.0) |
| **B4 `b4v7p`** | **33%** | 16.0 | 280k | – |
| Đối chứng N=14 | 35% | 17.9 | 287k | 8/10 (p=0.82) |

Ước lượng nhánh trên test: 30% (chạm 70/100 bài, 140 nhánh: 20 thắng, 0 thua; theo bài +14/−0).

| Vòng | Ứng viên (loại) | Kết quả |
|---|---|---|
| 1 | c1 ghi chú bằng chứng (working notes) | số kết quả khác nhau được xem 4.8 → 11.6, thắng 6/thua 2, hội đồng bỏ vì tốn |
| 1 | c2 giữ bằng chứng trực tiếp (context) | không đổi hành vi |
| 1 | **c3 `verifier/reject_unsupported_hedge` (acceptance)** | **8/0, p=0.004, gộp** (train 0.233, val 0.367) |
| 2 | c4 tìm rồi mở luôn (composite tool) | không đổi hành vi |
| 2 | c5 gọi model kiểm tra câu trả lời (helper call) | bác bỏ, 4/5 |
| 3 | c6 chuyển sang giai đoạn mở tài liệu (phases) | bác bỏ, 0/2 |
| 3 | c7 sửa mô tả công cụ (tool set) | không đổi hành vi |
| 3 | c8 khởi động lại sau khi bị từ chối (restart) | token 379k → 194k, 3/2, hội đồng nhận 2–1 vì tiết kiệm, không qua val |

Ý bị loại trước khi viết code: vòng 1 "restart" (điều kiện chỉ đúng ở 4/150 run) và "phases" (viết `n(get_document)` thiếu dấu nháy). Vòng 2: hai ý có điều kiện quá hiếm, còn ý công cụ harness `evidence_lookup` bị bỏ vì agent_loop đã có 2 ý.

**Đọc kết quả:**
- Giao loại sửa làm các ý **đa dạng hơn hẳn**: 8 ý thuộc 8 loại, trong đó 4 loại lớn. Các lượt trước gần như chỉ có chỉnh ngưỡng hay sửa thông báo.
- Nhưng **kết quả không đổi**: bản sửa duy nhất được gộp lại là ý "không nhận câu trả lời lấp lửng" như §21, test 33% = `b4v7m`, ngang đối chứng cùng chi phí.
- Các loại lớn chưa thắng. Công cụ gộp không được agent dùng; gọi thêm model và chia giai đoạn đổi đúng hành vi nhưng không tăng độ đúng.
- Công cụ harness chưa được thử lần nào, vì ba lỗi pipeline nói trên.

## 23. Thử nhánh trước trên bài "lúc được lúc không" + cổng chặn hồi quy, 3 vòng — BCP và AppWorld, seed 0 (`b4v7q`)

Mức `low`, giao thức MEDIUM như §21–22. Code: commit c3503ba, có ba bản sửa pipeline mà `b4v7p` thiếu (nên so với §22 có lẫn yếu tố). Hai thay đổi mới, chỉ dùng thống kê kết quả của 3 lần chạy đã lưu, không dùng ID hay nội dung bài:
- **Mục 1 — thử trước bài học được (`B4_LEARN=1`).** Khi rẽ nhánh, xếp trước các bài harness hiện tại giải được ở một số lần (không phải 0/3, không phải 3/3). Đây là nơi một thay đổi dễ làm lật kết quả nhất, nên 16 nhánh thăm dò đầu tiên có nhiều thông tin hơn.
- **Mục 3 — cổng chặn hồi quy (`B4_SENTINEL=1`).** Ngay sau thăm dò, chạy thêm tối đa 8 nhánh trên các bài harness giải được cả 3/3. Nếu số nhánh hỏng ≥ 2 và vượt rõ tỉ lệ hỏng ngẫu nhiên 10% (kiểm định nhị thức, p ≤ 0.05), dừng sàng lọc và không cho gộp, kể cả khi hội đồng đồng ý.

Mô phỏng lại trên các lượt cũ trước khi chạy: với các ý tốt, thăm dò đạt thắng − thua ≥ 2 ở 71% lần (thứ tự ngẫu nhiên: 50%). Cổng chặn không loại nhầm ý nào từng được gộp.

**BCP:**

| Harness | Test | Bước/bài | Token/bài | So từng bài với `b4v7q` (b4v7q thắng/thua) |
|---|---|---|---|---|
| H0 | 20% | 5.7 | 26k | 10/1 (p=0.01) |
| **B4 `b4v7q`** | **29%** | 15.7 | 269k | – |
| Đối chứng N=11 | 32% | 16.1 | 237k | 4/7 (p=0.55) |
| B4 `b4v7m` (§21) | 33% | 14.3 | 238k | 5/9 (p=0.42) |
| B4 `b4v7p` (§22) | 33% | 16.0 | 280k | 5/9 (p=0.42) |
| Đối chứng N=14 | 35% | 17.9 | 287k | 5/11 (p=0.21) |

Ước lượng nhánh trên test: 28.5%, khớp điểm thật 29% (chạm 70/100 bài, 140 nhánh: 17 thắng, 0 thua; theo bài +13/−0).

| Vòng | Ứng viên | Kết quả |
|---|---|---|
| 1 | c1 khởi động lại khi tìm kiếm bị kẹt | 2/0, hội đồng nhận, val 1/11 → không qua |
| 1 | c2, c4 | không đổi gì khi chạy lại |
| 1 | **c3 `verifier/reject_unsupported_hedge`** | **10/0, p=0.001, gộp** (train 0.247, val 0.433) |
| 1 | c5 chỉ mục bằng chứng | không đổi hành vi |
| 2 | c8 kiểm tra độ liên quan của kết quả | đổi đúng hành vi, 12/6, p=0.12, hội đồng bỏ |
| 2 | c6, c7, c9 | không đổi hành vi / không đổi gì |
| 3 | c11 mở ngay tài liệu đầu | bác bỏ: số lần mở tài liệu 0.6 → 45, 5/7; cổng chặn 0/8 hỏng |
| 3 | c10, c12 | không đổi hành vi |

**AppWorld** (H0 47.5%): 3 vòng, 11 ứng viên, **không gộp gì**, nên test giữ nguyên 47.5% (= `b4v7m`).

| Vòng | Ứng viên | Kết quả |
|---|---|---|
| 1 | **c1** (agent_loop) | **cổng chặn loại**: 4/8 nhánh trên bài 3/3 bị hỏng (p=0.005); tổng 6/7. Dừng ở 34 nhánh thay vì 64 |
| 1 | c2 | không đổi hành vi, 0/11 |
| 1 | c3 ghi chú bằng chứng | chưa rõ, 17/15 |
| 2 | c4 | chưa rõ, 16/12 |
| 2 | c5 đọc gộp kết quả đã mở | 16/7, p=0.047, **hội đồng bỏ** vì hành vi đo được không đổi như dự đoán |
| 2 | c7 (tool_policy) | 14/7, p=0.09, hội đồng bỏ vì cùng lý do; cổng chặn 2/11 hỏng (không đủ để chặn) |
| 2 | c6 | không đổi gì kể cả sau khi viết lại |
| 3 | c8 | gây hại, 12/17 |
| 3 | c9, c10, c11 | không đổi hành vi / không đổi gì / chưa rõ 15/15 |

**Đọc kết quả:**
- **Mục 3 có tác dụng thật nhưng nhỏ.** Trên AppWorld, cổng chặn bắt được c1 (đổi đúng hành vi nhưng làm hỏng một nửa số bài vốn luôn đúng) và dừng sớm, tiết kiệm 30 nhánh. Không loại nhầm ý nào. Trên BCP cổng không bao giờ phải chặn: các ý xấu ở BCP (c11) hỏng trên bài lúc được lúc không, không phải trên bài 3/3.
- **Mục 1 không đổi được kết quả.** BCP vẫn gộp đúng ý duy nhất như §21–22; điểm test 29% thấp hơn `b4v7p` 33% nhưng so từng bài 5/9 (p=0.42) là trong dao động, vì cùng một bản sửa. Không có ý mới nào lọt qua nhờ thăm dò tốt hơn.
- **Chỗ nghẽn bây giờ nằm ở hội đồng, không phải ở sàng lọc.** Trên AppWorld, c5 (16/7, p<0.05) và c7 (14/7) đều thắng nhiều hơn thua nhưng bị hội đồng bỏ vì chỉ số hành vi đã dự đoán không đổi. Tức là bản sửa có lợi theo một cách khác với giả thuyết. Muốn đi tiếp có thể cho các ý như vậy vào bước val thay vì bỏ ngay, rồi để val quyết định.

## 24. H0 fail ở đâu — đọc lại toàn bộ lượt chạy H0 (mức `low`, tập train + val)

Chỉ dùng train + val (BCP 180 lượt, AppWorld 180 lượt); không xem test AppWorld, không in câu hỏi BCP. Chỉ có số liệu gộp. Script: `scratchpad/h0_bcp.py`, `h0_aw.py`.

**BCP (30 đúng / 150 sai):**

| Dấu hiệu | Lượt đúng | Lượt sai |
|---|---|---|
| Số bước (trung vị, ngân sách 25) | 5 | 6 (81% dừng ở ≤ 6 bước, 0 lượt hết ngân sách) |
| Có mở tài liệu (`get_document`) | 87% | 12% |
| Đáp án đúng từng xuất hiện trong kết quả agent đã thấy | 100% | 16% |
| Agent tự chấm độ tin cậy ≤ 30 | 1/30 | 132/150 |
| Câu trả lời nước đôi ("không xác định được"...) | 3% | 37% |

Phân loại lượt sai: 78 chốt sớm mà chưa thấy đáp án; 45 trả lời nước đôi; 24 đã thấy đáp án nhưng chọn cái khác; 3 tìm lâu vẫn không ra.

**AppWorld (116 đúng / 64 sai), phân loại lượt sai theo thứ tự ưu tiên:**

| Nhóm | Lượt sai | Tín hiệu |
|---|---|---|
| Gọi API dạng danh sách nhưng không lật trang (`page_index`) | 23 | lượt không lật trang: 38 sai / 14 đúng; có lật trang: 26 sai / 102 đúng |
| Câu hỏi nhưng `complete_task` không kèm `answer` | 9 | 9 sai / 0 đúng |
| Gọi `complete_task` ngay sau một lỗi Python | 8 | 8 sai / 0 đúng |
| Còn lại (sai logic, chọn nhầm mục, sót bước con) | 24 | – |

**Pipeline có thấy những lỗi này không:**
- BCP, trả lời nước đôi: thấy (`answer_hedged`), và đã gộp ở cả ba lượt §21–23.
- BCP, độ tin cậy thấp: không có chỉ số nào. Trong 13 sổ ghi BCP, chưa ý nào dùng độ tin cậy.
- BCP, tìm kiếm kém: thấy gián tiếp. Đã thử mở tài liệu, kiểm tra độ liên quan; chưa ý nào được gộp.
- AppWorld, lật trang, thiếu `answer`: không thấy. Mọi hành động đều là `execute_python`, nên `n(tool)` không phân biệt được nội dung code. Trong 3 sổ ghi AppWorld, chưa ý nào nhắc đến lật trang hay `answer`.
- AppWorld, chốt sau lỗi: thấy `n_errors`. Có hơn 20 ý xử lý lỗi chung chung, không ý nào nhắm đúng "chốt ngay sau lỗi".

## 25. Cụm lỗi thay cho chỉ số đếm — AppWorld, 3 vòng, seed 0 (`b4v7r`)

Code giống hệt `b4v7q` (§23), chỉ thêm `B4_CLUSTER=1` (`baselines/b4_cluster.py`).

### 25.1 Tính năng

- **Gắn nhãn mọi lượt sai.** Sau mỗi vòng, một model đọc từng lượt sai trên train (6 lượt mỗi lần gọi). Bản tóm tắt nó đọc giữ tham số hành động tới 500 ký tự (bản cũ cắt ở 120) và không cho biết kết quả. Với mỗi lượt, model viết một câu "sai ở đâu" (không chứa thực thể của bài), rồi xếp lượt đó vào một cụm có sẵn hoặc mở cụm mới (tên + một câu định nghĩa).
- **Sổ cụm cộng dồn, không lọc.** Mỗi cụm có số lượt sai và số bài sai hiện tại, tổng số lượt đã xếp qua các vòng, và hai ví dụ. Bỏ bộ lọc `harness_fixable`: ý kiến của người gắn nhãn chỉ được hiển thị, proposer tự quyết. Trên 12 cụm thì một lần gọi gộp các cụm trùng nhau.
- **Cụm là một thước đo hành vi.** Giả thuyết có thể đặt `behaviour = mode:<cụm>` (hướng giảm). Một giám khảo không biết kết quả đọc cả lượt gốc lẫn nhánh của từng cặp và trả lời lượt đó có mắc lỗi này không. Sau đó áp kiểm định dấu như với chỉ số số. Cách này đo được những lỗi mà số đếm cuối lượt không diễn tả được (agent làm gì, chứ không phải làm bao nhiêu lần).
- Thử offline trên 55 lượt sai H0 trước khi chạy: cả 55 lượt đều được xếp. Cụm lớn nhất (22 lượt) khớp nhóm "không lật trang" của §24.

### 25.2 Kết quả

Vòng 1 xếp được cả 55 lượt sai train vào 5 cụm, với 10 lần gọi gắn nhãn. Không vòng nào gộp được ý, nên tập lượt sai không đổi và sổ cụm giữ nguyên qua 3 vòng.

| Cụm | Lượt sai | Người gắn nhãn cho là |
|---|---|---|
| `documentation_and_auth_recovery` (đọc sai hoặc bỏ tài liệu API, không xử lý được lỗi xác thực) | 22 | harness sửa được |
| `premature_incomplete_data` (quyết định dựa trên kết quả thiếu hoặc bị cắt, dừng trước khi đủ) | 16 | harness sửa được |
| `premature_task_abandonment` (bỏ dở việc còn làm được) | 14 | harness sửa được |
| `incorrect_relationship_filtering` (lọc quan hệ sai chiều hoặc sai tài khoản) | 2 | lỗi model/bài |
| `incomplete_source_coverage` (chỉ xem một phần các nguồn được yêu cầu) | 1 | harness sửa được |

| Vòng | Ứng viên | Thước đo hành vi | Hành vi đổi? | Thắng/thua (train) | Kết cục |
|---|---|---|---|---|---|
| 1 | c1 khởi động lại khi kết quả lặp | `mode:premature_task_abandonment` | **có** (0.69→0.41, 11/2, p=0.011) | **12/3, p=0.018** | hội đồng nhận; **val không xác nhận** (0/1, chỉ 6 nhánh trên 2 bài) |
| 1 | c2 ghi chú bằng chứng | `mode:premature_incomplete_data` | không | 19/11, p=0.10 | hội đồng bỏ |
| 1 | c3 pha kiểm tra | `mode:premature_incomplete_data` | – | – | code chết |
| 1 | c4 giữ đầu/cuối kết quả dài | `obs_chars/n_actions` | không | 1/3 | không hiệu quả |
| 2 | c5 chặn lặp y hệt | `repeat_ratio` | có (34/0) | 1/14 | **cổng hồi quy chặn** (5/8 bài luôn đúng hỏng) |
| 2 | c6 gọi thêm model đọc lỗi | `distinct_actions` ↑ | không | **21/10, p=0.035** | hội đồng nhận; **val không xác nhận** (9/13 trên 84 nhánh) |
| 2 | c7 công cụ đọc tài liệu gộp | `distinct_results` ↑ | không | 3/3 | không hiệu quả |
| 3 | c8 tìm trong kết quả đã thấy | `mode:premature_incomplete_data` | không | 15/14 | hội đồng bỏ |
| 3 | c9 tài liệu + đăng nhập sau lỗi | `mode:documentation_and_auth_recovery` | gần (0.34→0.23, p=0.11) | 15/9 | hội đồng bỏ |
| 3 | c10, c11, c12 | `mode:…` ×2, `answered` | – | – | code chết |

**Test: 47.5%, bằng H0 và bằng `b4v7q`**, vì không gộp gì. Chi phí thêm: 10 lần gọi gắn nhãn và 406 lần gọi giám khảo (214 cho `premature_incomplete_data`, 144 cho `documentation_and_auth_recovery`, 48 cho `premature_task_abandonment`).

### 25.3 Đọc kết quả

**Đọc kết quả:**
- **Cụm được dùng thật.** 7/12 ý dùng `mode:<cụm>` làm thước đo, và mọi ý đều ghi rõ cụm mình nhắm. Ở `b4v7q`, giả thuyết chỉ dựa được vào các chỉ số đếm.
- **Thước đo cụm đo được thay đổi mà chỉ số đếm bỏ sót.** c1 là ý đầu tiên trên AppWorld vừa đổi đúng hành vi đã dự đoán vừa thắng rõ trên train, nên lần đầu có ý đi được tới val. Ở `b4v7q`, c5 (16/7) và c7 (14/7) dừng ở hội đồng vì chỉ số dự đoán không đổi.
- **Chỗ nghẽn chuyển sang val.** c1 chỉ chạm 2 bài val (6 nhánh), quá ít để xác nhận một bản sửa hẹp. c6 chạm rộng hơn (84 nhánh) nhưng thua nhiều hơn thắng (9/13), nên thắng 21/10 trên train là nhiễu hoặc là khớp quá với train. Muốn đánh giá đúng các ý hẹp như c1 thì cần nhiều lượt val hơn trên những bài mà điều kiện kích hoạt xảy ra.
- **Cụm vẫn chưa gọi tên đúng lỗi lớn nhất của §24.** `premature_incomplete_data` (16 lượt) gần với "không lật trang", nhưng định nghĩa nói chung chung ("kết quả thiếu hoặc bị cắt"). Cả ba ý nhắm cụm này (c2, c3, c8) đều xử lý chuyện cắt hoặc ghi nhớ kết quả, không ý nào nhắc tới lật trang hay `answer`. Định nghĩa cụm một câu vẫn quá trừu tượng để dẫn proposer tới cơ chế cụ thể. Có thể thử bước sau: cho người gắn nhãn ghi kèm "dấu hiệu quan sát được trong hành động" (ví dụ một tham số có trong tài liệu nhưng agent không dùng).
- **Code chết tăng ở vòng 3 (3/5).** c10 và c11 (nhắm `documentation_and_auth_recovery`) đặt điều kiện vào các công cụ tài liệu và đăng nhập riêng, trong khi agent AppWorld chỉ gọi `execute_python` (§24). Vì vậy điều kiện không bao giờ xảy ra trên 145 lượt replay. c12 thì đặt điều kiện vào lượt trả lời không có hành động, mà trường hợp này không xuất hiện trong các lượt đã lưu.
- **Không có tác dụng phụ xấu:** cổng hồi quy vẫn chặn đúng c5, và chi phí giám khảo nhỏ so với chi phí chạy nhánh.

### 25.4 Ghi chú về phần tìm kiếm (BCP)

Đây là ghi chú, chưa chạy thử. Số liệu lấy từ sổ ghi của 4 lượt BCP mức `low` (`b4v7m`, `b4v7n`, `b4v7p`, `b4v7q`, tổng 43 ý) và từ §24.

**Lỗi tìm kiếm trên H0 trông như thế nào (§24):** lượt sai dừng sớm (trung vị 6/25 bước), chỉ 12% có mở tài liệu, và đáp án đúng chỉ xuất hiện trong những gì agent đã thấy ở 16% lượt sai. Vậy phần lớn lượt sai chưa bao giờ chạm tới tài liệu chứa đáp án. Vấn đề nằm ở khâu tìm, không phải khâu đọc hay khâu suy luận.

**Pipeline đã thử gì cho tìm kiếm (23 ý trong 43):**

| Hướng | Ý (lượt/ứng viên) | Kết quả |
|---|---|---|
| Công cụ gộp "tìm rồi mở" | n c1, p c4, q c6, q c11 | không đổi hành vi, hoặc đổi được nhưng thua nhiều hơn thắng (q c11: 5/7) |
| Đẩy agent mở tài liệu (thứ tự, mô tả công cụ, pha "xem xét") | p c6, p c7, q c2, q c10, q c12 | không đổi hành vi / không đổi gì / bác bỏ |
| Ghi chú hoặc chỉ mục bằng chứng | n c3, p c1, p c2, q c5 | p c1 thắng 6/2 nhưng hội đồng không nhận; còn lại không đổi hành vi |
| Đánh dấu hoặc lọc kết quả trùng | m c12, m c17 | m c17 thắng 7/2 nhưng hội đồng không nhận |
| Gọi thêm model để chấm độ liên quan | p c5, q c8 | q c8 thắng 12/6 (p=0.12), hội đồng không nhận; p c5 thua 4/5 |
| Đổi hướng khi gọi một công cụ quá lâu | m c7, m c15, m c19 | không đổi hành vi / chưa rõ |
| Khởi động lại khi bế tắc | q c1 | thắng 2/0 trên train, val không xác nhận |
| Cắt bớt kết quả dài, giữ phần cuối | m c4, q c9 | không đổi gì / không đổi hành vi |

**Điều chưa ý nào làm: thay đổi chính câu truy vấn.** Mọi ý trên đều tác động sau khi kết quả đã về (mở thêm, ghi lại, lọc, chấm lại) hoặc lên lúc nào thì dừng. Không ý nào đụng tới việc truy vấn được viết ra sao, trong khi đó mới là chỗ quyết định tài liệu đúng có lọt vào top-5 hay không. Có ba lý do:
1. Không có chỉ số nào nói về nội dung truy vấn. Các đặc trưng chỉ đếm số lần gọi, số kết quả khác nhau, số ký tự. Proposer không thể nêu giả thuyết kiểu "truy vấn ngắn hơn thì trúng hơn" vì không đo được.
2. Prompt HYP cấm viết lời khuyên cho model ("không thêm hướng dẫn vào prompt"). Cách tự nhiên nhất để đổi truy vấn là bảo model viết khác, nên cách này bị chặn, và chưa ý nào tìm ra cách làm phía harness.
3. Khâu đọc lượt sai (hindsight) có thấy truy vấn: bản tóm tắt cắt tham số ở 120 ký tự, nhưng chỉ 10% truy vấn H0 dài hơn mức đó (trung vị 94 ký tự). Khâu này không có đáp án hay tài liệu đúng nên không biết truy vấn nào hụt và hụt vì sao. Nó chỉ thấy top-5 đoạn trích 300 ký tự trông không liên quan. Nhãn lại buộc phải chung chung, nên kết luận chỉ còn "dừng sau vài lượt tìm rộng mà không tinh chỉnh truy vấn" (`premature_search_abandonment`, 14 bài). Proposer chỉ nhận tên, định nghĩa và số bài của nhãn này, không nhận lý do theo từng lượt. Mỗi vòng cũng chỉ đọc 16 lượt sai trên 150.

**Đo được gì về truy vấn (chỉ số gộp, không in nội dung):** agent viết trung bình khoảng 2.35 cụm trong ngoặc kép mỗi truy vấn và đưa cả chuỗi vào BM25 lấy top-5. Với BM25, một truy vấn trộn nhiều đầu mối thường trả về tài liệu khớp vừa vừa với tất cả, thay vì tài liệu khớp mạnh với một đầu mối.

**Nếu tự sửa, tôi sẽ làm phía harness, không phải lời khuyên:**
- *Tách truy vấn (query fan-out).* Tiền điều kiện: lời gọi `search` có từ 2 cụm trong ngoặc kép trở lên, hoặc dài hơn N từ. Hành động: harness chạy thêm từng cụm riêng (và truy vấn gốc), gộp thứ hạng (ví dụ reciprocal rank fusion), trả về top-k đã gộp kèm docid. Agent vẫn gọi đúng một công cụ như cũ, chỉ có kết quả rộng hơn. Đây là nguyên tắc chung cho mọi công cụ tìm kiếm dạng từ khoá, không dính tới bài nào.
- *Đo được bằng chỉ số mới:* thêm đặc trưng `distinct_docs_seen` (số docid khác nhau đã xuất hiện trong kết quả). Đặc trưng này có sẵn trong trajectory, cho phép nêu giả thuyết "agent thấy nhiều tài liệu khác nhau hơn" và đo nó trên từng cặp nhánh.
- *Tín hiệu độ tin cậy:* §24 cho thấy 132/150 lượt sai tự chấm độ tin cậy ≤ 30, còn 29/30 lượt đúng chấm ≥ 70. Đây là tín hiệu dừng tốt nhất hiện có, nhưng pipeline không đo nó. Thêm đặc trưng `stated_confidence` thì một ý kiểu "độ tin cậy thấp và còn ngân sách → chưa nhận câu trả lời, tìm tiếp bằng truy vấn đã tách" sẽ nêu và đo được.

**Pipeline có tự tìm ra được không:** với tính năng cụm lỗi (§25), người gán nhãn đọc được tham số gọi đầy đủ (tới 500 ký tự), nên có khả năng đặt ra cụm kiểu "truy vấn gộp quá nhiều đầu mối, kết quả không chứa tài liệu liên quan", và proposer có thể nhắm cụm đó bằng `mode:<cụm>` mà không cần đặc trưng đếm. Lệnh cấm lời khuyên vẫn còn, nên proposer phải tự nghĩ ra cách làm phía harness như tách truy vấn. Chưa kiểm chứng: lượt này chỉ chạy AppWorld theo yêu cầu.

## 26. Gắn nhãn theo "lỗi quyết định" thay vì theo hậu quả (prompt mới, chạy thử offline)

### 26.1 Vì sao sửa

Cụm ở §25 và nhãn ở các lượt trước phần lớn đặt tên theo **hậu quả**: `premature_task_abandonment`, `premature_incomplete_data`, `premature_search_abandonment`. Gần như lượt sai nào cũng kết thúc bằng một câu trả lời sai, thiếu hoặc dừng sớm, nên tên kiểu này đúng với mọi lượt mà không chỉ ra được nên sửa gì. Proposer nhận "dừng sớm" thì đề xuất chặn dừng hoặc mở thêm tài liệu, như đã thấy trong 23 ý tìm kiếm ở §25.4.

### 26.2 Prompt mới (`baselines/b4_cluster.py`, commit `97bade2`)

Với mỗi lượt sai, người gắn nhãn phải trả lời:
1. **step:** bước quyết định, tức bước sớm nhất mà sau đó lượt chạy không thể đúng nếu agent không đổi hướng. Prompt ghi rõ: kết thúc sai không phải là lỗi, hãy tìm cái dẫn tới nó.
2. **did:** agent đã làm gì ở bước đó, nói theo giao diện công cụ: công cụ nào, đối số có dạng gì (đặt hay bỏ đối số nào, gộp điều kiện ra sao, lặp lại gì). Không nêu thực thể của bài.
3. **evidence:** điều gì nhìn thấy được trong lượt chạy lúc đó cho biết đây là lỗi: kết quả agent nhận được và agent xử lý nó thế nào.
4. **better:** hành động nào tốt hơn ở bước đó.
5. **cluster:** xếp theo **lỗi** (did + evidence), không theo hậu quả. Cụm mới phải có thêm **signature**: một điều kiện mà chương trình kiểm tra được trên lượt chạy tính tới bước quyết định, chỉ dựa vào hành động và kết quả công cụ.

Các phần còn lại:
- **Giám khảo** đo `mode:<cụm>` nay nhận cả signature và phải nêu bước xảy ra lỗi.
- **Proposer** thấy signature và các ví dụ "did / evidence / better" của từng cụm. Prompt HYP nói rõ cơ chế có thể kiểm tra signature lúc chạy và thay đổi những gì harness đưa ra, hiển thị hoặc làm ở chỗ đó (vẫn cấm lời khuyên).
- **Bản tóm tắt lượt chạy** nay đánh số bước, giữ 8 sự kiện đầu (chỗ hướng đi thường được chốt) cùng các sự kiện cuối, và hiện kết quả công cụ 600 ký tự thay vì 300. Mỗi lần gọi đọc 4 lượt thay vì 6.

Prompt không chứa ví dụ nào lấy từ phân tích của tôi (lật trang, truy vấn gộp...). Như vậy nếu cụm tìm ra những lỗi này thì đó là do model đọc lượt chạy, không phải do tôi gợi ý.

### 26.3 Chạy thử offline trên lượt sai H0 (train)

| Benchmark | Cụm cũ (lớn nhất) | Cụm mới |
|---|---|---|
| AppWorld (55 lượt sai) | `documentation_and_auth_recovery` 22, `premature_incomplete_data` 16, `premature_task_abandonment` 14, 2 cụm nhỏ (§25) | `repeated_partial_query` 17 (lặp lại truy vấn đã trả kết quả bị cắt mà không đổi gì), `truncated_result_mutation` 16 (hành động dựa trên kết quả bị cắt), `protected_call_without_auth` 14 (gọi API cần đăng nhập mà không truyền token), `incomplete_library_enumeration` 8 (chỉ lấy trang đầu của danh sách phân trang, coi như đủ) |
| BCP (127 lượt sai) | `premature_search_abandonment` 14 bài, `repeated_search_results` 1 (nhãn từ 16 lượt được đọc, `b4v7q`) | `overloaded_search_queries` 105 (gộp nhiều đầu mối độc lập vào một truy vấn rộng thay vì tách đầu mối đặc trưng rồi thu hẹp dần), `repeats_uninformative_search` 13, `unproductive_source_reuse` 9 |

Bước quyết định có trung vị là bước 8 trên AppWorld và **bước 1** trên BCP: truy vấn đầu tiên đã chốt hướng đi.

Kiểm tra giám khảo (đọc không biết kết quả) xem nó có phân biệt được hay không:

| Cụm | Lượt đúng bị chấm là có lỗi | Thành viên cụm | Lượt sai khác |
|---|---|---|---|
| AppWorld `incomplete_library_enumeration` | 3/15 | 7/8 | 2/10 |
| AppWorld `protected_call_without_auth` | 2/15 | 12/14 | 3/10 |
| BCP `overloaded_search_queries` | **10/15** | 15/15 | 10/10 |

**Đọc kết quả:**
- **Prompt mới tìm ra đúng hai lỗi chính của §24 mà không cần chỉ số nào làm tay.** Trên AppWorld là lật trang và thiếu token. Trên BCP là truy vấn gộp quá nhiều đầu mối, đúng điều §25.4 nói là pipeline chưa bao giờ thấy.
- **Trên AppWorld, cụm phân biệt tốt lượt đúng với lượt sai** (lượt đúng chỉ 2–3/15 bị chấm là có lỗi). Dùng làm thước đo hành vi được.
- **Trên BCP, lỗi truy vấn gộp có ở cả 10/15 lượt đúng.** Đây là cách model này luôn tìm kiếm, và lượt đúng là những lần truy vấn gộp may mắn trúng. Cụm này vẫn đo được một bản sửa có làm giảm truy vấn gộp hay không. Nhưng không có bằng chứng rằng giảm nó sẽ làm tăng số câu đúng: điều đó chỉ thử nhánh mới trả lời được.
- Một cụm chiếm 105/127 lượt là khá thô. Nếu chạy thật nhiều vòng thì có thể cần tách nhỏ hơn.
- **Bỏ các đề xuất ở §25.4 là thêm chỉ số `distinct_docs_seen`, `stated_confidence` và tín hiệu "tài liệu đúng đã xuất hiện".** Ba cái này đặc thù cho BCP và vi phạm nguyên tắc khái quát. "Tách truy vấn" cũng không cài vào pipeline, vì đó là việc proposer phải tự nghĩ ra từ cụm `overloaded_search_queries`.

### 26.4 Điểm yếu của B1–B3 và B4 đã có gì để khắc phục (cập nhật tới §26)

| Điểm yếu (thấy trong log) | B4 đã có gì | Đã thấy hiệu quả chưa |
|---|---|---|
| **Chọn theo điểm val/train nhỏ nên bị nhiễu lừa.** B1 seed 1: val 26,7% nhưng test 19%. B3 chọn theo 4–8 bài đúng trên 30. | So từng cặp nhánh rẽ từ cùng một điểm của cùng một lượt chạy, rồi kiểm định dấu. Gộp phải qua cả train lẫn val. Ưu tiên rẽ nhánh ở bài "lúc được lúc không" (`B4_LEARN`). | Có: c1 và c6 ở `b4v7r` thắng train nhưng val không xác nhận, nên không gộp nhầm. Điểm yếu mới là val quá ít lượt chạm tới các bản sửa hẹp (§25). |
| **B1 gần như chỉ sửa lời nhắc trong prompt.** | Cấm lời khuyên và chuỗi dài. Có 12 loại sửa cấu trúc, mỗi vòng giao một nhóm loại. | Có, nhưng phần lớn ý vẫn xoay quanh "chặn dừng sớm" (9/13 lần gộp ở các lượt v7). §26 nhắm vào chỗ này: lỗi được đặt tên theo hành động chứ không theo hậu quả. |
| **B1 có giả thuyết dính chi tiết của bài.** | Cổng khái quát (không mã bài, không nội dung đề, không đáp án). Giả thuyết phải ở dạng "điều kiện chạy được trên trajectory → hành động" và điều kiện phải xảy ra đủ thường. | Có: chưa ý nào bị phát hiện dính thực thể. |
| **B1 sinh code chết hoặc code crash, mất cả vòng.** | Lint, chạy lại khô trên các lượt đã lưu, báo "DEAD CODE" kèm dấu vết, cho viết lại một lần. | Một phần: vòng 3 `b4v7r` vẫn có 3/5 ý chết, vì đặt điều kiện vào công cụ không tồn tại. |
| **B2 đứng yên 15 vòng vì giám khảo không chịu chỉ ra thủ phạm.** | Không cần thủ phạm. Mọi lượt sai đều được xếp cụm (§25), bằng chứng đến từ rẽ nhánh. | Có: lượt nào cũng ra giả thuyết. |
| **B2 thăng hạng biến thể có hại vì không so reward.** | Kiểm định thắng/thua trên nhánh, cổng chặn làm hỏng bài đang đúng (`B4_SENTINEL`), hội đồng 3 phiếu. | Có: cổng chặn bắt được c1 ở `b4v7q` và c5 ở `b4v7r` (5/8 bài luôn đúng bị hỏng). |
| **B3 tốn token gấp 1,6–2,2 lần.** | Chi phí là một chỉ số được đo trên từng cặp nhánh. Có thể gộp vì lý do tiết kiệm nếu không làm mất bài. | Có: v7k đạt 36% BCP với 72k token/bài (luật chặn bước cần 215k). |
| **B3 có canary quá lỏng.** | Phải chứng minh hành vi đổi đúng như dự đoán, rồi qua hội đồng và val. | Có. Mặt trái là ý có lợi theo cách khác dự đoán bị bỏ (§23). Thước đo cụm (§25) giúp một phần. |
| **Nhãn lỗi chung chung, không chỉ ra nên sửa gì** (cả B1–B3 lẫn B4 cũ: "dừng sớm", "tìm kém"). | §25: đọc mọi lượt sai, dùng cụm làm thước đo. §26: xếp theo lỗi ở bước quyết định, có signature. | Mới thử offline: tìm ra lật trang, thiếu token, truy vấn gộp. Chưa chạy vòng thật. |

Còn thiếu:
- Val ít lượt chạm tới các bản sửa hẹp.
- Code chết khi điều kiện dựa vào công cụ không có.
- Trên BCP, lỗi truy vấn gộp có cả ở lượt đúng nên chưa chắc sửa được thì tăng điểm.

## 27. Gắn nhãn theo lỗi quyết định + luật bộ công cụ + 3 lượt val H0 — AppWorld, 3 vòng, seed 0 (`b4v7s`)

Code so với `b4v7r` (§25):
- **Gắn nhãn theo lỗi ở bước quyết định** (prompt §26.2, commit `97bade2`). Mỗi cụm có định nghĩa và một *signature* kiểm tra được trên lượt chạy. Giám khảo của thước đo `mode:<cụm>` đọc cả signature.
- **Luật bộ công cụ** (commit `a8730d9`). Prompt giả thuyết và phản hồi "DEAD CODE" nêu đúng danh sách công cụ mà model được gọi trong các lượt đã lưu. Trên AppWorld chỉ có `execute_python`: tài liệu API và đăng nhập đều nằm trong code Python, không phải công cụ riêng.
- **Thêm 2 lượt H0 trên val** (`H0_VAL_ROLLS=3`). Val có 90 lượt H0 thay vì 30, mỗi lượt rẽ 2 nhánh (`B4_K_VAL=2`), nên một bản sửa có thể chạm tới 180 nhánh val. H0 val: 21/30, 16/30, 20/30 (tổng 57/90 = 63%).

### 27.1 Sổ cụm

88 lượt sai train được xếp vào 6 cụm. Lần gắn nhãn đầu dùng lượt sai H0, các vòng sau thêm lượt sai của harness đã gộp. Tên cụm đều gọi đúng hành động sai, không có cụm nào kiểu "dừng sớm" như ở §25.

| Cụm | Lượt sai | Signature (tóm tắt) |
|---|---|---|
| `act_on_truncated_results` | 38 | kết quả công cụ có dấu bị cắt hoặc bỏ bớt, sau đó agent hành động mà không lấy lại bản đầy đủ |
| `uses_partial_lookup_results` | 18 | lời gọi tra cứu có giới hạn trang, agent dùng như tập đầy đủ mà không gọi trang sau |
| `misuses_documented_arguments` | 15 | tài liệu ghi một tên hoặc dạng tham số, lời gọi sau dùng cái khác và không sửa |
| `drops_auth_token` | 12 | đăng nhập trả token, lời gọi cần quyền sau đó thiếu token và bị lỗi xác thực |
| `unsupported_sufficiency_decision` | 4 | (thêm ở vòng 2) chọn ứng viên mà bằng chứng của chính agent cho thấy chưa đạt ngưỡng |
| `missing_result_deduplication` | 1 | gộp kết quả nhiều truy vấn mà không bỏ bản ghi trùng |

### 27.2 Kết quả từng ý

| Vòng | Ý | Thước đo | Hành vi đổi? | Train thắng/thua | Val thắng/thua (nhánh) | Kết cục |
|---|---|---|---|---|---|---|
| 1 | c1 khởi động lại khi kẹt | `stale_streak` ↓ | ngược (4 đúng / 12 ngược) | 9/9 | – | cổng hồi quy chặn (5/8 bài luôn đúng hỏng) |
| 1 | c2 chỉ mục bằng chứng | `stale_streak` ↓ | ngược | 19/11, p=0.10 | – | hội đồng bỏ |
| 1 | **c3 bản tóm bằng chứng trong ngữ cảnh** | `distinct_results` ↑ | không rõ (p=0.14) | **22/6, p=0.002** | **19/11 (170)** | **GỘP** (gộp train+val 41/17, p=0.001) |
| 2 | c4 tìm trong kết quả | `repeat_ratio` ↓ | không | 2/5 | – | không hiệu quả |
| 2 | c5 sửa tham số sau lỗi | `n_errors` ↓ | – | – | – | code chết |
| 2 | c6 kiểm tra sau lỗi | `mode:misuses_documented_arguments` ↓ | ngược (0.25→0.39) | 14/6, p=0.058 | **5/19 (150)** | hội đồng nhận, **val bác** |
| 2 | c7 chặn kết luận thiếu căn cứ | `mode:unsupported_sufficiency_decision` ↓ | – | – | – | code chết |
| 2 | c8 sửa lời gọi Python | `n_errors` ↓ | – | 0/0 (chạm 1 lượt) | – | quá hẹp |
| 3 | c9 tra bằng chứng | `distinct_results` ↑ | **có** (p=0.029) | 8/8 | – | cổng hồi quy chặn |
| 3 | c10 thăm dò gộp nhiều trang | `mode:uses_partial_lookup_results` ↓ | không | 15/12 | – | nhiễu, hội đồng bỏ |
| 3 | c11 công cụ soi kết quả bị cắt | `mode:act_on_truncated_results` ↓ | – | – | – | code chết |
| 3 | c12 tra bằng chứng (bản 2) | `mode:uses_partial_lookup_results` ↓ | không | 17/8, p=0.054 | **6/14 (168)** | hội đồng nhận, **val bác** |

**c3 làm gì** (`context_mgmt/c3_retain_evidence_context`, 116 dòng, không chứa thực thể của bài):
- Mỗi bước, ngay sau câu hỏi, nó chèn một khối "Retained evidence digest". Khối này gồm tối đa 20 kết quả công cụ khác nhau gần nhất (bỏ bản trùng theo hash), mỗi kết quả tối đa 480 ký tự.
- Mỗi kết quả được gắn nhãn `[error]`, `[incomplete]` hoặc `[pagination]` nếu chứa các từ tương ứng (error/failed, truncated/partial, next page/page N/cursor…).
- Phần còn lại giống H0: cửa sổ 30 lượt, kết quả bị cắt ở 6000 ký tự.
- H0 hầu như không phải bỏ lượt nào (trung vị khoảng 15 bước, dưới mức 30). Vì vậy tác dụng của c3 không đến từ việc "giữ lại thứ bị cắt" như giả thuyết nói, mà từ một **bản tóm nhắc lại các kết quả đã thấy, có đánh dấu chỗ thiếu, chỗ lỗi và chỗ còn trang sau**.
- Các nhãn đó khớp đúng hai cụm lớn nhất (`act_on_truncated_results`, `uses_partial_lookup_results`), và cơ chế của c3 có nhắc tới "truncation markers, pagination cues". Mối liên hệ với sổ cụm là có thể, nhưng chưa chứng minh.

### 27.3 Test

| | Test (99 bài) | Bước | Token/bài |
|---|---|---|---|
| H0 (= `b4v7m`, `b4v7q`, `b4v7r`) | 47/99 = 47.5% | 14.3 | 83k |
| **B4 `b4v7s` (H0 + c3)** | **60/99 = 60.6%** | 15.8 | 117k (+40%) |

- **So từng bài với H0:** 24 bài thắng, 11 bài thua (kiểm định dấu một phía p=0.02).
- **Gộp 3 biến thể của cùng một kịch bản** (33 kịch bản): thắng 13, thua 5 (p=0.048).
- **Ước lượng trước bằng nhánh:** c3 chạm 95/99 lượt test, rẽ 190 nhánh, kết quả 43/23 (p=0.009), ước 57.6%. Lần chạy lại đầy đủ cho 60.6%, khớp chiều với ước lượng.
- Đây là **lần đầu B4 vượt H0 trên AppWorld**, sau 5 lượt chạy không gộp được gì (`b4v7l`, `b4v7m`, `b4v7q`, `b4v7r` và lượt `medium` §19).

**Chi phí tiến hoá:** 119M token, gấp 2.75 lần `b4v7r` (43M). Lý do là val lớn gấp 3 và cả ba ý lên tới val (c3, c6, c12) đều chạm hầu như mọi lượt (150–170 nhánh val mỗi ý). Ngoài ra còn 60 lượt H0 val thêm và 329 lần gọi giám khảo (`b4v7r`: 406).

### 27.4 Đọc kết quả

**Đọc kết quả:**
- **Val lớn hơn đã làm đúng việc của nó, theo cả hai chiều.** Nó xác nhận c3 (19/11) và bác hai ý mà hội đồng đã nhận trên train với p≈0.055: c6 (5/19) và c12 (6/14). Nếu val chỉ có 30 lượt như trước, hai ý này có thể đã không bị bác rõ như vậy. Bài học: thắng trên train với p≈0.05 chưa đáng tin. Ý được gộp có p=0.002.
- **Code chết giảm (3/12, `b4v7r` là 4/12), và không còn ý nào đặt điều kiện vào công cụ không tồn tại.** Luật bộ công cụ đã chặn được đúng lỗi của c10/c11 ở `b4v7r`. Ba ý chết còn lại:
  - c5: mẫu lỗi tham số mà nó bắt không khớp lượt nào;
  - c7: kiểm tra câu trả lời cuối, trong khi AppWorld kết thúc bằng một lời gọi trong code, nên có lẽ không có câu trả lời riêng để kiểm;
  - c11: chờ dấu "bị cắt" trong kết quả, nhưng dấu đó gần như không xuất hiện khi giới hạn là 6000 ký tự.
- **Thước đo cụm chưa tạo ra thắng lợi nào.** 5/12 ý dùng `mode:`, nhưng không ý nào làm cụm của mình giảm đúng như dự đoán. c6 còn làm cụm tăng. Ý được gộp dùng chỉ số đếm, và chỉ số đó cũng không đổi rõ. Như vậy lần gộp này lại là kiểu "có lợi theo cách khác với dự đoán", được nhận nhờ lối "benefit: success" của hội đồng chứ không nhờ cơ chế đo hành vi.
- **Cẩn trọng khi đọc con số 60.6%:**
  - (a) Chỉ có một seed.
  - (b) H0 test chỉ có 1 lượt, và H0 dao động mạnh giữa các lượt (train 35/27/33 trên 50). Kiểm định từng cặp (p=0.02) đã tính tới nhiễu này phần nào, nhưng chạy thêm một lượt test cho H0 hoặc B4 sẽ chắc hơn.
  - (c) c3 tốn thêm 40% token. Chưa có đối chứng cùng chi phí cho AppWorld.
  - (d) Chưa tách được phần lợi đến từ bản tóm hay từ các nhãn `[pagination]`/`[incomplete]`. Một đối chứng rẻ là chạy c3 bỏ nhãn.
- **Còn thiếu so với §26.4:**
  - Val giờ đủ cho các ý rộng, nhưng lượt này chưa có ý hẹp nào lên tới val, nên chưa biết val 90 lượt có đủ cho chúng không.
  - Thước đo cụm cần một ý thực sự làm cụm giảm mới chứng minh được giá trị của nó.
