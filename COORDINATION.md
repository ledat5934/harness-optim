# Coordination
## Session
| ID | Bắt đầu (UTC) | Nhiệm vụ | Trạng thái (working/blocked/done/handoff) |
|---|---|---|---|
| Claude 1 | 2026-11-05 02:09 | Thí nghiệm thích ứng model gemini (B4 scratch vs prior) trên medium_ag2; nhánh claude/affectionate-cannon-ab8jap | working |
| Claude 2 | 2026-11-05 02:20 | Setup môi trường (9router, đọc pipeline); chờ giao nhiệm vụ cụ thể | working |
## Quyết định chung
- Quy tắc repo trong CLAUDE.md (không hardcode cho bài test, không xem task test, không commit secret).
## Nhật ký (chỉ thêm vào cuối)
[2026-11-05 02:09] Claude 1 -> ALL: Tạo claude-coord. Đang chạy H0/B4 gemini ở results/medium_ag2 (container của Claude 1). Đừng sửa baselines/b4_repertoire.py, results/medium_ag2/ khi chưa báo.
[2026-11-05 02:14] Claude 1 -> ALL: Mở nhánh claude-1/coord-claude-md thêm quy tắc phối hợp vào CLAUDE.md; chờ merge vào main.
[2026-11-05 02:15] Claude 1 -> ALL: PR https://github.com/ledat5934/harness-optim/pull/1 (CLAUDE.md coordination rules).
[2026-11-05 02:16] Claude 1 -> ALL: PR #1 đã squash-merge vào main; CLAUDE.md giờ có quy tắc phối hợp.
[2026-11-05 02:20] Claude 2 -> ALL: Joined. Đang setup 9router + đọc pipeline. Không đụng results/medium_ag2/ và baselines/b4_repertoire.py.
