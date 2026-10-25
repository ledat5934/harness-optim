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
7. Bước 1 và 2: "Launch ONE Agent subagent" → một lệnh gọi mô hình cho mỗi bước; Bước 1 thêm `PARENT:` (chọn cha trong pool);
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

### (c) Sai lệch còn lại
- **Proposer không có hệ thống tệp.** Meta-Harness cho Claude Code đọc tệp bằng công cụ. Ở đây mọi tệp (mã cha, mã các ứng viên khác, quỹ đạo, frontier, tóm tắt) được render vào prompt, có giới hạn: tối đa `MAX_TRAJ_IN_PROMPT = 24` quỹ đạo, mỗi quỹ đạo tối đa 60 sự kiện.
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
- **Xác nhận** (bước 8): `find_regressions` chạy trên các roll validation. Hồi quy được ghi vào `confirm_regressions` và chặn thăng hạng.
- **Thăng hạng cuối:** luật chung `C.better` quyết định. Điều kiện bổ sung là không có hồi quy từ xác nhận.
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
- **Xác nhận gần như không kích hoạt ở smoke.** Mỗi tác vụ validation chỉ có một roll, nên không tác vụ nào có cả biến thể lẫn default; `paired_delta` trả `None`. Hàm vẫn được gọi và ghi kết quả.
- **Chẩn đoán tối đa `MAX_DIAG=4` tác vụ mỗi vòng.**
- **Efficiency investigator vẫn không tham gia chọn làn** (như cũ).
- **Không có helper subset** (`tool_helper`), vì H0 không có helper.
- **Prompt riêng:** `IMPLEMENT`, `FIX`, `REPAIR`, `PROTO`, `SAME_PROMPT` là của chúng tôi. Prompt composer và prompt điều tra là bản cắt của mã gốc.
- **`review_verdict` không có `accept_partial`:** giữ nguyên như mã gốc (chưa được bật).

---

## B3. MemoHarness (`baselines/b3_memo.py`, vendored tại `baselines/vendor/memoharness/`)

### (a) Mã gốc được tái sử dụng
Nguồn: `third_party/MemoHarness/src/memoharness/`. Repo không có LICENSE; sao chép theo cho phép `<ngày / hình thức cấp phép>`.

| file vendored | nguồn | thay đổi |
|---|---|---|
| `vendor/memoharness/core/models.py` | `core/models.py` | copy nguyên văn: `PerCaseEntry`, `CaseFeatures`, `CaseStats`, `HarnessConfig` (`clone`, `delta_from`, `as_dict`), `Diagnosis`, `DiagnosticSignal`, `Trajectory`, `BenchmarkCase`, `GlobalPattern`, `make_minimal_config` |
| `vendor/memoharness/bank/experience.py` | `bank/experience.py` | copy nguyên văn: `ExperienceBank` gồm `add_entry`, `should_distill`, `mark_distill_done`, `_check_consecutive_failure_trigger`, `retrieve_similar_cases_for_case`, `_case_similarity`, `save`, `load` |
| `vendor/memoharness/llm/distiller.py` | `llm/distiller.py` | copy nguyên văn: `LLMDistiller.distill`, `_build_prompt`, `_parse_patterns`, `_SYSTEM_PROMPT`. Phần truyền tin (`_call_llm`) không đổi, nhưng client được thay bằng `ChatShim` (xem (b)) |
| `vendor/memoharness/llm/retry.py` | `llm/retry.py` | copy nguyên văn: `call_with_retries` |
| `vendor/memoharness/controllers/llm_controller.py` | `controllers/llm_controller.py` | copy nguyên văn: `LLMController` gồm `adapt_for_case`, `stabilize_config`, `_call_llm_for_config`, `_parse_config_response`, `_build_harness_config`, `_build_bank_summary`, `_build_change_outcome_signals`, `_build_case_summary`; các hằng `_CONFIG_ONLY_DOC`, `_DIMENSIONS_DOC`, `_DIMENSION_ACTION_PLAYBOOK_DOC` |
| `vendor/memoharness/config/runtime.py` | `config/runtime.py` | copy nguyên văn. Lấy `HarnessSettings`: `controller_canary_min_reward_delta = -0.34`, `controller_canary_max_blocker_increase = 0` |

Các file `__init__.py` của gói vendored chỉ là dòng ghi chú, không copy vì bản gốc re-export mã Harbor (`controllers/__init__.py` import `codex_bundle`).

Các phần được giữ nguyên trong bước chạy: ngân hàng hai lớp (mục theo ca + mẫu toàn cục), trigger chưng cất theo `should_distill(every_n_entries=5)` và theo `min_consecutive_failures=3` (kích hoạt ngay khi `add_entry` trả về `True`), tối đa `max_patterns=3`, `adapt_for_case` (một lệnh gọi, chỉ đổi cấu hình khi bằng chứng ca tương tự đủ), `stabilize_config`, `delta_from`, `_CONFIG_ONLY_DOC`.

### (b) Sửa hạ tầng
- **Truyền tin:** `ChatShim` cung cấp giao diện `chat.completions.create(...)` mà mã gốc gọi, và chuyển sang `client.chat` của `llm.py` với `fallback_no_reasoning=True`. Tag: `b3:controller:<bench>`, `b3:distill:<bench>`, `b3:diagnose:<bench>`.
  - Bốn từ khoá mà các chỗ gọi gốc truyền là `model`, `messages`, `temperature`, `max_completion_tokens`. `temperature` được chuyển tiếp (controller dùng 0.2, distiller 0.0). `max_completion_tokens` đổi thành `max_tokens`. `model` bị bỏ qua vì `llm.py` chọn model.
  - Từ khoá khác (ví dụ `response_format`, `seed`, `top_p`) làm `TypeError` thay vì bị bỏ im lặng. Trước lần sửa này `temperature` bị bỏ, nên controller chạy ở 0.0; test `test_chatshim_forwards_reference_kwargs` chốt hành vi này.
  - Đối tượng trả về chỉ có `choices[0].message.content`, đủ cho mọi chỗ đọc của mã gốc. Không có `usage` hay `finish_reason`.
  - Nhánh `client.responses` (Responses API) của `distiller.py` không được dùng: `_should_use_responses_api` trả `False` vì `api_base` không phải host của OpenAI, nên chỉ đường Chat Completions chạy.
- **`ApiModelConfig`** dùng `api_base` của OpenRouter và `connection_retry_limit=0`, để `_should_use_responses_api` chọn Chat Completions và để việc thử lại nằm ở `llm.py`.
- **Embedding → BM25** (`BM25ExperienceBank`): ghi đè hai hàm `_embed_text` và `_cosine_similarity`. Điểm là BM25 của truy vấn trên tài liệu, chia cho tự điểm của truy vấn, nên nằm trong [0, 1] như cosine thay thế. Corpus là chỉ dẫn các mục trong ngân hàng. `_case_similarity` và `retrieve_similar_cases_for_case` không đổi (cùng cách cộng điểm đặc trưng và top-k).
- **Đóng băng:** `add_entry` ghi đè để ném `RuntimeError` khi `frozen`; `bank.save` trước lần kiểm thử; kiểm tra số mục không đổi sau lần kiểm thử.
- **Ánh xạ D1–D6** (bảng dưới). `base_config` lấy `stabilize_config(make_minimal_config())`, sau đó **xóa chuỗi chiến lược** (H0 không có) và đặt lại các số đã ánh xạ về giá trị H0 (`temperature=0.0`, `max_tokens=2048`, `history_keep=30`). Nếu không, `make_minimal_config` đặt `max_tokens=256` và `history_keep=0`, và `stabilize_config` thêm chuỗi chiến lược: đều làm đổi H0.
- **Canary:** tham chiếu là H0 trên cùng các tác vụ, lấy trung bình trên cả K=3 roll. Ngưỡng là `CANARY_MIN_REWARD_DELTA` và `CANARY_MAX_BLOCKER_INCREASE` từ `HarnessSettings`.
- **Blocker:** số episode có trường `error` (lỗi hạ tầng). Tương đương tương đối với "external blocker" của MemoHarness.
- **Bằng chứng train:** toàn bộ K=3 roll mỗi tác vụ được đưa vào ngân hàng (iteration 0), không còn chỉ roll cuối.
- **Test-time adaptation:** cờ `TEST_TIME_CASE_ADAPTATION = True` (mặc định). Khi bật, mỗi tác vụ val và test gọi `adapt_for_case`; khi tắt, dùng cấu hình toàn cục đã chọn.

**Bảng ánh xạ D1–D6 → H0.** Chỉ các núm H0 có thể biểu diễn được áp dụng; các khóa còn lại của schema gốc vẫn nằm trong cấu hình (để controller thấy trong prompt) nhưng không tác động gì.

| khóa (schema gốc) | nghĩa trong MemoHarness | tác động lên H0 |
|---|---|---|
| `D1.strategy` | văn bản chiến lược lắp ráp ngữ cảnh | `context_mgmt.extra_system` (gộp chung với các chiến lược khác) |
| `D2.strategy` | văn bản chiến lược tương tác tool | `context_mgmt.extra_system` |
| `D2.tool_access`, `tool_protocol`, `retrieval_mode`, `top_k` | bề mặt tool của Harbor | không áp dụng: H0 có tool cố định |
| `D3.temperature` | nhiệt độ sinh | `agent_loop.temperature` (giới hạn [0, 1]) |
| `D3.max_tokens` | giới hạn token mỗi lệnh gọi | `agent_loop.max_tokens` (giới hạn [256, 4096]) |
| `D3.top_p`, `candidate_count` | | không áp dụng |
| `D4.strategy` | văn bản điều phối | `context_mgmt.extra_system` |
| `D4.workflow`, `stop_rule` | luồng agent của Harbor | không áp dụng: vòng lặp H0 cố định |
| `D5.history_keep` | số lượt gần nhất giữ trong ngữ cảnh | `context_mgmt.keep_turns` (giới hạn [4, 60]) |
| `D5.memory_policy` | | không áp dụng |
| `D5.strategy` | văn bản quản lý bộ nhớ | `context_mgmt.extra_system` |
| `D6.strategy` | văn bản xử lý đầu ra | `context_mgmt.extra_system` |
| `D6.postprocess`, `validator`, `fallback` | | không áp dụng |
| slot `memory` | (không nằm trong schema) | `ExperienceMemory`: luôn bật; truy hồi mẫu toàn cục và ca thất bại tương tự |

### (c) Sai lệch còn lại
- **Controller chỉ đổi bề mặt cấu hình D1–D6.** `LLMController` gốc sinh lại toàn bộ mã `HarnessImpl` (`decide_next_harness`, `generate_initial_harness`). Đây là sai lệch lớn nhất. Ở đây `ConfigController.propose` chỉ dùng `_CONFIG_ONLY_DOC` và `_call_llm_for_config`. Phần còn lại của harness không đổi (H0 là cố định, hợp đồng slot được giữ).
- **`ConfigController.propose` là mã tự viết.** `baselines/b3_memo.py` không copy hàm này. Hàm gốc tương ứng là `LLMController.decide_next_config` (`third_party/MemoHarness/src/memoharness/controllers/llm_controller.py:257`), và nó gọi `decide_next_harness` để sinh lại toàn bộ mã. `propose` tự ghép prompt cấu hình từ các khối văn bản gốc (`_DIMENSIONS_DOC`, `_DIMENSION_ACTION_PLAYBOOK_DOC`, `_CONFIG_ONLY_DOC`), rồi gọi `_call_llm_for_config` và `_build_harness_config` đã vendor. Vì `b3_memo.py` tính 0 dòng copy, dòng của `propose` không được tính vào tỉ lệ copy của B3, dù logic của nó dựa trên mã gốc.
- **Chỉ một phần khóa D được áp dụng** (bảng trên). Phần lớn tiềm năng cấu hình của MemoHarness (tool, luồng, xác thực đầu ra) không có tương ứng trong H0.
- **Chẩn đoán:** trong MemoHarness, `primary_dim` do quy tắc của `harbor/loop.py::_classify_trial_failure` xác định từ ngoại lệ của Harbor (rule-based, không có prompt LLM). Chúng tôi không có ngoại lệ Harbor, nên dùng một lệnh gọi LLM với văn bản chiều `_DIMENSIONS_DOC` của mã gốc. Mặc định khi thất bại là `D4`, khi thành công là `D1` (cùng quy tắc mặc định của mã gốc).
- **Đặc trưng ca được suy ra tối thiểu:** `input_length`, `complexity_estimate` (độ dài chỉ dẫn / 2000), `domain` = tên benchmark, `requires_external_knowledge` = (benchmark là BrowseComp-Plus). Mã gốc có đặc trưng do LLM gán cho từng ca; không có bước đó ở đây.
- **Canary:** `cfg["n_check"]` tác vụ thay vì 6 của MemoHarness (giữ kích thước giao thức chung). Kiểm tra là điểm trung bình của ứng viên so với H0 trên cùng tác vụ (trung bình K roll).
- **Quy mô:** một vòng tìm kiếm (bài báo: 10 vòng).
- **Mẫu toàn cục bị thay thế, không cộng dồn:** `distill` của mã gốc thêm vào `bank.global_patterns`; ở đây danh sách được thay bằng kết quả mới nhất, cắt còn `max_patterns=3`. Lý do: giữ bộ nhớ không vượt 3 mẫu trong suốt các vòng.
- **Lỗi của distiller:** `call_with_retries` của mã gốc bao lỗi thành `RuntimeError`, nên ngân sách hết sẽ dừng cả lần chạy. Đây là hành vi mong muốn, nhưng khác với các baseline khác (vốn ném `BudgetExceeded`).
- **Không truyền `temperature`:** `llm.py` quyết định nhiệt độ, nên giá trị 0.2 và 0.0 của mã gốc không được dùng.
- **Trường `ExperienceMemory`** (memory slot) là phần thêm vào của chúng tôi, không thuộc schema D1–D6. Được bật ở mọi ứng viên.
- **Cấu hình được clamp sau `_build_harness_config`:** mã gốc không giới hạn khoảng giá trị; chúng tôi giới hạn các số H0 áp dụng được, để một đề xuất hỏng không phá harness.

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
| B1 Meta-Harness | 68 | 37 | 54,4 % | 31,8 % (98 / 308) |
| B2 ModularRSI | 1194 | 910 | 76,2 % | 84,5 % (3368 / 3984) |
| B3 MemoHarness | 599 | 500 | 83,5 % | 90,1 % (2312 / 2565) |

Cách đọc:
- Với mẫu đã chạy, mỗi file vendor được copy gần như trọn vẹn (100 % từng file, vì là copy nguyên văn). Thứ kéo tỉ lệ xuống là mã tự viết có chạy trong test: `baselines/b2_modular.py` (252 dòng đã chạy, 0 copy), `vendor/modularrsi/prompts.py` (32 dòng, 0 copy) và `baselines/b3_memo.py` (99 dòng, 0 copy).
- B2 và B3 theo file cao chủ yếu vì vendor cả file. Ví dụ `trajectory_analysis.py` có 1248 dòng logic, phần lớn không chạy trong test.
- B1 là file do chúng tôi viết, chỉ copy hai hàm và `SKILL.md`. Tỉ lệ đã chạy chỉ tính phần Python; `SKILL.md` chỉ có trong số theo file.
- B1 được đối chiếu với hai ví dụ tham chiếu (`terminal_bench_2`, `text_classification`); báo cáo dùng kết quả của `terminal_bench_2`, cao hơn theo dòng đã chạy.

## Ghi chú về ngân sách
Mọi lệnh gọi trong tài liệu này đi qua `llm.py`, chịu cùng một trần `MAX_USD` và dừng khi vượt 80 %. Chi phí của từng phương pháp được ghi trong `results/llm_calls.jsonl` theo tag (`b1:*`, `b2:*`, `b3:*`).
