# Báo cáo môi trường (Giai đoạn 0, 2026-10-18)

| hạng mục | trạng thái |
|---|---|
| Hệ điều hành | Windows 10 Pro 10.0.19045, 4 CPU logic, 8 GB RAM (≈1.9 GB trống tại thời điểm khảo sát) |
| WSL | Có WSL2, nhưng chỉ có distro `docker-desktop` (Stopped). **Chưa cài Ubuntu nào.** |
| Khắc phục WSL | Đã tải rootfs WSL Ubuntu 24.04 chính thức (`cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz`, sha256 `8251e27f…15ea`, đã kiểm tra với SHA256SUMS) và import thành distro **`Ubuntu-HG`** tại `E:\WSL\ubuntu-hg` (`wsl --import`, không cần admin, giữ nguyên ổ C: gần đầy). |
| Python (Windows) | 3.11.3 (cũng có 3.13 qua `py`) |
| Python (WSL) | Python3 hệ thống của Ubuntu 24.04 là 3.12 + venv |
| Java | Chưa cài trên Windows; đã cài `openjdk-21-jdk-headless` trong WSL (pyserini cần) |
| git / git-lfs | git 2.51.0.windows.2, git-lfs 3.7.0 (Windows); git + git-lfs qua apt trong WSL |
| Docker | Đã cài Docker Desktop 27.5.1 nhưng **không dùng** (TASK.md: không yêu cầu Docker) |
| Đĩa | C: còn trống 26 GB (đã dùng 85 %), E: còn trống 49 GB → mọi dữ liệu và môi trường ảo nằm trên E: hoặc trên ổ ext4 của WSL trên E: |
| GPU | Không có |

## Chạy ở đâu
- Mã nguồn nằm ở `E:\KLTN` (= `/mnt/e/KLTN` trong WSL).
- Các benchmark (ALFWorld/TextWorld, AppWorld, pyserini) chạy trong `Ubuntu-HG` với môi trường ảo tại `~/hg-venv`.
- `llm.py` chỉ dùng `requests` và chạy được cả trên Windows lẫn WSL.

## Ghi chú về OpenRouter
- Một `OPENROUTER_API_KEY` **khác** đã được đặt sẵn trong biến người dùng của Windows, và OpenRouter từ chối nó với lỗi `401 User not found`. Nay `llm.py` nạp `.env` với ngữ nghĩa ghi đè, nên key của dự án trong `.env` sẽ được ưu tiên.
- Model `inclusionai/ling-3.0-flash`, giá niêm yết $0.021 / triệu token prompt, $0.063 / triệu token completion (lấy từ `/api/v1/models`, chỉ để tham khảo; **chi phí luôn được đọc từ `usage.cost`**).
- Kiểm tra smoke (`python scripts/smoke_llm.py`):
  - gọi thường: 26 pt / 20 ct, độ trễ 2.25 s, chi phí $0.000002
  - gọi tool gốc: `add(a=17, b=25)` đúng, độ trễ 1.26 s, chi phí $0.000008
  - vòng tool trọn vẹn: câu trả lời "42", độ trễ 2.72 s, chi phí $0.000014
  - tổng cho 3 lệnh gọi ≈ $0.000024

## Công cụ dev (Windows)
- `pytest` cho test offline: `python -m pytest -q tests/`.
- `coverage==7.17.0` cho `scripts/copy_fidelity.py` (đo tỷ lệ dòng copy từ repo gốc trên các dòng được thực thi): `pip install coverage==7.17.0`.
- `scripts/summarize.py` in ký tự Unicode, nên trên console Windows cần đặt `PYTHONIOENCODING=utf-8`.
