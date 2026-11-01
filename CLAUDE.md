# harness-optim: quy tắc làm việc

- **Khái quát hoá, không hardcode cho bài test.** Mọi cải tiến ý tưởng hay implement (harness, candidate, proposer,
  router, baseline) không được chứa ID task, tên test, chuỗi đáp án, đường dẫn/tên file benchmark hay entity cụ thể
  của bài test. Thay đổi phải ở dạng nguyên tắc `precondition (chạy được trên trajectory) -> action`. Xem `docs/idea_v2.md` mục 3.1.
- Không xem nội dung task test AppWorld; không in câu hỏi BrowseComp-Plus.
- Không commit API key/token; `runs/` và `trajectories/` giữ gitignored.
