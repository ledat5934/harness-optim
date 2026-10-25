# HarnessGraph — bộ so sánh harness (quy mô smoke)

Đây là hạ tầng để so sánh các phương pháp tiến hóa harness cho agent trên **ALFWorld**, **AppWorld** và **BrowseComp-Plus**. Mọi thứ đều bắt đầu từ một harness hạt giống dùng chung **H0**, và chỉ dùng một LLM: `inclusionai/ling-3.0-flash` qua OpenRouter.

Các baseline đã cài đặt, chạy trên harness H0 chung. Mã gốc được tái sử dụng khi không phụ thuộc Harbor/Docker; phần còn lại ghi rõ trong `docs/baseline_fidelity.md` (mục (a), (b), (c) cho từng baseline):
- **B1 (Meta-Harness, MIT)**: tiến hóa harness dạng tự do, toàn cục. Hàm `compute_pass_rates`, `update_frontier`, `update_evolution_summary`, `summarize_trial_metrics`, `render_task_prompt` và SKILL.md được copy từ `third_party/meta-harness` (có chỉnh sửa ghi trong tài liệu). Proposer là hai lệnh gọi tới model của chúng tôi.
- **B2 (ModularRSI, CC BY-NC 4.0, chỉ nghiên cứu, trích dẫn Wu et al. 2026, arXiv 2609.14857)**: tiến hóa theo slot + bộ định tuyến K-roll + composer LLM theo tác vụ. `router.py`, `trajectory_analysis.py`, `review_verdict.py` và các prompt được vendor vào `baselines/vendor/modularrsi/` với tiêu đề ghi nguồn. Các module self-evo của ModularRSI không phụ thuộc Harbor cũng được vendor: `backlog.py`, `routing.py`, `clustering.py`, `proposals.py`, `portfolio.py`, `dual_implement.py`, `rebase.py`, `promotion.py`, `routing_probe.py`, `lease.py`, `dispositions.py`, `confirm.py` (phần thống kê). Phần không vendor và phần viết lại nằm trong tài liệu.
- **B3 (MemoHarness, repo không có LICENSE, tác giả đã cho phép sao chép — `<ngày / hình thức cấp phép>`)**: ngân hàng kinh nghiệm hai lớp, chưng cất, tìm kiếm cấu hình toàn cục và điều chỉnh theo từng ca lúc kiểm thử. `core/`, `bank/`, `llm/distiller.py`, `llm/retry.py`, `controllers/llm_controller.py`, `config/runtime.py` được vendor vào `baselines/vendor/memoharness/`. Truy hồi dùng BM25 thay cho embedding; controller chỉ đổi cấu hình D1–D6.

> Kết quả hiện tại là **SMOKE RUN** (3 tác vụ kiểm thử mỗi ô), không có ý nghĩa thống kê. Xem `results/summary.md`.

```
llm.py                    client OpenRouter dùng chung: retry, timeout, ghi usage.cost, chốt ngân sách $ bền vững
h0/                       harness hạt giống: protocols.py (5 Protocol theo slot), registry.py, compose.py, variants/<slot>/*.py
benchmarks/<name>/adapter.py   list_tasks(split), run_episode(task_id, harness, llm) -> Result
baselines/                common.py (giao thức, ứng viên, cổng kiểm tra, đánh giá), b1_freeform.py, b2_modular.py, b3_memo.py
scripts/                  run_smoke.sh, run_h0.py, run_baselines.py, run_adapter_smoke.py, summarize.py, wsl_*.sh
docs/                     env.md, h0_survey.md, checkpoint1.md, benchmarks.md, checkpoint2.md, baseline_fidelity.md, open_problems.md
results/                  *.jsonl (bản ghi từng episode), summary.md, spend.json, llm_calls.jsonl, runs/ (ứng viên, log)
third_party/              shallow clone của các repo tham chiếu (git-ignored)
```

## Cài đặt (Windows + WSL2)
Đây là các bước đã được chạy trên máy này (chi tiết trong `docs/env.md` và `docs/benchmarks.md`).

1. **WSL Ubuntu trên ổ có nhiều dung lượng (không cần quyền admin):**
   ```powershell
   curl.exe -L -o E:\WSL\dl\ubuntu.tar.gz https://cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz
   wsl --import Ubuntu-HG E:\WSL\ubuntu-hg E:\WSL\dl\ubuntu.tar.gz --version 2
   wsl -d Ubuntu-HG -u root -- bash -c "apt-get update && apt-get install -y python3 python3-venv python3-dev build-essential git git-lfs openjdk-21-jdk-headless curl unzip"
   ```
2. **API key.** `cp .env.example .env` rồi đặt `OPENROUTER_API_KEY`. `.env` nằm trong git-ignore, và `llm.py` cho phép nó ghi đè mọi biến môi trường hệ thống còn sót. `MAX_USD` (mặc định 1.0) là ngân sách **tổng** cho mọi lần chạy.
3. **Môi trường ảo cho từng benchmark** (một môi trường cho mỗi benchmark, bên trong WSL):
   - ALFWorld: `python3 -m venv /root/hg-venv && /root/hg-venv/bin/pip install alfworld requests && /root/hg-venv/bin/alfworld-download`
   - AppWorld: `bash scripts/wsl_setup_appworld.sh` (cài đặt, `appworld install`, `download data`, `verify tests/tasks`; `APPWORLD_ROOT=/root/appworld_root`)
   - BrowseComp-Plus:
     - Chạy `bash scripts/wsl_setup_bcp.sh && bash scripts/wsl_fix_bcp.sh` (pyserini với `--no-deps` + pyjnius; chúng tôi gọi Anserini trực tiếp).
     - Tải `bm25/*` của `Tevatron/browsecomp-plus-indexes` vào `data/browsecomp_plus/indexes/bm25`, rồi sao chép sang `/root/bcp_index/bm25`.
     - Tải shard `test-00000-of-00006.parquet` của `Tevatron/browsecomp-plus` vào `data/browsecomp_plus/dataset/`.
     - Chạy `python -m benchmarks.browsecomp_plus.prepare_subset --n 20`.
4. Chạy mọi entry point qua script bao, script này kích hoạt đúng môi trường ảo và đặt biến môi trường:
   `wsl -d Ubuntu-HG -u root -- bash /mnt/e/KLTN/scripts/wsl_run.sh <hg|aw|bcp> python <script> ...`

Kiểm tra:
- `python scripts/smoke_llm.py` (gọi thường + gọi tool)
- `python tests/test_h0_offline.py` (không tốn chi phí)
- `scripts/run_adapter_smoke.py --agent trivial` (toàn bộ pipeline)

## Chạy
```bash
bash scripts/run_smoke.sh                 # mọi benchmark: chạy H0 dùng chung, rồi B1, B2, B3, rồi tổng hợp
bash scripts/run_smoke.sh alfworld        # một benchmark
bash scripts/wsl_run.sh hg python scripts/run_h0.py --bench alfworld --phase train --roll 1
bash scripts/wsl_run.sh hg python scripts/run_baselines.py --bench alfworld --method b2
python scripts/summarize.py               # dựng lại results/summary.md
```
- Mọi script đều in ngân sách còn lại trước tiên.
- Mọi lệnh gọi LLM sẽ bị từ chối khi chi tiêu bền vững vượt 80 % của `MAX_USD` (ngưỡng dự trữ 20 %), hoặc khi đã đạt `MAX_USD`.
- Các episode AppWorld chạy tuần tự (luồng chính). Các benchmark khác dùng tối đa 3 episode song song (giới hạn 4).

## Thêm một biến thể thành phần mới
Tạo `h0/variants/<slot>/<name>.py` (slot ∈ `agent_loop, context_mgmt, tool_policy, memory, verifier`). Cài đặt Protocol của slot trong `h0/protocols.py` và đăng ký:
```python
class EvidenceVerifier:
    def __init__(self, min_steps: int = 2): self.min_steps = min_steps
    def check(self, task, action, state, env_done):
        from h0.protocols import Verdict
        if env_done or state.step >= self.min_steps: return Verdict(True)
        return Verdict(False, "Gather evidence before finishing.")

def register(reg):
    reg.register("verifier", "evidence", lambda c: EvidenceVerifier(**c),
                 "Rejects a finish before min_steps steps; for tasks where premature answers are common.",
                 config_schema={"min_steps": "int"}, niche={"evidence": "min_steps"})
```
- Registry tự động phát hiện biến thể này.
- Để dùng nó trong một gốc harness, ghim nó vào `<root>/bundle.json`: `{"verifier": {"name": "evidence", "config": {"min_steps": 3}}}`.
- Hoặc truyền một composer theo từng tác vụ vào `h0.compose.compose(task, root, composer=...)`.
- Chạy `python tests/test_h0_offline.py`. `baselines.common.static_gate(root)` là cùng một kiểm tra mà các baseline dùng.

## Log nằm ở đâu
| nội dung | vị trí |
|---|---|
| mọi lệnh gọi LLM (token, chi phí lấy từ `usage.cost`, độ trễ, tag) | `results/llm_calls.jsonl` |
| tổng chi tiêu tích lũy (sổ ngân sách bền vững) | `results/spend.json` |
| kết quả theo từng episode (thành công, số bước, token, chi phí, lỗi, bundle) | `results/{h0,b1,b2,b3}_<bench>.jsonl`, `results/phase2_trivial_<bench>.jsonl` |
| toàn bộ quỹ đạo (chỉ lưu cục bộ, git-ignored) | `results/trajectories/<bench>/<run_tag>/<task>.json` |
| sản phẩm tiến hóa: ứng viên, đề xuất, log, ngân hàng B3 | `results/runs/<method>/<bench>/` (sản phẩm BrowseComp-Plus git-ignored) |
| id tác vụ của giao thức | `results/runs/protocol/<bench>.json` |
| bảng tổng hợp | `results/summary.md` |

## Gỡ lỗi với một mẫu cho mỗi baseline
```bash
bash scripts/wsl_run.sh hg python scripts/run_baselines.py --bench alfworld --method b1 --debug
```
- `--debug` chạy toàn bộ logic của phương pháp (proposer / investigator / ngân hàng) trên đầy đủ bằng chứng H0 dùng chung, nhưng chỉ thực thi 1 kiểm tra, 1 val và 1 test episode, tuần tự (`--n-check/--n-val/--n-test/--workers` ghi đè các giá trị này).
- Bỏ qua test AppWorld trong chế độ debug (không được phép xem test_normal).
- Mọi thứ được ghi vào `results/debug/<method>_<bench>_<time>/` (git-ignored), không ghi vào kết quả đã commit:
  - `transcript.md`: mọi lệnh gọi LLM với đầy đủ message yêu cầu, lập luận ẩn, phản hồi và tool call
  - `llm_full.jsonl`: cùng nội dung, dạng thô
  - `trajectories/` và `runs/`
- Chi tiêu vẫn được ghi vào sổ ngân sách bền vững. Console in mọi bước của agent và mọi lệnh gọi LLM.
- Dựng lại transcript bằng `python scripts/show_debug.py <dir>`.
