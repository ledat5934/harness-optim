
## Phối hợp nhiều Claude session

Bạn là một trong nhiều Claude session cùng làm trên repo GitHub này. Các session chạy cô lập, kênh liên lạc duy nhất là file `COORDINATION.md` trên nhánh `claude-coord`.

## Bước 1: Nhận danh tính (làm đầu tiên)
1. `git fetch origin`. Nếu nhánh `claude-coord` chưa có: tạo từ nhánh mặc định và push. Nếu có: checkout và pull.
2. Nếu chưa có `COORDINATION.md`: tạo file theo mẫu dưới, tự nhận **Claude 1**. Nếu đã có: đọc file, lấy số lớn nhất trong bảng, tự nhận **Claude (số đó + 1)**.
3. Thêm dòng của bạn vào bảng, commit `coord: Claude N joined`, push. Nếu push bị từ chối: `git pull --rebase`, đọc lại, đổi sang số kế tiếp nếu số của bạn đã bị lấy, rồi push lại.

## Mẫu COORDINATION.md
```
# Coordination
## Session
| ID | Bắt đầu (UTC) | Nhiệm vụ | Trạng thái (working/blocked/done/handoff) |
## Quyết định chung
## Nhật ký (chỉ thêm vào cuối)
[UTC time] Claude N -> Claude M/ALL: nội dung
```

## Quy tắc
- Chỉ thêm vào cuối nhật ký; chỉ sửa dòng của chính bạn trong bảng. Giờ lấy bằng `date -u +"%Y-%m-%d %H:%M"`.
- Không có thông báo tự động: `git pull --rebase` và đọc file khi bắt đầu, trước mỗi bước lớn và trước khi kết thúc.
- Nhắn khi: đổi nhiệm vụ, sắp sửa file dùng chung, gặp blocker, xong một phần. Trước khi sửa file, kiểm tra session khác đã báo đang sửa chưa.
- Mỗi lần ghi: pull --rebase, thêm nội dung, commit `coord: Claude N - <tóm tắt>`, push; lỗi thì pull --rebase và thử lại.
- Code làm trên nhánh `claude-N/<tên-việc>`, không commit code vào `claude-coord`, không push thẳng nhánh chính. Xong thì mở PR và ghi link vào nhật ký.
- Không ghi secret vào file.
- Khi kết thúc hoặc sắp hết quota: đặt trạng thái `done`/`handoff` và ghi đã làm gì, còn gì dang dở, nhánh nào, bước tiếp theo.
