# Ý tưởng v3: kết hợp LLM nhiều hơn, đưa graph trở lại (B4 v4)

Tài liệu này nối tiếp `docs/idea_v2.md` và các kết quả B4 v3 trong `docs/luna_results.md` §8–10.

**Hai nhận xét dẫn tới bản này:**

1. **B4 v3 quá thiên về luật viết tay.**
   - Failure mode là 6 luật cố định trên tín hiệu.
   - Precondition chỉ đọc được khoảng 20 tín hiệu số.
   - Action chỉ có 4 loại hook.
   - LLM chỉ được dùng để viết báo cáo và để đề xuất.

   Hệ quả là B4 ổn định nhưng trần thấp. Mọi lỗi nằm ngoài 6 luật đều rơi vào `other`, và proposer không sửa được context, memory hay cấu trúc vòng lặp.
2. **Graph của ý tưởng gốc gần như đã biến mất khi implement.** `idea_v2.md` §3.4 hạ graph xuống thành một "view" của ledger, nhưng trong code không có view nào và không quyết định nào dùng đến graph.

**Nguyên tắc giữ nguyên:**
- Khái quát hoá: lint, không hardcode.
- Sàng lọc ghép cặp với task mục tiêu và task an toàn.
- Gộp chỉ khi có biên ghép cặp trên val.
- Kích hoạt lười.

Đây là những thứ làm B4 ổn định hơn B1, nên không đổi.

---

## Lộ trình

Trạng thái: ✅ đã implement · 🧪 implement xong, chưa chạy thật · ⏳ chưa làm.

### P1. Failure mode do LLM phát hiện (🧪, `baselines/b4_modes.py`)

- Prompt hindsight có thêm trường `failure_label`: 3–8 từ mô tả hành vi sai, không chứa entity của task.
- Mỗi vòng gắn nhãn cho tối đa `B4_N_LABEL=16` run sai, gồm 6 run có báo cáo đầy đủ và các run khác chỉ có hindsight.
- Một lệnh gọi LLM gom các nhãn này thành tối đa 6 mode. Mỗi mode có:
  - `definition`;
  - `members`: các task được gán nhãn thuộc mode;
  - `harness_fixable`;
  - `signal_hint` tuỳ chọn: một biểu thức DSL xấp xỉ mode. Hint dùng để gán thêm các run sai chưa được gán nhãn, đánh giá trên signature đã lưu (`R.eval_pre_sig`).
- Tên mode được giữ ổn định qua các vòng: registry cũ được đưa vào prompt.
- Proposer nhận các mode này kèm định nghĩa, và `failure_mode` không còn bị giới hạn trong 6 nhãn cố định.
- Bước sàng lọc chọn task mục tiêu theo mode LLM: các task thuộc `members` cộng các task khớp `signal_hint`. Mode không có trong registry thì quay về luật cũ.
- Luật cũ chỉ còn là đặc trưng (`rule_modes`) đưa vào bước gom cụm.
- Cơ chế đóng băng áp dụng cho mọi tên mode.
- Tắt bằng `B4_LLM_MODES=0` để quay về v3, phục vụ ablation.

**Cần kiểm chứng khi chạy:**
- Mode có ổn định qua các vòng và các seed không.
- `signal_hint` khớp với nhãn LLM tới mức nào: cần đo precision/recall trên các run đã có nhãn.
- Chi phí: khoảng 10 lệnh gọi hindsight thêm và 1 lệnh gom cụm mỗi vòng.

### P2. Graph cơ chế dùng cho proposer (🧪, `baselines/b4_modes.py`)

- **Node:** mode (định nghĩa, có sửa được không) và mechanism (kind, precondition, text, trạng thái).
- **Cạnh mechanism → mode:**
  - `in_set`: đã vào bộ;
  - `helps`: qua sàng lọc;
  - `hurts`: dT < 0 hoặc dS < 0;
  - `tried`.

  Mỗi cạnh mang dT, dS, số lần kích hoạt và lý do bị loại.
- **Cạnh mechanism ↔ mechanism:** `conflicts`, khi bộ gộp thua trên val.
- Graph được dẫn xuất từ pool. Pool và ledger vẫn là nguồn sự thật.
- Graph được ghi ra `runs/<tag>/<bench>/graph.json` mỗi vòng.
- Proposer thấy graph của lần chạy hiện tại, nhóm theo mode: "đã thử gì cho mode này, cái gì giúp, cái gì hại".
- `B4_GRAPH=<run roots>`: graph của các lần chạy trước (seed khác, model khác) được đưa vào prompt như ý tưởng có thể chuyển giao, không phải bằng chứng. Đây là cách chuyển giao mềm hơn `B4_PRIOR`, vốn sàng lọc thẳng cơ chế cũ.

### P3. Precondition hai tầng: tín hiệu + câu hỏi LLM (⏳)

- Tầng 1 là bộ lọc rẻ trên tín hiệu, như hiện nay.
- Tầng 2 là một câu hỏi yes/no ngắn cho LLM, chỉ được gọi khi tầng 1 đúng. Ví dụ: "đáp án hiện tại đã được tài liệu nào xác nhận chưa?", "bước vừa rồi có tiến gần mục tiêu không?".
- Cần làm:
  - schema `llm_check: "<question>"`;
  - hook trong `HookedLoop` để gọi model, có giới hạn số lần gọi và token;
  - ghi kết quả vào telemetry.
- Lint áp cho câu hỏi giống như áp cho `text`.
- Chi phí phải tính vào mục tiêu (bài học F6 của B3).

### P4. Mở rộng action sang các slot còn thiếu (⏳)

Theo taxonomy 11 slot của `idea_v2.md` §2, v3 mới phủ S1, S4, S5 và S7. Cần thêm các kind sau, mỗi kind là một hook trong runtime:

| kind | slot | hành động |
|---|---|---|
| `compress_context` | S1/S9 | tóm tắt hoặc cắt lịch sử khi `tokens`/số bước vượt ngưỡng, bằng LLM hoặc luật |
| `note` | S9 | agent có scratchpad: ghi lại các kết luận đã kiểm chứng, chèn lại vào context |
| `verify` | S8 | trước `finish`: một lệnh gọi LLM kiểm tra đáp án với bằng chứng, rồi từ chối nếu không đạt |
| `plan` | S6 | đầu episode hoặc khi lỗi lặp lại: sinh kế hoạch hoặc todo, chèn vào context |
| `tool_wrap` | S3/S4 | hậu xử lý output của tool: rút trích phần liên quan, chuẩn hoá lỗi |
| `decode` | S10 | đổi temperature hoặc mức reasoning theo điều kiện |

Bước xa hơn là cho phép ứng viên dạng code: một variant H0 đầy đủ, như B1 làm. Ứng viên này phải qua đủ lint, sàng lọc ghép cặp và cổng val, và cần thêm smoke test.

### P5. Router theo task dùng graph (⏳)

- Hiện tại bộ cuối áp cho mọi task, chỉ có precondition làm bộ lọc.
- Hướng làm:
  - dự đoán mode từ các bước đầu của episode, bằng tín hiệu và/hoặc LLM;
  - bật các mechanism có cạnh `helps`/`in_set` với mode đó;
  - tránh các cặp `conflicts`.
- Cần dữ liệu ledger theo cụm task, và cách đánh giá router mà không rò rỉ test.

### P6. Chuyển giao giữa model bằng graph (⏳, phụ thuộc P2)

- Thêm node model profile vào graph.
- Khi gặp model mới, lấy các cạnh `helps` từ graph của model có profile gần nhất làm ứng viên ưu tiên. Phần này đã có một nửa qua `B4_PRIOR` và `B4_GRAPH`.
- Thí nghiệm gemini (`scripts/chain_ag2.sh`) sẽ chạy với v4 thay cho v3.

### P7. Hiệu chỉnh báo cáo (⏳)

- Trên luna, blind confidence không phân biệt được run đúng và run sai (§6).
- Cần đo xem `failure_label`/`cause` của hindsight có dự đoán được cơ chế nào giúp hay không. Nếu có thì tăng trọng số cho nguồn đó; nếu không thì giảm.

---

## Thí nghiệm cần chạy cho v4

1. Ablation trên BCP và AppWorld, cùng seed, cùng cấu hình MEDIUM:
   - `B4_LLM_MODES=0` (tương đương v3);
   - `B4_LLM_MODES=1` (P1 + P2).
2. Chạy lại với `B4_GRAPH` trỏ tới lần chạy seed 0 để đo xem graph có giúp proposer tìm được cơ chế nhanh hơn không.
3. Khi có P3 và P4, chạy lại cả hai benchmark với 2 seed.

**Ghi chú hạ tầng:**
- `runs/` (gitignored) đã mất khi container khởi động lại, kể cả pool của luna v3. Muốn dùng `B4_GRAPH`/`B4_PRIOR` thì phải chạy lại, hoặc lưu `final.json` và `graph.json` vào `results/`.
- Token luna đã hết hạn; cần đăng nhập lại Codex trong 9router.
