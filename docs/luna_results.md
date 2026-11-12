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
- **Lượt chạy này không cho thấy graph có ích, và cũng không đo được graph có hại trên test.** Khác biệt test (32% so với 22%) đến từ vòng 1, khi sổ còn rỗng nên hai cấu hình giống hệt nhau: hai lượt chạy gộp hai sửa đổi khác nhau, và c4 yếu hơn hẳn (train 3 thắng / 0 thua). Đây là độ dao động giữa các lần chạy của chính pipeline, lớn hơn mọi hiệu ứng của graph.
- **Ở vòng 2–3, nơi graph có nội dung, tỉ lệ ứng viên hỏng ở code không đổi** (9/10 so với 6/7). Proposer có dùng graph (phân tích vòng 2 nhắc đúng hai hướng có lợi và tránh cách đã thất bại), nhưng chỗ nghẽn là bước viết code: 5 DEAD CODE, 2 NOT BUILT (ghi cứng tên tool), 4 INEFFECTIVE trên 14 ứng viên.
- **Tiêu chí gộp còn lỏng với lợi ích nhỏ:** c4 được gộp với 3 thắng / 0 thua trên train; chạy lại toàn bộ trên test cho 7 thắng / 9 thua. Ước lượng rẽ nhánh (26%) và chạy lại toàn bộ (22%) chênh nhau 4 điểm, đúng cỡ nhiễu ±5 đã biết.
- **Hệ quả cho ba lượt v7:** test 33%, 32%, 22%. Kết luận "cải thiện khoảng 8 điểm, nhất quán" ở §14 phải hạ xuống: 2 trên 3 lượt hơn H0, 1 lượt không hơn; trung bình 29%.
