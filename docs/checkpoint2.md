# Checkpoint 2 (sau Giai đoạn 3: H0)

Theo chỉ dẫn của mục tiêu, tôi không dừng lại tại đây. Tệp này ghi lại những gì lẽ ra đã được trình bày tại CHECKPOINT 2: các giao diện H0, kết quả smoke và chi phí.

## Giao diện H0 (`h0/`)
- `h0/protocols.py`: năm Protocol theo slot, đồng bộ và không phụ thuộc benchmark:
  - `AgentLoop.run(task, env, h, llm, rec) -> LoopOutcome`
  - `ContextMgmt.build(system, task, history, memory_notes) -> messages`
  - `ToolPolicy.tools(task)`, `.parse(resp, task) -> [Action]`, `.format_observation(action, step_result, task) -> str`
  - `Memory.recall(task) -> str`, `.update(task, outcome, success, trajectory)` (đóng băng lúc kiểm thử)
  - `Verifier.check(task, action, state, env_done) -> Verdict(accept, feedback)`
- `h0/registry.py`: tự động phát hiện `variants/<slot>/*.py`. Mỗi tệp gọi `reg.register(slot, name, factory(config), description, config_schema, niche)`, theo `library.py` của ModularRSI. Chế độ đường dẫn với tên module duy nhất cho phép các cây ứng viên nạp song song.
- `h0/compose.py`:
  - `compose(task, root, composer=None) -> Harness` mang tính xác định
  - H0 = `DEFAULT_BUNDLE` (mọi slot → `default`), tương đương `StaticComposer` của ModularRSI
  - `<root>/bundle.json` ghim biến thể và cấu hình (được kiểm tra, có thể một phần, rơi về default khi không hợp lệ)
  - một hook `composer(task, registry, base_bundle) -> bundle` tùy chọn theo từng tác vụ (được B2 và B3 dùng, và là nơi composer của HarnessGraph sẽ cắm vào)
- Các biến thể mặc định:

| slot | biến thể mặc định |
|---|---|
| agent_loop | ReAct: một tool call gốc mỗi bước; dừng khi env báo xong / finish được chấp nhận / đạt số bước tối đa / 3 phản hồi không có tool call. Chỉ với tác vụ có tool finish: nhắc đưa đáp án cuối 2 bước trước giới hạn, và ép dùng tool finish qua `tool_choice` gốc ở bước cuối. Các tool không được cung cấp ở bước đó sẽ không bao giờ được thực thi. |
| context_mgmt | system prompt + hướng dẫn benchmark (từ adapter) + `extra_system` tùy chọn + memory notes; tin nhắn tác vụ được ghim; cửa sổ trượt 30 lượt assistant (cặp tool được giữ nguyên vẹn); quan sát bị giới hạn 6000 ký tự |
| tool_policy | schema tool gốc của env giữ nguyên; phân tích tool call gốc với phương án dự phòng JSON dạng văn bản / `<tool_call>`; quan sát được cắt đầu+đuôi xuống 8000 ký tự |
| memory | không có |
| verifier | chấp nhận tín hiệu hoàn thành đầu tiên (chỉ từ chối đáp án rỗng) |

- Mã riêng của từng benchmark chỉ nằm trong `benchmarks/<name>/adapter.py`: giao diện env, schema tool, và văn bản hướng dẫn lấy từ các agent tham chiếu công khai (prompt ReAct rút gọn của AppWorld, prompt search-agent của BrowseComp-Plus, hướng dẫn lệnh kiểu ReAct của ALFWorld).
- Kiểm thử offline: `tests/test_h0_offline.py` (registry, compose, đường đi env-done, đường từ chối của verifier, dự phòng văn bản, dừng khi không có hành động). Không tốn chi phí.
- Hash cây H0 đã đóng băng: **`885ec0b302b8`** (`baselines.common.tree_hash`). Mọi bản ghi H0 dùng chung đều mang hash này, và `run_baselines.py` từ chối bằng chứng từ H0 khác.

## Kết quả smoke của H0 (H0 cuối, 5 tác vụ train của giao thức, roll 1)
| benchmark | split | thành công | số bước trung bình | token (tổng) | chi phí (USD, tổng) | chi phí/episode | lỗi |
|---|---|---|---|---|---|---|---|
| ALFWorld | train | 4/5 | 33.0 | 321,368 | 0.003304 | 0.00066 | 0 |
| AppWorld | train | 1/5 | 28.0 | 696,225 | 0.006403 | 0.00128 | 0 |
| BrowseComp-Plus | tập con dev | 1/5 | 25.0 | 2,723,000 | 0.022122 (gồm judge) | 0.00442 | 0 |

- Quỹ đạo: `results/trajectories/h0_<bench>_<phase>_r<roll>/` (cục bộ, git-ignored).
- Bản ghi: `results/h0_<bench>.jsonl`. Các tệp này cũng chứa roll train thứ hai, val và test, là bằng chứng dùng chung mà mọi baseline sử dụng.
- Mọi dòng H0 (roll train, val, test) đều có trong `results/summary.md`.

## Thay đổi trên H0 trong Giai đoạn 3 (đều được ghi lại; bản ghi thô của các lần chạy bị thay thế đã bị xoá khi dọn artifact, chi tiêu vẫn nằm trong `results/spend.json`)
1. **BrowseComp-Plus: H0 không bao giờ trả lời.** Cả 5 episode đều dùng hết ngân sách 25 bước cho `search` và không bao giờ gọi `finish`, nên điểm bằng 0 theo cấu trúc ("cố tình yếu").
   - Đã thêm một lời nhắc ngân sách không phụ thuộc benchmark trong `agent_loop/default`. Nó chỉ hoạt động với các tác vụ có tool finish, nên hành vi trên ALFWorld/AppWorld không đổi.
   - Lời nhắc đơn thuần chưa đủ: mô hình vẫn gọi `search` ngay cả khi chỉ được cung cấp `finish`. Vì vậy bước cuối ép dùng tool finish bằng `tool_choice` gốc, và các lệnh gọi tới tool không được cung cấp ở bước đó sẽ bị từ chối.
2. **ALFWorld dưới đồng thời.** Bộ phân tích TatSu toàn cục của TextWorld không an toàn luồng (`IndexError: pop from empty list`). Các lệnh gọi TextWorld nay được tuần tự hóa bằng khóa trong adapter. Đây chỉ là thay đổi ở adapter.
3. **Adapter BrowseComp-Plus.** Anserini trả về một kết quả có `lucene_document` null (`NullPointerException`). Adapter nay chuyển sang lấy tài liệu theo id. Val H0 trên BC+ đã được chạy lại.
4. Do thay đổi 1, **mọi lần chạy H0 của ALFWorld và AppWorld đều được làm lại với H0 cuối**, nên bằng chứng dùng chung đến từ đúng hash `885ec0b302b8`.
   - Thông báo tool bị từ chối khác với thông báo env trước đó trên 9 episode ALFWorld đã gọi một tool không tồn tại, ví dụ `look`.
   - Các bản ghi BC+ được tạo sau lần chỉnh sửa cuối và được gắn hash sau đó (trường `h0_hash_note`).

**Độ biến thiên giữa các lần chạy vẫn thấy được ngay cả ở nhiệt độ 0** (định tuyến nhà cung cấp OpenRouter):
- Val và train H0 của AppWorld đi từ 2/5 → 1/5 và val 1/3 → 0/3 giữa lần chạy trước khi chốt và lần cuối, mặc dù các thay đổi vòng lặp không ảnh hưởng đến AppWorld.
- Kiểm thử H0 của ALFWorld là 3/3 với H0 nhưng 2/3 khi B1 giữ H0 và chạy lại trên cùng 3 tác vụ (lần thử trước khi chốt).

Với 3 tác vụ kiểm thử, chênh lệch một tác vụ là nhiễu.

## Chi phí cho đến nay (cuối Giai đoạn 3, sổ bền vững)
Khoảng $0.24 trên $1.00 tại thời điểm viết này, gồm cả mọi lần thử bị thay thế. Phần lớn đến từ BrowseComp-Plus: ngữ cảnh tìm kiếm dài ≈ 100k token mỗi episode, cùng các lần chạy lại. Xem `results/spend.json` / `results/summary.md` để có số liệu chính xác và hiện hành.

## Đặc điểm của model (ảnh hưởng đến các baseline)
`inclusionai/ling-3.0-flash` phát ra lập luận ẩn (`message.reasoning`). Với prompt sinh dài (proposer của B1), nó đã dùng hết 8000 `max_tokens` cho lập luận và trả về nội dung rỗng (`finish_reason=length`). `reasoning.effort` và `max_tokens` của lập luận trên OpenRouter không có tác dụng với nhà cung cấp này; chỉ `{"enabled": false}` mới hoạt động.

`llm.chat(..., fallback_no_reasoning=True)` thử lại một phản hồi rỗng một lần với lập luận bị tắt. Nó được dùng cho mọi lệnh gọi sinh của baseline. Lệnh gọi agent của H0 giữ mặc định của model.
