# Độ trung thực của baseline: mã gốc nào được dùng, hạ tầng nào đã thay, sai lệch nào còn lại

Ba baseline (B1 Meta-Harness, B2 ModularRSI, B3 MemoHarness) được đưa về sát mã gốc nhất có thể trên harness H0 và các adapter benchmark của chúng tôi. Repo gốc không chạy nguyên khối được vì phụ thuộc vào Harbor, Docker, Daytona/e2b/Modal, Claude Code và Codex CLI. Vì vậy mỗi baseline được chia thành ba phần:

- **(a) Mã gốc được tái sử dụng:** file và hàm nguồn. Mã gốc không có phụ thuộc Harbor thì được copy hoặc import; phần còn lại được copy vào `baselines/vendor/<repo>/` kèm tiêu đề ghi nguồn và danh sách thay đổi.
- **(b) Sửa hạ tầng:** thay phần gọi thực thi, gọi LLM, đường dẫn, và định dạng ghi kết quả. Thuật toán và ngưỡng không đổi.
- **(c) Sai lệch còn lại:** mỗi điểm lệch có lý do.

Nguyên tắc: chỉ thay hạ tầng. Thuật toán, ngưỡng và prompt được giữ nguyên, trừ khi mã gốc không thể chạy trong môi trường này (khi đó ghi rõ ở (c)).

## Giấy phép và ghi nguồn

| repo | giấy phép | cách dùng trong dự án |
|---|---|---|
| Meta-Harness (`stanford-iris-lab/meta-harness`) | MIT | copy hàm vào `baselines/b1_freeform.py`; SKILL.md được chép có chỉnh sửa (xem B1 (a)) |
| ModularRSI (`IQuestLab/ModularRSI`, commit `b5c72c3`) | **CC BY-NC 4.0: chỉ dùng cho nghiên cứu phi thương mại.** Ghi nguồn: Wu et al. 2026, arXiv 2609.14857 | vendored tại `baselines/vendor/modularrsi/`, mỗi file có tiêu đề ghi nguồn và thay đổi |
| MemoHarness (`HowieHwong/MemoHarness`) | **Repo không có tệp LICENSE.** Chủ dự án đã được tác giả cho phép sao chép mã, ngày và hình thức cấp phép: `<ngày / hình thức cấp phép>` | vendored tại `baselines/vendor/memoharness/`, mỗi file có tiêu đề ghi nguồn và thay đổi |

## Giao thức chung (B1, B2, B3)

| hạng mục | giá trị |
|---|---|
| seed | cùng một H0 (`h0/`, bundle mặc định) cho mọi phương pháp; hash `c7e35268c202` (`baselines/common.py::tree_hash`) |
| model | một model cho mọi lệnh gọi (agent, proposer, composer, judge, controller): `inclusionai/ling-3.0-flash` qua OpenRouter, đi qua `llm.py` |
| tác vụ | id train / val / test giống nhau cho mỗi benchmark (`protocol_tasks`, `results/runs/protocol/<bench>.json`) |
| bằng chứng dùng chung | H0 trên các tác vụ train với **K=3 roll** mỗi tác vụ, và H0 trên các tác vụ val; thực thi một lần, đưa cho mọi phương pháp (`results/h0_<bench>.jsonl`) |
| số vòng | `SMOKE["rounds"]` = 1 |
| kiểm tra (canary / smoke) | `cfg["n_check"]` tác vụ train, cùng kích thước cho mọi phương pháp |
| validation | `cfg["n_val"]` tác vụ val |
| quy tắc chọn | `common.better`: thành công val cao hơn; hòa thì ít token hơn; H0 là ứng viên đầu |
| đóng băng | trước lần kiểm thử, mọi thứ học được được đóng băng (B3: `bank.frozen=True`); lần kiểm thử không ghi lại gì |
| AppWorld | chỉ dùng split `test_normal`; không ai đọc nội dung; chỉ lưu tổng hợp đạt/trượt |
| kiểm tra dữ liệu | `scripts/run_baselines.py` từ chối bằng chứng H0 có hash khác và từ chối tác vụ train thiếu roll (cần đủ K=3) |

Các lệnh gọi LLM của thực thi (agent) và các lệnh gọi phục vụ tiến hóa (proposer, investigator, reviewer, composer, controller, distiller, judge) không được tính vào một ngân sách chung. Chi phí USD của từng nhóm được ghi trong sổ chi tiêu (`results/llm_calls.jsonl`, `results/spend.json`). Đây là bất đối xứng còn lại chính: B2 và B3 thêm một lệnh gọi LLM cho mỗi tác vụ lúc val và test, đúng như trong các bài báo gốc.

Tất cả baseline dùng `client.chat(..., fallback_no_reasoning=True)`. Mô hình có lập luận ẩn và đôi khi dùng hết `max_tokens` cho lập luận, khiến nội dung trả về rỗng. Lệnh gọi lỗi được thử lại một lần với `reasoning` tắt.

---

## B1. Meta-Harness (`baselines/b1_freeform.py`)

### (a) Mã gốc được tái sử dụng
Nguồn: `third_party/meta-harness/reference_examples/terminal_bench_2/`.

| phần | nguồn | cách dùng |
|---|---|---|
| `compute_pass_rates` | `meta_harness.py` (dòng 256–271) | copy nguyên văn |
| `summarize_trial_metrics` | `meta_harness.py` (310–356) | copy nguyên văn |
| `update_frontier` | `meta_harness.py` (373–393) | copy; đường dẫn là tham số; định dạng `{task: {"best_agent", "pass_rate"}, "_best": {"agent", "avg_pass_rate"}}` |
| `update_evolution_summary` | `meta_harness.py` (396–428) | copy; đường dẫn là tham số; thêm trường `rollout_metrics` |
| `render_task_prompt` | `meta_harness.py` (530–547) | viết lại theo cấu trúc, giữ các dòng về đường dẫn run và "Write pending_eval.json to" |
| file `pending_eval.json` | `meta_harness.py` (`PENDING_EVAL`, dòng 83) | ghi sau bước phân tích; đọc sau khi gọi |
| vòng validate → smoke → benchmark | `run_evolve` (dòng 700–800) | cùng thứ tự; `validate_candidate` + `smoke_test` → `C.static_gate` + `C.evaluate` trên `n_check` tác vụ |
| SKILL.md | `.claude/skills/meta-harness-terminal-bench-2/SKILL.md` (MIT) | giữ nguyên văn tiêu đề, CRITICAL CONSTRAINTS, quy tắc chống quá khớp, nguyên tắc thiết kế, quy trình Bước 1–3, IMPORTANT NOTES, có thay đổi sau |

**Thay đổi trong SKILL.md** (đã ghi trong mã tại `SKILL_CHANGES`):
1. tiêu đề và mô tả: "Terminal Bench 2" → tên benchmark;
2. "`meta_harness.py`" → "`baselines/b1_freeform.py`";
3. CONTEXT: AgentHarness, `agents/baseline_kira.py`, Claude Opus 4.6, 89 tác vụ TB2, ràng buộc kế thừa Terminus2 → file slot H0, split theo giao thức, model của chúng tôi;
4. "CANDIDATE DESIGN": một file `agents/<name>.py` → tập file slot;
5. "Key methods" của Terminus2 → năm Protocol slot;
6. "CANNOT modify meta_harness.py, claude_wrapper.py" → hợp đồng file H0;
7. Bước 1 và 2: "Launch ONE Agent subagent" → một lệnh gọi mô hình cho mỗi bước; Bước 1 thêm `PARENT:` (chọn cha trong pool); Bước 1.3 "Read agent implementations in `agents/*.py`" → đọc mã H0 đầy đủ và từng ứng viên trong pool dưới dạng diff so với H0;
8. JSON Bước 3: `import_path` → `parent`; ghi chú về `agents/<name>.py` được bỏ;
9. IMPORTANT NOTES: tên lớp `AgentHarness`, phương thức async, litellm, placeholder của template prompt, giới hạn 30 KB bị bỏ; thêm ghi chú về hợp đồng slot và việc không có tool.

### (b) Sửa hạ tầng
- Đường dẫn (`PENDING_EVAL`, `FRONTIER_VAL`, `EVOLUTION_SUMMARY`) là tham số hàm thay vì biến toàn cục của module.
- `harbor_run`, `parse_job_results`, `parse_trial_metrics` được thay bằng `C.evaluate` và bản ghi episode của chúng tôi. Không có bước đọc `result.json` của Harbor.
- Proposer là hai lệnh gọi tới model của chúng tôi (xem (c)).
- Thay vì `claude_wrapper.run`: `client.chat` với `tag="b1:analyze:<bench>"` và `tag="b1:implement:<bench>"`.
- Validate: `C.static_gate` (import, registry, toy run). Smoke: `C.evaluate` trên `cfg["n_check"]` tác vụ train, lỗi bị tính là crash.
- Điểm số: `compute_pass_rates({task: [reward]})`, với reward = 1 nếu thành công. Đây là mỗi tác vụ một roll trên tập val.
- `summarize_trial_metrics` nhận `trial_metrics_of(recs)`: `cost_usd` = chi phí, `n_turns` = số bước, `n_input_tokens` = tổng token (xem (c)).
- **Biến thể mới phải được `bundle.json` chọn** (SKILL thay đổi 9, `unselected_variants`): trong mã gốc mỗi ứng viên *là* file agent mới (`import_path`), nên luôn chạy. Trong H0, file biến thể mới chỉ chạy khi `bundle.json` chọn nó. Lần MEDIUM đầu, harness cuối của B1 trên BrowseComp-Plus và AppWorld chỉ chứa biến thể không được chọn (và `SearchMemory` mà H0 không bao giờ gọi `update`), tức hành vi y hệt H0. Nay SKILL và prompt triển khai nói rõ điều này, và ứng viên có biến thể không được chọn bị coi là trượt cổng (có một lượt sửa). B1 trên hai benchmark này được chạy lại (bản ghi cũ ở `results/medium/aborted_unselected/`).
- **Khôi phục token `<arg_value>` trong reply của proposer** (`proposer_io.restore_special_tokens`, dùng chung cho B1 và B2): model không xuất được chuỗi `<arg_value>` (token gọi tool của chính nó), mà trả về `">`. Mỗi bản chép `tool_policy/default.py` của H0 vì thế mất token và hỏng regex (`unterminated string literal`). Trong lần chạy MEDIUM đầu tiên, 3/5 vòng B1 trên ALFWorld bị loại ở cổng tĩnh vì lỗi này; B1 được chạy lại sau khi sửa (bản ghi cũ ở `results/medium/aborted_argvalue/`). Chỉ khôi phục ngay sau `</arg_key>` hoặc trong `<arg_key>/`, nơi `">` không thể là ý định của model. Đây là sửa lớp truyền tin, không đổi thuật toán.

### (c) Sai lệch còn lại
- **Proposer không có hệ thống tệp.** Meta-Harness cho Claude Code đọc tệp bằng công cụ. Ở đây mọi tệp được render vào prompt:
  - Bước phân tích thấy mã của mọi ứng viên (`_pool_code`): H0 đầy đủ, mỗi ứng viên khác là unified diff so với H0 (Bước 1.3 của SKILL.md).
  - Bước triển khai thấy toàn bộ mã cha, không cắt (`tree_text(root, None)`; riêng H0 đã 18 776 ký tự, giới hạn cũ 20 000 ký tự cắt mất mã của ứng viên lớn hơn).
  - **Quỹ đạo vẫn là bản tóm tắt, không phải trace gốc** (sai lệch chính còn lại của B1): tối đa `MAX_TRAJ_IN_PROMPT = 24` quỹ đạo, mỗi quỹ đạo 60 sự kiện cuối, mỗi sự kiện 600 ký tự. Đầu mỗi quỹ đạo có chỉ dẫn tác vụ (`TASK_CHARS = 1500` ký tự, `summarize_trajectory(task_chars=...)`); B2/B3 giữ mặc định 0.
- **Hai bước, hai lệnh gọi.** Bước 1+3 (phân tích, chọn cha, ghi `pending_eval.json`) là một lệnh gọi. Bước 2 (triển khai) là lệnh gọi thứ hai. Meta-Harness dùng hai subagent có công cụ.
- **Chọn cha trong pool.** Proposer có thể chọn bất kỳ ứng viên nào đã qua validate (H0 và `candidates/r*`). Nếu tên cha không hợp lệ, dùng `cand.parent` hoặc H0.
- **Một ứng viên mỗi vòng**, và một vòng (`SMOKE`). Bài báo dùng nhiều vòng trên 89 tác vụ × 2 lần thử.
- **Lời nhắc "one mechanism per candidate"** được giữ, nhưng không có cơ chế kiểm tra rằng một ứng viên chỉ thay đổi một cơ chế.
- **Tổng token trong `rollout_metrics`:** `llm.py` ghi tổng token, không tách input và output, nên `n_output_tokens` và `n_cache_tokens` để trống.
- **Validation chỉ trên tập val nhỏ** (`n_val` tác vụ, mỗi tác vụ một roll). Thăng hạng theo luật chung `C.better` (chứ không theo `frontier`). `frontier_val.json` vẫn được cập nhật đúng định dạng để proposer đọc.
- **Hợp đồng slot được giữ ở tầng prompt.** Vì tệp được render sẵn, lỗi import chỉ bị phát hiện bởi cổng tĩnh; không có kiểm tra trước khi render.

---

## B2. ModularRSI (`baselines/b2_modular.py`, vendored tại `baselines/vendor/modularrsi/`)

### (a) Mã gốc được tái sử dụng
Nguồn: `third_party/ModularRSI/src/harbor/agents/terminus_2_modular/self_evo/` (commit `b5c72c3`, CC BY-NC 4.0, nghiên cứu phi thương mại). Mỗi file vendored giữ nguyên logic. Chỉ đổi đường dẫn import, trừ hai file bị cắt các hàm phụ thuộc Harbor (ghi trong header của file).

| file vendored | nguồn | thay đổi |
|---|---|---|
| `trajectory_analysis.py` | `self_evo/trajectory_analysis.py` | copy nguyên văn (chỉ đổi header và đường dẫn import). Lấy: `_MODULE_LENS`, `_module_lens`, `TrialSummary`, các preamble điều tra và review, `_CONTRAST_FINDING_RE`, `loads_finding_block`, các hằng `PARSE_*` |
| `router.py` | `self_evo/router.py` | copy; một dòng import đổi thành `baselines.vendor.modularrsi.trajectory_analysis`. Lấy: `Bucket`, `RouterConfig`, `classify`, `Ledger`, `route_batch` |
| `review_verdict.py` | `self_evo/review_verdict.py` | copy nguyên văn. Lấy: `validate_attrs`, `_normalize` |
| `prompts.py` | `trajectory_analysis.py`, `composer/llm_dynamic.py::_llm_pick` | không phải copy văn bản: import hằng từ file vendored, cắt khối công cụ bằng `re.subn` có khẳng định đúng một lần khớp. Composer lấy từ `_llm_pick`, bỏ khối helper |
| `backlog.py` | `self_evo/backlog.py` | copy nguyên văn. Sổ finding `backlog/findings.jsonl` với id ổn định. Mọi finding đều được ghi, kể cả culprit không sửa được ngay |
| `routing.py` | `self_evo/routing.py` | copy nguyên văn. Lấy: `validate_routing`, `parse_routing`, `looks_truncated`, `build_routing_instruction`, `MODULE_BOUNDARIES` |
| `clustering.py` | `self_evo/clustering.py` | copy nguyên văn. `cluster_finding`: một finding thành đề xuất mới, hoặc gắn vào đề xuất đang mở cùng can thiệp |
| `proposals.py` | `self_evo/proposals.py` | copy nguyên văn. Máy trạng thái: open, selected, attempted, promoted, rejected_proposal, rejected_implementation, taboo, superseded |
| `portfolio.py` | `self_evo/portfolio.py` | copy nguyên văn. `select_portfolio`: tối đa một đề xuất mỗi làn (incumbent, novelty), xếp hạng theo số lần thử, tuổi, số tác vụ hỗ trợ |
| `dual_implement.py` | `self_evo/dual_implement.py` | copy nguyên văn. `implement_lanes`: các làn không thấy nhau, mỗi làn có cây staging riêng. Hai callable của chúng tôi thay cho editor: `prepare` và `run_lane` |
| `rebase.py` | `self_evo/rebase.py` | copy nguyên văn. `rebase_onto` đưa làn thứ hai lên cây đã hợp nhất |
| `promotion.py` | `self_evo/promotion.py` | copy nguyên văn. `plan_promotions`, `gates_after_rebase` |
| `routing_probe.py` | `self_evo/routing_probe.py` | copy `probe_routing` và `RoutingProbeResult`. **Bỏ** `retired_quals`, `load_instructions`, `make_composer_chooser`, vì chúng đọc archive, composer và cache tác vụ của Harbor |
| `confirm.py` | `self_evo/confirm.py` | copy các hàm thống kê thuần: `variant_pass_stats`, `paired_delta`, `find_regressions`, `helper_*`, `_samples_from_records`. **Bỏ** `confirm_and_rollback*` và `_active_quals`, vì chúng đọc archive của Harbor |
| `lease.py` | `self_evo/lease.py` | copy nguyên văn. Nhật ký thuê (`selected`, `attempt_started`, `attempt_finished`); `recover` chạy đầu mỗi vòng |
| `dispositions.py` | `self_evo/dispositions.py` | copy nguyên văn. Các phán quyết (out_of_scope, covered, stale, invalid) không bị định tuyến lại; `retryable` thì định tuyến lại |
| `staging.py` | `self_evo/staging.py` | copy nguyên văn (`dual_implement` import). Bước chuẩn bị cây của B2 là `_prepare` riêng |

Không vendor: `online_evo.py` (điều phối cửa sổ), `k_roll.py`, `evidence_pass.py`, `editor_memory.py`, `run_editor.py`, `smoke_tests.py`, `task_runner.py`, `phase0.py`, `state.py`, `manifest.py`, `action_gate.py`, `two_lane.py`, `editor_skills/`. Các file này chạy editor, agent hoặc Harbor job, hoặc chỉ phục vụ điều phối nhiều cửa sổ mà smoke run không dùng. `evidence_pass.py` chứa LLM hook `same_intervention` mà `clustering.py` gọi; phần đó được viết lại (xem (c)).

### (b) Sửa hạ tầng
- **Harbor → lớp thực thi của chúng tôi.** Mọi đánh giá đi qua `C.evaluate`, theo mục "Lớp thực thi" bên dưới.
- **Bản ghi → `TrialSummary`** (`to_summary`): `reward = 1.0/0.0`; lỗi hạ tầng (`error` khác rỗng) thành `reward=None`, nên router coi là "không có verdict" (`infra_only`) và `variant_pass_stats` bỏ qua. Đây là quy tắc của `_is_real_fail`.
- **Số bước và tỷ lệ lặp** lấy từ quỹ đạo (`C.traj_stats`).
- **Sổ ledger của router** lưu tại `results/runs/b2/<bench>/router_ledger.json`. Cuối mỗi vòng, `record_reflection` ghi các tác vụ bị nhắm tới.
- **Trạng thái theo lần chạy:** `backlog/`, `staging/`, `work/` trong `results/runs/b2/<bench>/` bị xoá khi bắt đầu mỗi lần chạy, để id đề xuất của lần trước không rò sang lần sau.
- **Định tuyến và gắn cụm (bước 4):** mỗi finding culprit có `fixable_now=true` được định tuyến bằng một lời gọi (`b2:route:<bench>`) và kiểm tra bằng `validate_routing`. Reply bị cắt ở giới hạn token thành `retryable`; reply sai thành `invalid`. Cả hai ghi qua `dispositions`.
- **Phán đoán cùng can thiệp** (`Judge.same_intervention`): mỗi đề xuất đang mở của cùng module là một lời gọi `b2:same:<bench>`. Không so sánh chéo module.
- **Cổng làn** (bước 6): `static_gate` của biến thể mới, reviewer (`b2:review`), `reject_class="implementation"` kèm `repair_brief` được sửa một lần trong cùng vòng. Routing không nằm trong cổng: sau reviewer, `routing_diagnosis` chạy routing probe một lần; nếu composer không chọn biến thể ở tác vụ train nào, `description` của biến thể được viết lại đúng một lần (`b2:describe:<bench>`) rồi probe lại. Cả hai kết quả ghi vào `detail["routing"]`, và làn không bị loại vì kết quả đó.
- **Hợp nhất** (bước 7): làn đầu được copy lên cây ứng viên. Làn thứ hai: `rebase_onto` lên cây đó; nếu `gates_after_rebase` không cho dùng lại review thì chạy lại review; luôn chạy lại `static_gate` trên cây đã rebase (routing không chạy lại vì chỉ là chẩn đoán). Chỉ khi cả hai qua, cây ứng viên mới được thay bằng cây đã rebase.
- **Niche-dedup gate** (bước 6, sau static gate và trước reviewer như `online_evo._gate_and_promote`): `niche_reject` dùng `niche.niche_key` đã vendor trên registry H0. Biến thể mới phải khai báo `niche` và không được trùng ô niche của biến thể khác cùng slot (implementer của ta không khai báo SUPERSEDES, nên trùng là bị loại). Prompt implementer liệt kê các ô niche hiện có.
- **Thăng hạng** (bước 8): như mã gốc, chỉ theo cổng: smoke/static gate, niche-dedup, reviewer, sanity crash check (`n_check` tác vụ train, biến thể được ghim). Không so reward, không có val.
- **Cửa sổ và bằng chứng** (bước 9): cửa sổ 1 dùng bằng chứng H0 chung (K=3 roll trên 50 tác vụ train). Mỗi cửa sổ sau học từ K=3 roll của **thư viện hiện tại** (composer chọn biến thể theo tác vụ) trên một lô `n_val // K` tác vụ train mới, luân phiên qua tập train. Ngân sách mỗi vòng giữ nguyên (`n_check + n_val` episode).
- **Đóng đề xuất:** làn được thăng hạng → `promoted`. Làn không qua cổng → `rejected_proposal` nếu reviewer báo `proposal`, còn lại `rejected_implementation`.
- **Lệnh gọi LLM:** tag `b2:<kind>:<bench>`, với kind ∈ `investigate`, `efficiency`, `route`, `same`, `implement`, `review`, `describe`, `composer`.

### (c) Sai lệch còn lại
- **Không có tool và không đọc tệp bằng công cụ.** Investigator và reviewer nhận quỹ đạo đã render và mã slot được nhúng trong prompt. ModularRSI bắt model tự đọc bằng tool; các khối đó đã bị cắt.
- **Không có điều phối nhiều cửa sổ.** `online_evo.py` không được vendor. Smoke run chỉ có một vòng, nên không có lineage, không có taboo qua nhiều cửa sổ, và `recover` chỉ được gọi để ghi journal.
- **Phán đoán cùng can thiệp là của chúng tôi.** Bản gốc nằm ở LLM hook trong `evidence_pass.py`, không vendor. `SAME_PROMPT` và `Judge` viết mới; khi reply không có boolean, clustering ghi `comparison_unresolved`.
- **Routing probe là chẩn đoán, không phải cổng.** Trước đây, làn chỉ được thăng hạng khi có `routing_proven`. Nay routing chỉ là chẩn đoán, như docstring của `routing_probe.py` mô tả. Biến thể không được composer chọn được viết lại mô tả đúng một lần rồi probe lại; kết quả được ghi nhận nhưng không loại làn. Lý do: một mô tả kém không có nghĩa là cài đặt kém. Đây là khác biệt có chủ đích.
- **Làn chạy tuần tự.** `dual_implement.implement_lanes` dùng `asyncio.gather`, nhưng lời gọi LLM là đồng bộ nên các làn chạy lần lượt.
- **Implementer luôn tạo biến thể mới (file sibling), kể cả với `modify`.** Thư viện chỉ được cộng thêm; `default.py` không bị sửa. Bản gốc sửa tệp tại chỗ với `modify`.
- **Sửa lần 2 xảy ra trong cùng vòng.** Bản gốc thử lại làn ở cửa sổ sau (`retry=True`, `repair_brief`).
- **Brief của implementer là bản viết lại.** `_brief_text` lấy nội dung của brief gốc (đề xuất và mọi finding hỗ trợ, kể cả finding không đọc được từ sổ). Phần hướng dẫn công cụ của brief gốc bị bỏ.
- **Không chạy `confirm` (thống kê hồi quy ghép cặp).** Thăng hạng không còn dựa trên val, nên không có roll ghép cặp để xác nhận.
- **Chẩn đoán tối đa `MAX_DIAG=10` tác vụ mỗi vòng** (mã gốc điều tra cả lô).
- **Efficiency investigator không tham gia chọn làn** (như cũ).
- **Không có helper subset** (`tool_helper`), vì H0 không có helper.
- **Prompt riêng:** `IMPLEMENT`, `FIX`, `REPAIR`, `PROTO`, `SAME_PROMPT` là của chúng tôi. Prompt composer và prompt điều tra là bản cắt của mã gốc.
- **`review_verdict` không có `accept_partial`:** giữ nguyên như mã gốc (chưa được bật).
- **Một module mỗi lineage → tất cả slot mỗi vòng.** Mã gốc chạy mỗi lineage với một `--locked-module`, rồi mới tích hợp chéo module. Ở đây mỗi vòng điều tra cả 5 slot, và composer chọn trên mọi slot.
- **Giao thức memory:** prompt `PROTO` nay ghi rõ mỗi episode dựng harness mới và `update()` không bao giờ được gọi (lần MEDIUM đầu, `memory/token_recall` được thăng hạng nhưng vô tác dụng vì điều này).
- **Không có action gate.** Implementer của ta luôn thêm biến thể mới (kể cả với `modify`), nên kiểm tra `check_action` của mã gốc (modify phải sửa đúng mục tiêu) không áp dụng được.
- **`history_pass_lookup=None`** khi gọi `route_batch`: router không dùng lịch sử pass của các cửa sổ trước.
- **Efficiency investigator chỉ chạy khi không có culprit** (như mã gốc).
- **Prompt composer:** "terminal coding agent" đổi thành "LLM agent"; phần còn lại là văn bản của `_llm_pick`.

---

## B3. MemoHarness (`baselines/b3_memo.py`, vendored tại `baselines/vendor/memoharness/`)

### (a) Mã gốc được tái sử dụng
Nguồn: `third_party/MemoHarness/src/memoharness/` (commit `4c3da18`). Repo không có LICENSE; sao chép theo cho phép `<ngày / hình thức cấp phép>`.

| file vendored | nguồn | dùng gì |
|---|---|---|
| `core/models.py` | `core/models.py` | nguyên văn: `PerCaseEntry`, `CaseFeatures`, `HarnessConfig`, `Diagnosis`, `GlobalPattern`, `make_minimal_config` ... |
| `bank/experience.py` | `bank/experience.py` | nguyên văn: `ExperienceBank` (`add_entry`, `should_distill`, `distill_global_patterns_llm`, `retrieve_similar_cases_for_case`); chỉ thay cặp embedding bằng BM25 |
| `llm/distiller.py`, `llm/retry.py` | cùng tên | nguyên văn: `LLMDistiller` (client thay bằng `ChatShim`) |
| `controllers/llm_controller.py` | cùng tên | nguyên văn: `LLMController` làm helper (`stabilize_config`, `_parse_config_response`, `_build_case_summary`, `_CONFIG_ONLY_DOC`, `_DIMENSIONS_DOC`) |
| `controllers/local_cli.py` | cùng tên | nguyên văn: `ClaudeCodeController`/`CodexController`: `adapt_for_case` (prompt thích nghi của controller Codex), `_build_iteration_bank_summary`, `_build_task_history_matrix`, `_build_recent_failure_excerpt`, `_build_iteration_signal_summary`, `_run_direct_edit_harness_with_retry`, `_build_direct_edit_retry_prompt` |
| `controllers/codex_bundle.py` | cùng tên | nguyên văn: `CodexBundleController` (`decide_next_harness`, `_build_iteration_bundle_prompt` gồm "Hard Constraints On What You May Write" và ngân sách bundle 9000 ký tự, `_load_live_harness_state`, snapshot/restore) |
| `runtime/codex_bundle.py` | cùng tên | nguyên văn: bố cục bundle (`AGENTS.override.md`, `policy.json`, `.memoharness/playbook.md`, `.memoharness/memory.md`), `refresh_codex_bundle_support_docs`, render memory/playbook từ mẫu chưng cất |
| `config/runtime.py` | cùng tên | nguyên văn: ngưỡng canary `-0.34`, `0` |

Pipeline giữ đúng `harbor/loop.py::run()` với controller duy nhất mã gốc cho phép (`controller="codex"`):
1. Mỗi vòng, harness hiện tại chạy trên tập train; kết quả (bỏ blocker) vào ngân hàng; trigger chưng cất (`add_entry` trả `True` khi một ca thất bại 3 lần liên tiếp, hoặc `should_distill(5)`); mẫu được **nối thêm** (`distill_global_patterns_llm`) và `memory.md`/`playbook.md`/`policy.json` của bundle sống được render lại (`refresh_codex_bundle_support_docs`).
2. Controller viết lại bundle từ bằng chứng (prompt `_build_iteration_bundle_prompt` của mã gốc), có cổng công bố và tối đa 3 lần thử lại.
3. Canary so với kết quả của harness hiện tại trên cùng tác vụ (ba luật của `_evaluate_candidate_with_canary`); không qua thì khôi phục bundle (`restore_codex_bundle`).
4. Chọn harness: vòng có reward train trung bình cao nhất, hòa thì ít token hơn ("correctness-first selection" của README). Không có val.
5. Lúc test: ngân hàng đóng băng; mỗi ca gọi `adapt_for_case` (chỉ đổi cấu hình D1–D6, dựa trên ca tương tự), rồi bundle được render với cấu hình đã thích nghi (`_apply_eval_config`).

### (b) Sửa hạ tầng
- **Truyền tin của controller** (`BundleController`, kế thừa `CodexBundleController`): thay Codex CLI (`_run_controller_command`) bằng một lệnh gọi `client.chat` (tag `b3:controller:<bench>`, thích nghi: `b3:adapt:<bench>`). Controller không có tool, nên các tệp bundle được đưa nguyên văn vào prompt (`_on_disk_state_doc`) và model trả về các khối `### FILE:` cho tệp nó viết lại; các khối này được ghi vào bundle trước khi loader gốc đọc lại. Các đoạn prompt mô tả workspace CLI được thay: `_project_brief_doc` (bundle cho agent ReAct trên benchmark, và **chỉ `D3.temperature`, `D3.max_tokens`, `D5.history_keep` đổi tham số chạy thật**), `_controller_command_scope_doc` (không có tool, định dạng FILE), `_bundle_inspection_doc`, `_targeted_supporting_evidence_doc`, `_direct_edit_finish_doc` (cổng công bố do bên gọi chạy).
- **Cổng công bố** (`publish_gate`): các kiểm tra mà "Required Finish State" của mã gốc yêu cầu Codex tự chạy (policy.json là JSON hợp lệ có `config` với D1–D6, AGENTS.override.md không rỗng, ngân sách 9000 ký tự) do bên gọi chạy; trượt → `BundleInvalid` → prompt thử lại của mã gốc.
- **Bundle → H0:** bốn tệp bundle được chèn vào system prompt (`context_mgmt.extra_system`), như agent Codex đọc chúng từ workspace. `D3.temperature`, `D3.max_tokens`, `D5.history_keep` ánh xạ sang `agent_loop.temperature`, `agent_loop.max_tokens`, `context_mgmt.keep_turns` (giới hạn [0,1], [256,4096], [4,60]).
- **Cấu hình gốc mô tả H0:** `base_config` đặt các số về giá trị của H0 và các khóa mô tả về đúng H0 (`tool_access=benchmark_tools`, `workflow=react_loop`, `stop_rule=env_done_or_accepted_finish_or_max_steps`, `memory_policy=sliding_window`, `validator=verifier_slot`) thay vì mặc định của Harbor (bash, `stop_rule=immediate`), vốn khiến chẩn đoán và chưng cất "sửa" các núm không tồn tại.
- **Embedding → BM25** (`BM25ExperienceBank`), **ChatShim** cho distiller, **đóng băng** ngân hàng trước test: như trước.
- **Canary** (`canary_metrics`, `canary_check`): số liệu theo tác vụ (trung bình các roll không lỗi; thành công khi ≥ 0,5), blocker bị loại khỏi reward; ba luật theo thứ tự gốc. Tham chiếu là kết quả của harness hiện tại trên cùng tác vụ canary (H0: cả K roll).
- **Ngân sách:** mỗi vòng `n_check` episode canary + `n_val` episode chạy train (30 tác vụ train đầu, mỗi tác vụ 1 roll), bằng ngân sách mỗi vòng của B1/B2.
- **Chẩn đoán:** mỗi episode thất bại được một lệnh gọi LLM gán `primary_dim` và `analysis` (theo lô 10 ca; mã gốc dùng `diagnostics: "llm"`), mặc định D4/D1 như mã gốc.

### (c) Sai lệch còn lại
- **Controller một lượt, không tool.** Codex CLI trong mã gốc tự đọc tệp, chạy lệnh kiểm tra và sửa nhiều lượt; ở đây là một lệnh gọi (cộng tối đa 2 lần thử lại khi trượt cổng công bố).
- **Agent không phải Codex.** Bundle điều khiển agent ReAct cố định của H0 qua system prompt; chỉ 3 tham số số có tác dụng runtime. Các khóa D1–D6 khác chỉ tác động qua văn bản.
- **Tập train mỗi vòng là 30 tác vụ** (mã gốc: toàn bộ tập train), để giữ ngân sách chung; vòng 0 là bằng chứng H0 chung trên 50 tác vụ × 3 roll.
- **Canary `n_check` = 2 tác vụ** (mã gốc: 6).
- **Đặc trưng ca tối thiểu** (độ dài chỉ dẫn, domain = benchmark).
- **Quy mô:** 5 vòng (bài báo: 10).
- **Bản port trước đây (chỉ đổi cấu hình, chọn trên val)** được giữ ở `results/medium/b3_configonly/` để so sánh; xem `docs/medium_results.md`.

**Bảng ánh xạ D1–D6 → H0** (giá trị có tác dụng runtime):

| khóa | tác động lên H0 |
|---|---|
| `D3.temperature` | `agent_loop.temperature` (giới hạn [0, 1]) |
| `D3.max_tokens` | `agent_loop.max_tokens` (giới hạn [256, 4096]) |
| `D5.history_keep` | `context_mgmt.keep_turns` (giới hạn [4, 60]) |
| mọi khóa khác, mọi `strategy`, AGENTS.override.md, playbook.md, memory.md | chỉ qua system prompt (`context_mgmt.extra_system`) |

---

## Lớp thực thi

Ba baseline dùng chung một lớp thực thi: `benchmarks/<bench>/adapter.py` và `C.evaluate(...)`, cùng giao thức (`SMOKE`) và cùng H0. Harbor không được dùng, vì theo yêu cầu của dự án nó không có adapter cho ALFWorld, AppWorld hay BrowseComp-Plus.

Thuật toán, prompt và luật chọn của baseline không phụ thuộc lớp này. Chúng chỉ đọc các trường `success`, `steps`, `tokens`, `cost`, `error`, `trajectory_path` của bản ghi. Các hàm vendored có gọi agent, editor hoặc Harbor (ví dụ `run_lane` của `dual_implement`, `probe_routing`) nhận callable của chúng tôi thay vì được viết lại.

## Đo tỉ lệ mã gốc và mã viết lại

Đo bằng `python scripts/copy_fidelity.py` (cần `pip install coverage`; script tự chạy `tests/` dưới coverage). Có hai cách đo, và số chính là cách đầu:
- **Theo dòng đã chạy (chính):** chỉ tính các dòng logic mà bộ test offline thực sự chạy. Dòng không chạy trong bộ test không vào mẫu.
- **Theo file (tĩnh):** tính mọi dòng logic của file, kể cả hàm không được dùng.

Quy tắc:
- **Dòng logic:** không rỗng, không phải comment, không nằm trong docstring, không phải câu lệnh import (import bị loại ở cả hai phía).
- **Dòng copy:** dòng logic của file mà nằm trong dãy con chung dài nhất, theo thứ tự, với file gốc (`difflib`). Dòng do chúng tôi viết không được tính là copy.
- **Dòng đã chạy:** dòng logic có số dòng nằm trong tập dòng mà coverage báo đã thực thi.
- **Phạm vi:** các file của baseline (file riêng và mọi file vendored mà nó dùng). Đo theo **file**: một file vendored được tính toàn bộ, kể cả hàm không được dùng.

| baseline | dòng logic đã chạy | trong đó được copy | tỉ lệ (đã chạy) | tỉ lệ (theo file) |
|---|---|---|---|---|
| B1 Meta-Harness | 82 | 38 | 46,3 % | 30,2 % (99 / 328) |
| B2 ModularRSI | 1194 | 910 | 76,2 % | 84,5 % (3368 / 3984) |
| B3 MemoHarness | 663 | 501 | 75,6 % | 88,3 % (2312 / 2619) |

Cách đọc:
- Với mẫu đã chạy, mỗi file vendor được copy gần như trọn vẹn (100 % từng file, vì là copy nguyên văn). Thứ kéo tỉ lệ xuống là mã tự viết có chạy trong test: `baselines/b2_modular.py` (252 dòng đã chạy, 0 copy), `vendor/modularrsi/prompts.py` (32 dòng, 0 copy) và `baselines/b3_memo.py` (162 dòng, 0 copy). B1 và B3 giảm so với lần đo trước vì các sửa lỗi canary, thích nghi và prompt phân tích là mã tự viết.
- B2 và B3 theo file cao chủ yếu vì vendor cả file. Ví dụ `trajectory_analysis.py` có 1248 dòng logic, phần lớn không chạy trong test.
- B1 là file do chúng tôi viết, chỉ copy hai hàm và `SKILL.md`. Tỉ lệ đã chạy chỉ tính phần Python; `SKILL.md` chỉ có trong số theo file.
- B1 được đối chiếu với hai ví dụ tham chiếu (`terminal_bench_2`, `text_classification`); báo cáo dùng kết quả của `terminal_bench_2`, cao hơn theo dòng đã chạy.

## Ghi chú về ngân sách
Mọi lệnh gọi trong tài liệu này đi qua `llm.py`, chịu cùng một trần `MAX_USD` và dừng khi vượt 80 %. Chi phí của từng phương pháp được ghi trong `results/llm_calls.jsonl` theo tag (`b1:*`, `b2:*`, `b3:*`).
