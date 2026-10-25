# Checkpoint 1 (sau Giai đoạn 1)

Theo chỉ dẫn của mục tiêu, tôi không dừng lại tại đây. Tệp này ghi lại những gì lẽ ra đã được trình bày tại CHECKPOINT 1.

## Trạng thái
- Giai đoạn 0 đã xong.
  - Khung dự án, `.env` (git-ignored) / `.env.example`, `llm.py`, `results/spend.json`.
  - Gọi OpenRouter thường và gọi tool gốc đều thành công (xem `docs/env.md`).
- Giai đoạn 1 đã xong.
  - Shallow clone: `third_party/ModularRSI@b5c72c3`, `third_party/MemoHarness@4c3da18`, `third_party/meta-harness@8123cca`.
  - `docs/h0_survey.md` bao quát mục (a)–(g) cho từng repo, dựa trên các tệp thực sự đã đọc, và kết thúc bằng giao diện H0 được khuyến nghị.
  - (`docs/h0_survey.md` vô tình được đưa vào commit của Giai đoạn 0. Nội dung không thay đổi.)
- Chi tiêu đến nay: khoảng $0.00002 (3 lệnh gọi smoke).

## Phát hiện chính
1. **Chỉ ModularRSI có seed mô-đun thực sự.** Terminus-2 được tách thành 5 module `baseline` đứng sau các Protocol, có registry và `StaticComposer`/`LLMComposer`.
   - "Harness" của MemoHarness là một lớp `HarnessImpl` duy nhất cộng với một *bản tóm tắt cấu hình* D1–D6.
   - Meta-Harness là một lớp con `Terminus2` dạng tự do (KIRA).
2. **Cả ba đều phụ thuộc vào hạ tầng mà TASK.md cấm hoặc chúng tôi không có.**
   - ModularRSI cần Harbor + Docker/e2b và một LLM editor.
   - MemoHarness cần Harbor + Daytona, Codex CLI (bộ điều khiển duy nhất được hỗ trợ), và embedding của OpenAI.
   - Meta-Harness cần Harbor + Runloop/Modal và Claude Code (Opus).
   - Vì vậy cả ba đều được tái hiện theo thuật toán (Giai đoạn 4).
3. **Giấy phép.**
   - Mã gốc của ModularRSI là CC BY-NC 4.0: chỉ dùng cho nghiên cứu, có ghi nguồn.
   - Meta-Harness là MIT.
   - **MemoHarness không có LICENSE**, nên chúng tôi không sao chép mã nào từ đó và chỉ tái hiện thuật toán đã công bố.
4. Sai lệch đường dẫn trong đặc tả: ModularRSI có `scripts/evolve.sh`, không có `scripts/self_evolve.sh`. "gen_0" trong `generations/merged_active/gen_0` là thư viện *đã tiến hóa* đã được gộp (20 cài đặt), không phải seed.
5. HarnessDev: không tìm thấy kho công khai nào, nên không đưa vào.

## Giao diện H0 đề xuất (đã cài đặt ở Giai đoạn 3)
Năm slot: `agent_loop`, `context_mgmt`, `tool_policy`, `memory`, `verifier`.
- Đây là các Protocol đồng bộ, theo registry kiểu ModularRSI (`name`, `description`, `config`, `niche`).
- `compose(task) -> Harness` mang tính xác định: H0 = bundle toàn `default`.
- Các benchmark được truy cập qua một adapter `Env` mỏng (`reset/step/evaluate` + schema tool gốc).

Xem cuối `docs/h0_survey.md` để biết chữ ký ở mức mã nguồn.

## Quyết định mà người dùng có thể muốn xem lại
- **`observation` được gộp vào `tool_policy`.** Module `observation` riêng cho terminal của ModularRSI được gộp vào `tool_policy.format_observation`, vì ba benchmark của chúng tôi không phải terminal.
- **D5 được tách sang hai slot.** D5 của MemoHarness được tách thành `context_mgmt` (trong một episode) và `memory` (qua nhiều episode; không có tác dụng trong H0).
- **Truy hồi của B3 dùng BM25, không dùng embedding**, phù hợp với ràng buộc RAM của TASK.md.
