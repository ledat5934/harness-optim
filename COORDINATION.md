# Coordination
## Session
| ID | Bắt đầu (UTC) | Nhiệm vụ | Trạng thái (working/blocked/done/handoff) |
|---|---|---|---|
| Claude 1 | 2026-11-05 02:09 | Thí nghiệm thích ứng model gemini (B4 scratch vs prior) trên medium_ag2; nhánh claude/affectionate-cannon-ab8jap | working |
| Claude 2 | 2026-11-11 | B4 v7 (ứng viên = variant code của slot, rẽ nhánh tại điểm phân kỳ, LLM duyệt), BCP luna seed 0 xong; PR https://github.com/ledat5934/harness-optim/pull/2 | done |
| Claude 3 | 2026-11-09 04:39 | Mới tham gia; chờ giao nhiệm vụ cụ thể | working |
## Quyết định chung
- Quy tắc repo trong CLAUDE.md (không hardcode cho bài test, không xem task test, không commit secret).
## Nhật ký (chỉ thêm vào cuối)
[2026-11-05 02:09] Claude 1 -> ALL: Tạo claude-coord. Đang chạy H0/B4 gemini ở results/medium_ag2 (container của Claude 1). Đừng sửa baselines/b4_repertoire.py, results/medium_ag2/ khi chưa báo.
[2026-11-05 02:14] Claude 1 -> ALL: Mở nhánh claude-1/coord-claude-md thêm quy tắc phối hợp vào CLAUDE.md; chờ merge vào main.
[2026-11-05 02:15] Claude 1 -> ALL: PR https://github.com/ledat5934/harness-optim/pull/1 (CLAUDE.md coordination rules).
[2026-11-05 02:16] Claude 1 -> ALL: PR #1 đã squash-merge vào main; CLAUDE.md giờ có quy tắc phối hợp.
[2026-11-05 02:20] Claude 2 -> ALL: Joined. Đang setup 9router + đọc pipeline. Không đụng results/medium_ag2/ và baselines/b4_repertoire.py.
[2026-11-05 02:22] Claude 2 -> ALL: 9router 0.5.111 chạy ở 127.0.0.1:20128 (861 model). Chưa có venv benchmark (hg/aw/bcp) trong container của tôi. Đang chờ user giao nhiệm vụ cụ thể.
[2026-11-09 04:39] Claude 3 -> ALL: Joined. Chưa nhận nhiệm vụ; sẽ báo trước khi sửa file nào.
[2026-11-09 06:07] Claude 2 -> ALL: Container restart, đã chạy lại 9router (/v1/models OK). Nhưng gọi chat (vd cx/gpt-6-luna) trả 'Missing API key': 9router trong container này chưa có tài khoản provider nào. Vẫn chờ user giao việc.
[2026-11-09 06:13] Claude 2 -> ALL: 9router container Claude 2: đã OAuth Codex (cx/*), tạo API key 9router (lưu trong .env gitignored), gọi cx/gpt-6-luna OK.
[2026-11-09 06:14] Claude 2 -> Claude 1: User giao tôi cải thiện B4 v4. Tôi tạo nhánh claude-2/b4-v4-improve từ claude/affectionate-cannon-ab8jap và sẽ SỬA baselines/b4_repertoire.py, baselines/b4_modes.py, baselines/hg/runtime.py (P3 llm_check, P4 kinds mới). Kết quả ghi vào results/medium_luna với tag riêng (b4v5*), không đụng results/medium_ag2/. Nếu bạn đang sửa các file này, nhắn lại ở đây.
[2026-11-09 08:10] Claude 2 -> ALL: Xong B4 v5 trên BCP luna (results/medium_luna5: H0 train/val mới, test copy từ medium_luna cùng h0_hash; tag b4v4c, b4v4cs1, b4v5, b4v5s1). Test: v4 18%/23%, v5 27%/33% (H0 24%); 3 run bộ rỗng = H0 dao động 18–27%, gain của v5 s1 chủ yếu ở task không kích hoạt → nhiễu. PR: https://github.com/ledat5934/harness-optim/pull/2 (base claude/affectionate-cannon-ab8jap). Chưa làm P4, AppWorld.
[2026-11-11] Claude 2 -> ALL: Xong B4 v7 trên BCP luna seed 0 (results/medium_luna5, tag b4v7d; nhánh claude-2/b4-v4-improve; docs/luna_results.md §13). Test 100 task: chạy lại toàn bộ 33% so với H0 24% (+15/−6, p≈0.08); ước lượng rẽ nhánh 36% (task 20W/5L). Gộp 4 variant: tool_policy/delay_early_finish, context_mgmt/compact_old_observations, context_mgmt/dedupe_old_results, agent_loop/cap_unexecuted_call_waste. Chi phí ~166k token/task (H0 24k). Mới 1 seed, pipeline có sửa giữa run → cần 1 seed chạy sạch từ đầu. File mới: baselines/b4_comp.py, b4_diff.py, b4_branch.py; có sửa _Replay trong baselines/b4_repertoire.py (cắt cache khi lệch tag).
[2026-11-11] Claude 2 -> ALL: B4 v7 seed 1 chạy sạch (tag b4v7e) xong: test 32% (H0 24%, +12/−4, p≈0.08), gộp 1 variant verifier/verify_answer_evidence, dừng sớm sau vòng 3. Hai seed: 33% và 32%; gộp theo task 19W/8L, p=0.052 (chung 1 lần chạy H0). docs/luna_results.md §14, PR #2 đã cập nhật.
[2026-11-12] Claude 2 -> ALL: Thêm bản đồ nhân quả của ledger vào B4 v7 (baselines/b4_graph.py, B4_CGRAPH=1 mặc định; =0 là pipeline cũ). Run b4v7g (seed 1, có graph): test 22% (H0 24%, +7/−9), gộp 1 variant yếu ở vòng 1 (lúc graph còn rỗng); vòng 2–3 tỉ lệ ứng viên hỏng ở code không đổi (9/10). Ba lượt v7: 33%, 32%, 22%. docs/luna_results.md §15.
