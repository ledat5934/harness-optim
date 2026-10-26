# Kết quả lần chạy MEDIUM: pipeline, số liệu và nhận xét từng baseline

Ngày chạy: 2026-10-25 → 2026-10-26. Mã được chốt ở commit `82eaa0d`; trong lần chạy này không sửa gì thêm, chỉ chạy và ghi lại các lỗi phát hiện được (mục 5). Số liệu tính bằng `python scripts/analyze_medium.py` từ `results/medium/*.jsonl`; bảng đầy đủ ở `results/medium/analysis.md`. Model `inclusionai/ling-3.0-flash` được dùng cho agent, proposer và judge của BrowseComp-Plus. **Tổng chi phí: $TOTAL_USD** (gồm cả các lượt chạy đã hủy).

**Giao thức MEDIUM:**
- 1 seed, 5 vòng tiến hóa;
- 50 tác vụ train × K=3 roll, 30 tác vụ val, 2 tác vụ kiểm tra (canary/smoke) mỗi vòng;
- tập test cố định ~100 tác vụ mỗi benchmark (`benchmarks/<bench>/test100.json`):
  - ALFWorld: 100/134 `valid_unseen`, phân tầng theo loại;
  - AppWorld: 33 scenario `test_normal` = 99 tác vụ;
  - BrowseComp-Plus: 100 câu held-out.

Quy ước tính:
- Episode lỗi hạ tầng tính là thất bại; episode HTTP 402 (key hết tiền) bị loại khỏi mẫu.
- McNemar: kiểm định chính xác, hai phía, chỉ trên các tác vụ mà đúng một trong hai phương pháp thành công.

## 1. Ý tưởng pipeline của từng baseline (gốc và bản port)

Cả ba baseline cùng xuất phát từ harness H0: 5 slot (`agent_loop`, `context_mgmt`, `tool_policy`, `memory`, `verifier`), mỗi slot là một file Python trong `h0/variants/<slot>/`. `bundle.json` chọn biến thể cho từng slot; không có thì dùng `default`.

### B1 Meta-Harness: tiến hóa mã tự do, chọn trên val
- **Gốc (paper + repo):** mỗi vòng, một proposer dạng coding-agent đọc toàn bộ cây ứng viên trước đó, mã nguồn, điểm và trajectory thất bại, rồi viết một harness mới (sửa tự do). Ứng viên qua validate → smoke → chấm trên tập search; giữ ứng viên tốt nhất (incumbent) và lưu lại toàn bộ lịch sử để proposer học từ đó.
- **Port:**
  - proposer là một lời gọi LLM theo SKILL của repo gốc, nhận cây ứng viên, mã của pool, tóm tắt trajectory (kể cả tác vụ sai) và trả về các file sửa;
  - cổng: static gate (import, registry, toy run), smoke trên 2 tác vụ train, cổng `unselected_variants` (biến thể mới phải được `bundle.json` chọn);
  - chấm trên 30 tác vụ val; incumbent là ứng viên có val cao nhất.
- **Khác gốc:** proposer là 1 lời gọi chứ không phải agent nhiều bước có shell; tập search nhỏ (30 val).

### B2 ModularRSI: đề xuất theo module, cổng nhiều tầng, composer chọn theo tác vụ
- **Gốc:**
  - **phân tích:** router phân loại lỗi theo lens (slot); điều tra tương phản thành công/thất bại; backlog các đề xuất mở; gom cụm theo niche;
  - **sinh và lọc biến thể:** implementer viết biến thể mới (chỉ thêm, không sửa default); cổng static, niche-dedup, reviewer, kiểm tra crash khi chạy;
  - **thăng hạng và dùng:** thăng hạng chỉ dựa vào cổng, không so reward; ở test, composer LLM đọc mô tả biến thể và chọn biến thể cho từng tác vụ;
  - **bằng chứng:** cửa sổ sau học từ các roll của thư viện hiện tại.
- **Port:** giữ đúng các bước trên (`niche.py` vendored nguyên văn).
  - Bằng chứng cửa sổ 1 là roll H0 chung; các cửa sổ sau là K=3 roll của thư viện hiện tại trên lô train mới.
  - `lens_of` được tích lũy qua các vòng.
- **Khác gốc:** không có bước `confirm` và cổng hành động; mỗi bước LLM là 1 lời gọi.

### B3 MemoHarness: ngân hàng kinh nghiệm + controller viết lại bundle + thích nghi theo ca
- **Gốc:**
  - harness là một "Codex bundle": `AGENTS.override.md`, `policy.json` (các chiều D1–D6), `.memoharness/playbook.md` và `memory.md`;
  - mỗi vòng, harness hiện tại chạy trên một lô train; kết quả được nạp vào ngân hàng kinh nghiệm; một LLM chưng cất ra pattern toàn cục và làm mới các tài liệu hỗ trợ;
  - controller viết lại bundle; bundle mới phải qua publish gate rồi canary (so với baseline trên vài ca);
  - chọn iteration có reward train tốt nhất, không dùng val;
  - ở test, `adapt_for_case` điều chỉnh cấu hình theo từng ca dựa trên ngân hàng kinh nghiệm.
- **Port** (lần này):
  - vendored nguyên văn `runtime/codex_bundle.py`, `controllers/codex_bundle.py`, `controllers/local_cli.py` (commit `4c3da18`);
  - `BundleController` chỉ thay phần gọi CLI bằng 1 lời gọi LLM ghi các khối `### FILE:`;
  - canary dùng đúng 3 luật gốc; chọn iteration theo reward train;
  - nội dung bundle được đưa vào system prompt.
- **Khác gốc:**
  - H0 chỉ có ba núm runtime thật là `D3.temperature`, `D3.max_tokens` và `D5.history_keep`; các chiều còn lại chỉ có tác dụng qua chữ trong prompt;
  - canary chỉ có 2 ca.

## 2. Kết quả test

| benchmark | H0 | B1 Meta-Harness | B2 ModularRSI | B3 MemoHarness |
|---|---|---|---|---|
| ALFWorld (100) | 73,0% | **86,0%** (+18/−5, p = 0,011) | 60,0% (+8/−21, p = 0,024) | 65,0% (+9/−17, p = 0,17) |
| BrowseComp-Plus (100) | 17,0% | 21,0% (+8/−4, p = 0,39) ¹ | **23,0%** (+14/−8, p = 0,29) | 18,0% (+7/−6, p = 1,0) |
| AppWorld TGC (99) | 6,1% | 6,1% (+2/−2, p = 1,0) | B2_AW | **8,1%** (+2/−0, p = 0,5) |

¹ Harness cuối của B1 trên BrowseComp-Plus có hành vi y hệt H0 (lỗi 1, mục 5). 21% chính là kết quả của một lần chạy lại H0: bản chạy lại H0 trong `aborted_unselected/` cũng đạt 21%.

Chi phí mỗi episode test (USD) và số token:

| benchmark | H0 | B1 | B2 | B3 |
|---|---|---|---|---|
| ALFWorld | 0,00066 (62,6k) | **0,00054** (51,4k) | 0,00081 (69,2k) | 0,00111 (140,9k) |
| BrowseComp-Plus | 0,00471 (526k) | **0,00437** (505k) | 0,00482 (481k) | 0,00699 (478k) |
| AppWorld | 0,00198 (186k) | **0,00190** (185k) | B2_AW_COST | 0,00327 (275k) |

Chi phí tiến hóa (proposer + episode train/val/canary), tính bằng USD:

| benchmark | B1 | B2 | B3 |
|---|---|---|---|
| ALFWorld | 0,05 + 0,15 | 0,14 + 0,08 | 0,07 + 0,14 |
| BrowseComp-Plus | 0,08 + 0,42 | 0,21 + 0,56 | 0,12 + 0,75 |
| AppWorld | 0,06 + 0,19 | B2_AW_EVO | 0,10 + 0,39 |

**AppWorld chi tiết:**

| | H0 | B1 | B2 | B3 |
|---|---|---|---|---|
| TGC | 6,1% | 6,1% | B2_AW | 8,1% |
| SGC (33 scenario) | 6,1% | 3,0% | B2_SGC | 6,1% |
| tỉ lệ unit test đạt trung bình | 50,1% | 52,9% | B2_UT | **58,3%** |
| có gọi `task_completed` | 54/99 | 55/99 | B2_TC | **68/99** |

**ALFWorld theo loại tác vụ** (số đúng / tổng):

| | light | simple | clean | cool | heat | two obj |
|---|---|---|---|---|---|---|
| H0 | 12/13 | 15/18 | 19/23 | 13/16 | 10/17 | 4/13 |
| B1 | 13/13 | 17/18 | 17/23 | 14/16 | **15/17** | **10/13** |
| B2 | 11/13 | 12/18 | 16/23 | 7/16 | 9/17 | 5/13 |
| B3 | 12/13 | 13/18 | 13/23 | 11/16 | 12/17 | 4/13 |

**BrowseComp-Plus:** B3 có nhiều câu không nộp đáp án nhất (22/100, so với H0 13, B1 12, B2 17). Số lần gọi `search` trung bình của cả bốn đều khoảng 20–22.

### Độ nhiễu giữa hai lần chạy

Cùng một harness có hành vi y hệt H0, chạy lại trên cùng các tác vụ:

| benchmark | H0 | lần chạy lại | số tác vụ đổi kết quả |
|---|---|---|---|
| ALFWorld | 73% | 69% | 30/100 (13 sang đúng, 17 sang sai) |
| BrowseComp-Plus | 17% | 21% | 10/100 (7 / 3) |
| AppWorld | 4,5% | 4,5% (66 tác vụ) | 0/66 |

Chênh lệch tổng ±4 điểm vì thế là nhiễu thuần túy. Kết quả từng tác vụ trên ALFWorld cũng rất ngẫu nhiên. Một ví dụ khác: trong B2 ALFWorld, 46 tác vụ mà composer chọn toàn biến thể `default` (tức chạy y hệt H0) vẫn chỉ đúng 25 so với 32 của H0.

### So với các bản port cũ (đã thay thế, lưu để đối chiếu)

| benchmark | B2 cũ (`b2_v1/`) | B2 mới | B3 cũ chỉ đổi cấu hình (`b3_configonly/`) | B3 mới (Codex bundle) |
|---|---|---|---|---|
| ALFWorld | 70% | 60% | 81% | 65% |
| BrowseComp-Plus | 15% | 23% | 18% | 18% |
| AppWorld | 4,0% | B2_AW | 5,8% (69 tác vụ) | 8,1% |

- **B2 cũ:** các biến thể được thăng hạng nhờ val nhưng composer gần như không chọn chúng, nên harness cuối thực chất là H0.
- **B3 cũ:** chỉ tìm kiếm trên D1–D6 và không viết bundle. ALFWorld 81% của nó (ít token: 52k mỗi episode) tốt hơn bản bundle (65%, 141k mỗi episode). Tuy vậy cả hai chênh lệch với H0 đều không có ý nghĩa thống kê.

## 3. Diễn biến tiến hóa

- **ALFWorld**
  - **B1:** val theo vòng là 67, 57, 63, 57, 70%. Incumbent cuối là r5 (cha r1), thêm khoảng 20 dòng vào `agent_loop/default.py`: sau nhiều quan sát "Nothing happens" liên tiếp thì nhắc agent gọi `admissible_commands()`. Đây là thay đổi chung, rút ra từ trajectory thất bại. Cải thiện lớn ở heat (10→15) và two-obj (4→10).
  - **B2:** r2 thăng hạng `verifier/goal_satisfied`, r5 thăng hạng `context_mgmt/milestone_compressor`; r1 và r3 không có đề xuất mở, r4 không có biến thể nào qua cổng. Ở test, composer chọn `goal_satisfied` cho 54/100 tác vụ và `milestone_compressor` cho 9/100. Trên 54 tác vụ dùng `goal_satisfied`, B2 đúng 35 so với 41 của H0.
  - **B3:** canary loại r2 và r3 (reward −0,5 trên 2 ca). Chọn r4 vì train 83,3%, nhưng chính harness r1 khi chạy lại trên train dao động 67–77%, nên việc chọn theo 1 roll trên 30 tác vụ train rất nhiễu. Ở test, `adapt_for_case` viết lại đoạn chiến lược cho phần lớn các ca, đẩy số token lên gấp đôi (141k so với 63k).
- **BrowseComp-Plus**
  - **B1:** r2 thắng val (20% so với 13%), nhưng thay đổi của r2 không bao giờ chạy (lỗi 1, mục 5); r3 crash ở smoke; r4 proposer không trả ứng viên.
  - **B2:** r2 và r3 cùng thăng hạng `verifier/completeness` (r3 ghi đè cùng tên, lỗi 2, mục 5); r4 crash ở bước kiểm tra chạy; r5 thăng hạng `agent_loop/todo_plan`. Composer chọn `todo_plan` cho 99/100 và `completeness` cho 97/100 tác vụ test, nên đây thực sự là một harness khác H0. Đây là kết quả tốt nhất trên BrowseComp-Plus (+6 điểm), nhưng chưa vượt nhiễu.
  - **B3:** canary chấp nhận cả 5 vòng. Train theo vòng là 20, 27, 20, 20, 17%; chọn r2 (chiến lược "chia câu hỏi thành câu hỏi con, kiểm chứng từng ý").
- **AppWorld**
  - **B1:** r1 crash ở smoke (HTTP 400 `tool_call_id`); r2, r3, r5 lần lượt thành incumbent mới (val 6,7 → 10 → 13,3%); r4 bị loại ở validate. Harness cuối chọn bộ `auth_recovery` cho `agent_loop`, `tool_policy` và `verifier`: phát hiện lỗi 401/422 rồi chèn lời gọi `supervisor.show_account_passwords`. Val tăng nhưng test vẫn đúng bằng H0: 6/99.
  - **B2:** B2_AW_EVO_TEXT
  - **B3:** canary chấp nhận cả 5 vòng; train 10, 13, 10, 17, 23%; chọn r5. Trên test B3 tốt nhất ở mọi chỉ số phụ (unit test đạt 58%, gọi `task_completed` 68/99), nhưng TGC chỉ hơn H0 2 tác vụ.

## 4. Nhận xét từng baseline

### B1 Meta-Harness
**Điểm mạnh**
- Kết quả duy nhất có ý nghĩa thống kê trong cả lần chạy: ALFWorld 86% so với 73% (p = 0,011), lại rẻ nhất (ít bước hơn).
- Thay đổi nhỏ, đọc được và tổng quát, rút ra trực tiếp từ việc đọc trajectory thất bại. Cơ chế cây ứng viên cho phép tích lũy qua các vòng (r5 lấy r1 làm cha).
- Chi phí proposer thấp nhất (≤ $0,08 mỗi benchmark), vì mỗi vòng chỉ một lời gọi lớn.

**Điểm yếu**
- Chọn trên 30 tác vụ val nên dễ "thắng nhờ nhiễu": BrowseComp-Plus r2 và AppWorld r5 thắng val nhưng không cải thiện trên test.
- Tự do sửa mã nên dễ tạo mã chết hoặc mã crash: r2 BrowseComp-Plus không có hiệu lực; crash ở smoke trên AppWorld r1 và BrowseComp-Plus r3. Mỗi lần như vậy mất một vòng.
- Với benchmark mà H0 rất thấp (AppWorld 6%), tín hiệu val (1–4 tác vụ đúng) quá yếu để dẫn hướng.

### B2 ModularRSI
**Điểm mạnh**
- Pipeline có cấu trúc nhất: chẩn đoán theo lens, điều tra tương phản, niche-dedup, reviewer. Các biến thể có mục đích rõ và không đụng vào default.
- Trên BrowseComp-Plus, biến thể được dùng thật (`todo_plan` và `completeness` trên ~100% tác vụ) và cho kết quả tốt nhất (23%).
- Thư viện chỉ thêm, nên về nguyên tắc không phá được hành vi gốc. Composer có thể bỏ qua biến thể không hợp với tác vụ.

**Điểm yếu**
- Thăng hạng chỉ dựa vào cổng, không so reward, nên biến thể có hại vẫn vào thư viện. Ví dụ ALFWorld: `goal_satisfied` được chọn cho 54 tác vụ và trên nhóm đó kém H0 6 tác vụ; tổng 60% so với 73% (p = 0,024). Một phần chênh lệch là nhiễu (xem nhóm chạy `default`), nhưng không có cơ chế nào loại biến thể này.
- Chất lượng phụ thuộc composer: nó chỉ đọc mô tả, không có phản hồi về việc biến thể có giúp hay không.
- Tốn nhất ở phía proposer ($0,14–0,21 mỗi benchmark) vì có nhiều lời gọi LLM mỗi vòng. Nhiều vòng không ra gì ("no open proposal", "no variant passed").

### B3 MemoHarness
**Điểm mạnh**
- Học từ cả ca đúng lẫn ca sai qua ngân hàng kinh nghiệm và pattern chưng cất; bundle là văn bản nên dễ đọc và dễ kiểm tra.
- Có canary và publish gate nên ít khi ra harness hỏng; không vòng nào crash.
- AppWorld: tốt nhất ở TGC (8,1%) và mọi chỉ số phụ; agent hoàn thành nhiều bước hơn và gọi `task_completed` nhiều hơn.

**Điểm yếu**
- Đắt nhất ở test: $/episode cao hơn H0 40–70%, vì bundle dài trong system prompt, `max_tokens` cao, và `adapt_for_case` thêm lời gọi LLM ở mỗi ca. Trên ALFWorld số token tăng gấp đôi.
- Chọn iteration theo 1 roll train trên 30 tác vụ, không có val, nên rất nhiễu: ALFWorld chọn r4 (83% train) nhưng test chỉ 65%.
- Canary 2 ca quá yếu: trên BrowseComp-Plus và AppWorld nó chấp nhận mọi vòng, còn trên ALFWorld nó loại vì đúng 1 ca đổi kết quả.
- Trong H0 phần lớn D1–D6 chỉ là chữ trong prompt, nên điểm mạnh "tìm kiếm cấu hình" của bản gốc bị thu hẹp. Bản cũ chỉ đổi cấu hình lại tốt hơn trên ALFWorld (81%).
- Thích nghi theo ca đôi khi trả JSON hỏng: 3 ca trên ALFWorld, 7 trên BrowseComp-Plus và 10 trên AppWorld rơi về cấu hình chung.

### Nhận xét chung
- Với 1 seed và ~100 tác vụ test, chỉ B1 trên ALFWorld vượt nhiễu. Các chênh lệch còn lại (±2–6 điểm) nằm trong mức nhiễu đo được. Muốn kết luận chắc cần ≥3 seed hoặc tập test lớn hơn.
- Tập val/train nhỏ (30 tác vụ, 1 roll) là điểm yếu chung của cả ba khi chọn ứng viên. Phương pháp nào dựa vào nó nhiều thì càng dễ chọn nhầm.
- Trên AppWorld (H0 6%), model quá yếu nên không phương pháp nào cải thiện đáng kể; giới hạn nằm ở năng lực model, không ở harness.

## 5. Lỗi phát hiện trong mã đã chốt (chỉ ghi lại, không sửa)

1. **B1, cổng `unselected_variants` có lỗ hổng.** Cổng chỉ xét các file biến thể mới có lời gọi `register(...)` và bỏ qua các file `default.py`. Hai kiểu mã chết vì thế lọt qua:
   - file biến thể không đăng ký gì (`agent_loop/planning_agent_loop.py` ở BrowseComp-Plus r1/r2);
   - tên mới đăng ký ngay trong `default.py` (`context_mgmt/context_summary`), hoặc tùy chọn mới có mặc định tắt (`compress_dropped=False`).

   Hệ quả: harness cuối của B1 trên BrowseComp-Plus (r2) chạy y hệt H0.
2. **B2, implementer có thể ghi đè biến thể đã thăng hạng nếu dùng lại tên.** Regex cho phép chỉ loại `default.py`, còn `niche_reject` bỏ qua biến thể cùng tên. Đã thấy trên BrowseComp-Plus: `verifier/completeness.py` bị thay giữa r2 và r3.
3. **B2 thiếu bước `confirm` và cổng hành động** so với mã gốc. Implementer chỉ thêm biến thể, nên ít ảnh hưởng, nhưng là một khác biệt.
4. **Crash của ứng viên bị cổng bắt** (HTTP 400 `tool_call_id` ở B1 AppWorld r1; "too many values to unpack" ở B1 BrowseComp-Plus r3; B2 BrowseComp-Plus r4 crash ở bước kiểm tra chạy). Đây là lỗi của ứng viên do LLM viết, không phải lỗi framework; cổng hoạt động đúng.
5. **B3, `adapt_for_case` đôi khi nhận JSON hỏng** ("LLM config response JSON parse failed", 20 ca tổng cộng) và rơi về cấu hình chung. Đây là hành vi của mã gốc, không phải lỗi port. Việc số token tăng mạnh khi thích nghi theo ca cũng là hành vi gốc.
6. **Cách đọc kết quả:** B2 ALFWorld có 46 tác vụ chạy y hệt H0 nhưng kém 7 tác vụ. Mọi so sánh từng tác vụ trên ALFWorld cần đọc cùng mức nhiễu.

## 6. Dữ liệu

- Kết quả theo episode: `results/medium/{h0,b1,b2,b3}_<bench>.jsonl`; log: `results/medium/logs/`; bảng tổng: `results/medium/analysis.md`.
- Bản cũ để đối chiếu: `results/medium/b2_v1/`, `results/medium/b3_configonly/`. Các lượt chạy hủy (429, lỗi `<arg_value>`, biến thể không được chọn, hết tiền) nằm trong `results/medium/aborted_*`.
- Thư mục `runs/` (ứng viên, bundle) và trajectory không được commit: chúng chứa câu hỏi đã giải mã của BrowseComp-Plus.
