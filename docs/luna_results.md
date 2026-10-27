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

Ghi chú nhỏ, chưa sửa vì không ảnh hưởng: `baselines/b3_memo.py` vẫn ghi `MODEL = "inclusionai/ling-3.0-flash"`, nhưng `ChatShim` bỏ qua tham số model nên mọi lệnh gọi đều đi tới model cấu hình trong `.env`.

## 5. Dữ liệu

- `results/medium_luna/*.jsonl`: bản ghi từng episode (H0 train/val/test; B1/B2/B3 tiến hóa và test).
- `results/medium_luna/baseline_runs.jsonl`: dòng tóm tắt mỗi baseline. Với ALFWorld, dòng cuối là sau khi chạy lại các episode lỗi (`redo_test_errors`).
- `results/medium_luna/runs/<method>/<bench>/`: workspace tiến hóa (log, candidate, bundle, bank).
- `results/medium_luna/logs/`: log từng tiến trình, gồm cả `alfworld_<method>_redo.log`.
- Trajectory và thư mục `runs/` lớn không được commit (gitignore), giống lần chạy ling.
