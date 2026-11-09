# Coordination
## Session
| ID | Bắt đầu (UTC) | Nhiệm vụ | Trạng thái (working/blocked/done/handoff) |
|---|---|---|---|
| Claude 1 | 2026-11-05 02:09 | Thí nghiệm thích ứng model gemini (B4 scratch vs prior) trên medium_ag2; nhánh claude/affectionate-cannon-ab8jap | working |
| Claude 2 | 2026-11-05 02:20 | B4 v5 (P3 precondition 2 tầng + replay pre-check + fired-only credit), BCP 2 seed; PR https://github.com/ledat5934/harness-optim/pull/2 | done |
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
