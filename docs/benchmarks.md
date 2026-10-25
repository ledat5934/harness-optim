# Benchmark: thiết lập, adapter, kết quả smoke, các sai lệch (Giai đoạn 2)

Cả ba benchmark đều chạy trong distro WSL2 `Ubuntu-HG` (Ubuntu 24.04, Python 3.12), với **một môi trường ảo cho mỗi benchmark** (`/root/hg-venv`, `/root/aw-venv`, `/root/bcp-venv`). Cách này tách biệt các ràng buộc phiên bản chặt của AppWorld và các phụ thuộc khai báo khá nặng của pyserini.

Chạy bất kỳ thứ gì bằng:
`wsl -d Ubuntu-HG -u root -- bash /mnt/e/KLTN/scripts/wsl_run.sh <hg|aw|bcp> python <script> ...`

## Giao diện adapter thống nhất (`benchmarks/common.py`)
```
list_tasks(split) -> [task_id]
run_episode(task_id, harness, llm, split=..., run_tag=..., max_steps=None)
    -> Result(success, steps, tokens, cost, trajectory_path, error, ...)
```
- Một adapter xây dựng một `Env` (`reset() -> TaskSpec`, `step(tool, args) -> StepResult`, `evaluate()`, `close()`).
- Nó gọi `harness.run(task, env, llm, rec)` rồi hỏi Env về phán quyết ground-truth. Harness không bao giờ thấy bộ đánh giá.
- Mỗi episode ghi một quỹ đạo JSON vào `results/trajectories/<bench>/<run_tag>/<task>.json` (git-ignored; xem "Vệ sinh dữ liệu").
- Các ngoại lệ được ghi vào `Result.error` và không bao giờ bị nuốt. `BudgetExceeded` được ném lại và làm dừng lần chạy.

## Smoke Giai đoạn 2 (agent trivial, 3 tác vụ mỗi benchmark; `scripts/run_adapter_smoke.py`)
Agent trivial (`benchmarks/trivial_agent.py`) được cố tình tối giản: tối đa 6 lệnh gọi LLM, không quản lý ngữ cảnh, không verifier. Nó chỉ chứng minh pipeline chạy từ đầu đến cuối; kỳ vọng 0 thành công.

| benchmark | split | số tác vụ | thành công | số bước trung bình | token | chi phí (USD) | lỗi |
|---|---|---|---|---|---|---|---|
| ALFWorld | train | 3 | 0/3 | 12.0 | 16,382 | 0.000252 | 0 |
| AppWorld | dev | 3 | 0/3 | 6.7 | 21,250 | 0.000239 | 0 |
| BrowseComp-Plus | dev (tập con) | 3 | 0/3 | 10.0 | 98,867 | 0.001298 | 0 |

- Agent trivial không bao giờ gọi `finish` trên BrowseComp-Plus, nên judge được kiểm tra riêng bằng `scripts/test_bcp_judge.py`. Đáp án vàng → được judge là đúng, đáp án sai → judge là sai, trên 2 truy vấn: **PASS** ($0.000128).
- Bản ghi thô từng episode: `results/phase2_trivial_<bench>.jsonl`.
- Tệp AppWorld cũng chứa 3 bản ghi trước đó với `error="ValueError: signal only works in main thread"`, từ lần thử trước khi sửa dưới đây. Chúng được giữ lại như một nhật ký trung thực.

## ALFWorld
- Cài đặt: `pip install alfworld` (0.4.2; cài cơ bản = `textworld[pddl]` 1.7.0, **không có torch / THOR**), rồi `alfworld-download` → `/root/.cache/alfworld` (2.3 GB, gồm cả các detector mà chúng tôi không bao giờ nạp).
- Chỉ chế độ TEXT, qua `textworld.gym.register_game(..., wrappers=[AlfredDemangler(), AlfredInfos])`, giống `AlfredTWEnv` của ALFWorld.
- Các split: `train` (3553 game, khớp với số lượng chính thức), `seen` = valid_seen, `unseen` = valid_unseen. Áp dụng cùng bộ lọc như `AlfredTWEnv.collect_game_files` (cần `traj_data.json`; loại `movable`/`Sliced`).
- Tool: `act(command)` và `admissible_commands()`. Thành công = `won` của TextWorld. Tối đa 50 bước (ngân sách ReAct ALFWorld).
- Không thử Windows gốc. TextWorld/fast-downward không hỗ trợ Windows, và TASK.md khuyến nghị dùng WSL2.

## AppWorld
- Cài đặt: `pip install appworld` (0.1.3.post1), `appworld install`, `appworld download data` (`APPWORLD_ROOT=/root/appworld_root`).
  - `appworld verify tests`: **1553 passed**.
  - `appworld verify tasks`: xác minh đầu cuối cho train/dev chạy mà không có thông báo lỗi.
- Tool: `execute_python(code)` trong REPL có trạng thái của AppWorld. Prompt được rút gọn từ agent ReAct dạng mã đơn giản công khai (`experiments/prompts/react_code_agent/instructions.txt`, Apache-2.0).
- Hoàn thành = `world.task_completed()` (agent gọi `apis.supervisor.complete_task`). Thành công = `world.evaluate()` success.
- **Quy tắc split kiểm thử:** smoke, H0, train và val chỉ dùng `train`/`dev`. `scripts/run_adapter_smoke.py` từ chối `test_*` đối với AppWorld.
  - Với các split kiểm thử, chúng tôi chỉ nạp id tác vụ và ghi các số đếm đạt/trượt tổng hợp.
  - Không in, không lưu trong tài liệu, và không dùng để điều chỉnh bất kỳ chỉ dẫn hay nội dung test case nào.
  - Các tệp `.bundle` đã mã hóa không bao giờ được mã của chúng tôi mở.
- **Vấn đề đã tìm thấy và đã sửa (chế độ trong tiến trình):**
  1. `SafetyGuard` của AppWorld monkey-patch `builtins.open`, `io.open`, `pathlib.Path.open` và một số hàm `os.*` trên toàn tiến trình trong lúc `execute()`. `disable()` của nó không khôi phục `io.open`, nên `open` chỉ đọc bị rò rỉ, làm hỏng việc ghi quỹ đạo/chi tiêu của chúng tôi (`PermissionError: Writing to OS file system is disabled`) và `mkdir`.
     - Cách sửa: `benchmarks/appworld/adapter.py` chụp lại mọi hàm trong bảng `DISALLOWED_MODULE_TO_FUNCTION_NAMES` của chính AppWorld trước khi thế giới đầu tiên được tạo, và khôi phục chúng sau mỗi `execute` / `evaluate` / `close`.
     - `llm.py` và `benchmarks/common.py` ghi qua `io.open`.
  2. AppWorld dùng timeout dựa trên signal (chỉ luồng chính) và một đồng hồ `freezegun` toàn cục của tiến trình. Vì vậy **các episode AppWorld chạy tuần tự trong luồng chính** (không đồng thời).
     - Hệ quả phụ: bên trong tiến trình AppWorld, `time.time()` bị đóng băng theo ngày của tác vụ. Độ trễ mà `llm.py` ghi log cho các lệnh gọi AppWorld do đó không có ý nghĩa, và timeout của khóa chi tiêu được viết lại để dùng bộ đếm vòng lặp thay vì thời gian thực.
  3. AppWorld cũng đặt `builtins.SystemExit = Exception` khi nó tạo bộ bảo vệ.

## BrowseComp-Plus
- Tham chiếu mã nguồn: `third_party/BrowseComp-Plus` (MIT).
- Dữ liệu:
  - Chỉ mục BM25 `Tevatron/browsecomp-plus-indexes/bm25/*` (2.17 GB, lưu tài liệu thô nên `get_document` được phục vụ từ chỉ mục) được tải trên Windows và sao chép sang ổ ext4 của WSL tại `/root/bcp_index/bm25`.
  - Bộ truy vấn `Tevatron/browsecomp-plus` nặng 2.8 GB vì mỗi dòng nhúng luôn tài liệu của nó. Chúng tôi chỉ tải **một shard** (`test-00000-of-00006.parquet`, 508 MB).
  - Chúng tôi chỉ giải mã `query_id/query/answer` của **20 dòng đầu tiên**, bằng lược đồ canary-XOR chính thức (`benchmarks/browsecomp_plus/prepare_subset.py`) → `data/browsecomp_plus/subset.jsonl` (git-ignored).
  - Chia: 10 đầu = `dev` (smoke / H0 / train / val), 10 cuối = `test`.
- Giao diện agent theo mặc định của search agent chính thức (`search_agent/openai_client.py`): `search(query)` top-k=5, snippet ≈ 512 token, cùng với `get_document(docid)` và tool `finish(answer)` mang định dạng chính thức "Explanation / Exact Answer / Confidence".
- **Cách giải quyết: không có API Python của pyserini.** `pyserini` 2.4.0 khai báo torch ≥ 2.9, transformers 5, onnxruntime, v.v., và `pyserini.search` import torch ngay khi được import.
  - Thay vào đó chúng tôi cài `pyserini --no-deps` + `pyjnius` và gọi `io.anserini.search.SimpleSearcher` trực tiếp từ fat jar của Anserini nằm trong wheel. Đây là lớp Java mà `LuceneSearcher` bao bọc, với cùng mặc định BM25 (k1=0.9, b=0.4).
  - Java 21 (openjdk-21-jdk-headless) chạy trong WSL; heap của JVM được giới hạn 1 GB.
  - Đo được: mở chỉ mục ≈ 20 s, tìm kiếm ≈ 1.7 s cho truy vấn đầu tiên.
- **Sai lệch: độ dài snippet.** Snippet được cắt còn 2000 ký tự thay vì 512 token Qwen3, để tránh tải tokenizer. Điều này tương đối tương đồng.
- **Sai lệch: judge.** Judge chính thức là Qwen3-32B (cần GPU). Chúng tôi dùng `GRADER_TEMPLATE` chính thức với model OpenRouter của chúng tôi `inclusionai/ling-3.0-flash` và phân tích `correct: yes|no`.
  - **Vì vậy điểm số KHÔNG so sánh được với bảng xếp hạng công khai.**
  - Chi phí judge là chi tiêu thực: nó được theo dõi dưới tag `judge:browsecomp_plus` và được tính vào `cost` của mỗi episode.

## Vệ sinh dữ liệu
`data/`, `third_party/`, `results/trajectories/` và `.env` đều nằm trong git-ignore. Quỹ đạo chứa các câu hỏi BrowseComp đã giải mã (canary: "should never appear as plain text online"), nên chúng được giữ cục bộ. Kết quả đã commit chỉ chứa id, số liệu và lỗi.
