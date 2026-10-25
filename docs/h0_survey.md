# Khảo sát H0: ba repo baseline định nghĩa và tiến hóa harness hạt giống của chúng như thế nào

Mọi khẳng định dưới đây đều đến từ các tệp đã đọc trong các shallow clone dưới `third_party/`:

| repo | commit | giấy phép |
|---|---|---|
| IQuestLab/ModularRSI | `b5c72c3` | CC BY-NC 4.0 cho phần đóng góp gốc (`LICENSE-MODULARRSI.md`); mã dẫn xuất từ Harbor là Apache-2.0 (`LICENSE`) |
| HowieHwong/MemoHarness | `4c3da18` | **không có tệp LICENSE trong repo**, nên áp dụng bản quyền mặc định. Chúng tôi tái hiện thuật toán và không sao chép mã |
| stanford-iris-lab/meta-harness | `8123cca` | MIT (`LICENSE`) |

**HarnessDev:** chúng tôi không tìm thấy kho công khai nào, nên khảo sát này không bao gồm nó, và không có suy luận nào ở đây về nó.

Khi đường dẫn trong đặc tả TASK.md không tồn tại, điều đó được ghi chú (ví dụ ModularRSI không có `scripts/self_evolve.sh`; trình khởi chạy là `scripts/evolve.sh`).

---

## 1. ModularRSI (IQuestLab)

### (a) Seed / H0 và vị trí của nó
- Seed là **Terminus-2 được tách thành 5 module**. Mỗi module có một cài đặt `baseline`:
  `src/harbor/agents/terminus_2_modular/modules/{agent_loop,observation,context_mgmt,tools,verification}/baseline.py`
  (kích thước: agent_loop 906 dòng, context_mgmt 714, tools 425, observation 85, verification 48).
- Bundle mặc định gen-0 được mã cứng trong `composer/static.py::DEFAULT_BUNDLE`: mọi loại đều nhận `ModuleSpec(name="baseline")`.
- `archive.json` (`generations/merged_active/archive.json`) đánh dấu các mục seed là `change_type: "baseline"`, `born_gen: "gen_0"`. Ví dụ: niche của `agent_loop/baseline` là `{grounding: reactive, drift: none, parse: baseline}`.
- Thư viện đã tiến hóa được phát hành `generations/merged_active/gen_0/modules/` có 20 cài đặt đã đăng ký: 3 agent_loop, 2 observation, 2 context_mgmt, 5 tools, 2 verification, và 6 `tool_helper` (xem README và `PROVENANCE.json` của nó, trong đó ghi "code_behavior_changed: false" so với cây nguồn). Dù tên thư mục là `gen_0`, đây là thư viện *đã tiến hóa và được gộp*, không phải seed.
- Hành vi seed, từ docstring của các module:
  - hành vi baseline của agent_loop: "vòng lặp chính tương đương Terminus2 đầy đủ" với retry bằng tenacity và phương án dự phòng khi tràn ngữ cảnh.
  - baseline context_mgmt: tóm tắt QA 3 bước, ngưỡng chủ động 8000 token (`agent.py`).
  - baseline tools: một tool tmux duy nhất với ngữ pháp phím JSON.
  - baseline observation: chụp terminal gia tăng.
  - baseline verification: kết thúc sau khi thấy `task_complete` 2 lần liên tiếp.

### (b) Phân rã và giao diện chính xác (`terminus_2_modular/protocols.py`)
Mọi phương thức Protocol đều nhận một `ModuleCtx(state: RuntimeState (frozen), services: KernelServices, shared: SharedResources)`.
```python
class Observation(Protocol):
    async def capture(self, prev: ObsState, ctx) -> tuple[ObsResult, ObsState]
class ContextMgmt(Protocol):
    async def maybe_compress(self, chat: Chat, original_instruction: str, ctx) -> CompressResult
    async def force_summarize(self, chat, original_instruction, ctx) -> CompressResult
class ToolSet(Protocol):
    async def setup(ctx); async def teardown(ctx)
    def format_initial_prompt(instruction, terminal_state, ctx) -> str
    def format_continuation_prompt(terminal_state, ctx) -> str
    def parse_llm_response(response: str) -> LLMResponseParseResult   # commands, is_task_complete, analysis, plan, error
    async def execute(call: ToolCall, ctx) -> ToolResult
class VerificationLoop(Protocol):
    async def should_terminate(state: AgentLoopState, ctx) -> tuple[bool, str]
class AgentLoop(Protocol):
    async def run(initial_prompt, original_instruction, observation, context_mgmt, tools,
                  verification, chat, ctx) -> AgentLoopResult
class Composer(Protocol):
    async def choose(instruction, library: list[ModuleInfo], stats, ctx) -> ModuleBundle
```
- `ModuleBundle` có 5 trường `ModuleSpec(name, params)`.
- `ModuleInfo(name, type, description, params_schema, niche)`.
- Registry (`library.py`): mỗi tệp module định nghĩa `register(library)`, gọi `library.register(type_, name, factory(params)->obj, description, params_schema, niche)`. Việc phát hiện là tự động, từ `modules/<type>/*.py`, ở chế độ package hoặc chế độ đường dẫn (chế độ đường dẫn nạp cây của một thế hệ cho trước).
- `tool_helper` là loại thứ 6 được lưu trữ, với bậc **tập con**: mọi helper được đưa cho module `tools` qua `params={"helpers": [...]}`, và composer có thể loại một số helper.
- Shim kernel/agent (`agent.py`, `kernel/orchestration.py`) được đóng băng. Tiến hóa chỉ được thay đổi cài đặt module, và `protocols.py` là "không bao giờ" được editor sửa.

### (c) Cách seed được chọn lúc chạy
- `composer_name="static"` dùng `StaticComposer`: nó trả về `DEFAULT_BUNDLE` (tất cả baseline) trừ khi `<modules_root>/active_bundle.json` ghi đè các loại (được kiểm tra, rơi về mặc định theo kiểu toàn bộ-hoặc-không có; `composer/bundle_config.py`). README của merged_active nói `static` "cố ý trả về bundle baseline".
- `composer_name="llm_dynamic"` (mặc định của solver) dùng `LLMComposer` (`composer/llm_dynamic.py`). Nó thực hiện **một lệnh gọi LLM cho mỗi tác vụ**:
  - Prompt: "chọn MỘT cài đặt có mô tả khớp nhất với TÁC VỤ NÀY … khi nghi ngờ, ưu tiên default … Không có tín hiệu phần thưởng". Nó hiển thị danh mục `name: DESCRIPTION` cho mỗi loại có nhiều cài đặt, cùng `exclude_helpers` tùy chọn.
  - Nó phân tích JSON từ văn bản tự do và rơi về default khi có bất kỳ lỗi nào.
  - Nó lọc các biến thể được đánh dấu `superseded`/`excluded` trong `archive.json`, giữ một đại diện cho mỗi ô niche (`niche.py`), và cách ly `_NON_SOLVER_IMPLS` (`editor_file_tools`, `passthrough`, `combined_robust`).
  - Các loại được ghim trong `active_bundle.json` không được đưa cho bộ chọn.

### (d) Cách tiến hóa chỉnh sửa nó (`self_evo/`, entry `phase0.py` → `online_evo.run_online_evo`)
- **Một loại module bị khóa mỗi lần chạy** (`--locked-module`). Các tool tệp của editor từ chối ghi ra ngoài `modules/<locked>/`.
- **K-roll** (`k_roll.py`): mỗi tác vụ chạy K=3 lần với *cùng bundle đóng băng* (lựa chọn composer của roll đầu tiên được ghim qua một snapshot riêng), nên kết quả chỉ khác nhau do lấy mẫu.
- **Bucket định tuyến** (`router.py`): `ALL_PASS_EFFICIENT`, `ALL_PASS_WASTEFUL`, `MIXED`, `FIXABLE_FAIL`, `STUCK_FAIL`.
  - Các bucket để chẩn đoán là MIXED và FIXABLE_FAIL (đối chiếu đạt-với-trượt; một lần đạt có thể đến từ lịch sử lưu trữ).
  - ALL_PASS_WASTEFUL nhận một investigator về hiệu quả.
  - STUCK_FAIL bị đưa vào thời gian hồi (cooldown).
  - Đây là cách nhóm "dương / đối chiếu / âm".
- **Điều tra đối chiếu** (`trajectory_analysis.py::build_contrast_investigation_instruction`, `_MODULE_LENS`):
  - Nó mang tính phản thực tế: "THAY ĐỔI module này có chuyển tác vụ fail→pass không?"
  - Mỗi loại module có lăng kính riêng: covers / yardstick / probes.
  - Đầu ra là một phát hiện JSON với `is_culprit`.
- Các phát hiện được **gom cụm thành đề xuất** (`clustering.py`, `evidence_pass.py`). Một **danh mục** (portfolio) chọn ≤1 đề xuất cho mỗi làn (incumbent / novelty) (`portfolio.py`).
- **Cài đặt kép** (`dual_implement.py`) chạy hai implementer độc lập không biết nhau trong các cây staging riêng. Editor của họ (giống Claude Code) thêm một **tệp biến thể mới** (thư viện chỉ cộng thêm) với DESCRIPTION và niche.
- **Cổng kiểm tra**:
  - `smoke_tests.py`: kiểm tra AST bảo vệ kernel, kiểm tra import, nạp thư viện (đủ 5 loại).
  - **Review diff mù phần thưởng** (`build_review_instruction`, `_REVIEW_PREAMBLE`): đánh giá cơ chế và quá khớp, và không thể thấy đạt/trượt.
  - Thăm dò kích hoạt/định tuyến (`routing_probe.py`): composer phải thực sự chọn biến thể mới.
  - Bộ kiểm tra crash.
- **Thăng hạng / rebase** (`promotion.py`, `rebase.py`): nếu cả hai làn đều qua, làn thứ hai được rebase lên làn đầu, và chỉ các cổng phụ thuộc cây được chạy lại.
- **Xác nhận/hoàn tác xuyên kỷ nguyên** (`confirm.py`): so sánh ghép cặp theo tác vụ với biến thể baseline. Một biến thể rõ ràng kém hơn sẽ trở thành `superseded`.
- Các dòng dõi tuần tự ghim các chiến thắng trước đó qua `active_bundle.json`. `composer_scope=all` cho phép chọn các biến thể được kế thừa.

### (e) Cách khởi chạy một lần chạy
- `bash scripts/evolve.sh` (tiến hóa): nó gọi `python -m harbor.agents.terminus_2_modular.self_evo.phase0 --locked-module ... --support-dataset-dir ...` với `PROFILE=train|smoke`. Smoke nghĩa là reflect_every=2, concurrency=2, epochs=1, max_tasks=2. Train nghĩa là 10/6/3/all.
- `bash scripts/evaluate.sh` (đánh giá đóng băng): nó gọi `python -m harbor.cli.main run -d terminal-bench@2.0 -a terminus-2-modular --ak modules_root=... --ak composer_name=llm_dynamic|static`.

### (f) Phụ thuộc cứng
- Harbor (vendored trong `src/harbor`).
- `ENVIRONMENT` phải là `docker` hoặc `e2b`. Tác vụ chạy trong container với một phiên tmux (`SUPPORTS_WINDOWS=False`).
- LiteLLM.
- Dataset `IQuestLab/ModularRSI_2000_Instances` (tác vụ Terminal/SWE).
- `pyproject` kéo theo `claude-agent-sdk`, `supabase`, `litellm`, v.v.
- Editor là một agent LLM có tool tệp.
- Không cần GPU, và không yêu cầu model cụ thể nào (bài báo dùng DeepSeek-V4-Flash-Preview).

### (g) Tái sử dụng hay chuyển thể
- **Tái sử dụng nguyên trạng được (ý tưởng và đoạn mã nhỏ, nghiên cứu, CC BY-NC):**
  - *hình dạng* của Protocol
  - mẫu registry (`register(library)` + `ModuleInfo` với description/niche)
  - ngữ nghĩa ghim của `StaticComposer` + `active_bundle.json`
  - prompt của LLMComposer và các quy tắc dự phòng của nó
  - định nghĩa các bucket định tuyến
  - các lăng kính của module
  - các quy tắc của cổng review (mù phần thưởng, chống quá khớp)
  - các tầng của cổng smoke
- **Bắt buộc phải chuyển thể:** mọi thứ chạm đến Harbor, tmux, Docker, hoặc `Chat`. Điều đó gồm Observation đặc thù terminal (benchmark của chúng tôi là môi trường văn bản/API, không phải terminal), ngữ pháp phím JSON kiểu Terminus, agent editor kiểu Claude Code, và bộ chạy tác vụ e2b/docker. Kernel bất đồng bộ của Harbor được thay bằng vòng lặp adapter đồng bộ của chúng tôi.

---

## 2. MemoHarness (HowieHwong)

### (a) Seed / H0 và vị trí của nó
- `configs/experiment.json` → `experiment.harness_path = "configs/harness_terminal.py"`. Đây là một **`HarnessImpl` Python được tiến hóa thủ công dài 6351 dòng** với một bản tóm tắt đi kèm `configs/harness_terminal.json` (các chiến lược D1–D6). Nó *không* phải seed tối giản.
- Trong config đi kèm, runtime của agent là `harness.agent_runtime="harbor_codex"` và seed là **bundle Codex** `configs/harness_codex/` (`policy.json` với D1–D6, `AGENTS.override.md`, `.memoharness/{playbook,memory}.md`). Nó chạy bên trong agent CLI Codex chính thức của Harbor (`agent_import_path: memoharness.harbor.codex_agent:MemoHarnessCodexAgent`).
- Nếu không có tệp harness, `HarborTrainingLoop._setup` (`harbor/loop.py`) yêu cầu bộ điều khiển `generate_initial_harness`. Khi thất bại, nó rơi về `core/models.py::make_minimal_config()`:
  - D1 không có ví dụ / không nén
  - D2 tắt tool
  - D3 temp 0, max_tokens 256
  - D4 single_call
  - D5 memory tắt
  - D6 passthrough thô
  - `LLMController.stabilize_config` sau đó ép một vòng bash theo kiểu agent với cửa sổ trượt 12 lượt.
- Vì vậy seed hiệu lực là "một mẫu ổn định được render từ một cấu hình D1–D6" (`LLMController._render_harness_code`), trừ khi có một tệp harness phong phú hơn được cung cấp.

### (b) Phân rã: sáu chiều (`core/models.py::HarnessConfig`)
- `HarnessConfig(D1..D6: dict[str, Any])`, với `clone`, `update_dimension`, `delta_from`. Các chiều là:
  - D1 lắp ráp ngữ cảnh
  - D2 tương tác tool
  - D3 kiểm soát sinh
  - D4 điều phối
  - D5 quản lý bộ nhớ (`MemoryPolicy`: disabled | sliding_window | summary_buffer | importance_based)
  - D6 xử lý / kiểm tra đầu ra
- Harness *thực thi được* là một lớp Python có hợp đồng cố định (`controllers/llm_controller.py::_HARNESS_INTERFACE_DOC`):
  `class HarnessImpl: async def setup(self, environment); async def run(self, instruction, environment, context)`.
  Dict D1–D6 là một *bản tóm tắt/cấu hình* gắn với mã đó, nên các chiều là trục mô tả, không phải module mã riêng biệt.
- Ngân hàng kinh nghiệm (`bank/experience.py`) là `B=(E,G)`:
  - `PerCaseEntry(case_id, iteration, case_features, config, delta_from_prev, trajectory, primary_reward, cost_actual, diagnosis(primary_dim))`
  - `GlobalPattern(description, evidence[case_ids], effect, primary_dim)`
  - `CaseStats` (số lần thất bại liên tiếp, xu hướng phần thưởng, số lần thất bại theo chiều)

### (c) Cách seed được chọn lúc chạy
- Huấn luyện: vòng lặp nạp tệp harness .py/.json (hoặc bundle codex), với config `stabilize_config(...)`.
- Sau huấn luyện, `_select_best_harness` chọn vòng lặp tốt nhất theo `best_harness_selection_modes` (mặc định `mean_reward`; ưu tiên đúng đắn, token làm luật phá hòa theo README) và khôi phục harness đã lưu trữ đó.
- Kiểm thử: `_run_test_evaluation_with_case_adaptation` làm như sau cho mỗi tác vụ kiểm thử:
  1. `_adapt_eval_config_for_case` xây dựng `CaseFeatures` từ văn bản tác vụ.
  2. Nó gọi `controller.adapt_for_case(bank, case, base_config)`, hàm này truy hồi các ca thành công tương tự (top 5) và thất bại (top 3) rồi yêu cầu LLM "Chỉ điều chỉnh các chiều khi bằng chứng ca tương tự biện minh", trả về các cập nhật cấu hình.
  3. Nó áp dụng cấu hình đã điều chỉnh, chạy đúng ca đó, và khôi phục harness gốc.
- Ngân hàng không được cập nhật trong lúc kiểm thử (điều chỉnh là "một lần", không có nhãn kiểm thử hay phản hồi).

### (d) Cách tiến hóa chỉnh sửa nó
- Mỗi vòng lặp chạy mọi tác vụ train, rồi:
  1. `_update_bank` thêm các `PerCaseEntry`. Heuristic đổ lỗi D4 cho các thất bại (xem `_make_entry`), và LLM chẩn đoán/chưng cất sau đó.
  2. Cứ mỗi `distill_every=5` mục, hoặc khi một ca đạt `min_consecutive_failures=3`, `LLMDistiller` yêu cầu ≤3 `GlobalPattern` dạng JSON trải ≥2 ca, mỗi mẫu gắn với một chiều-D (`llm/distiller.py`).
  3. `_update_config` yêu cầu bộ điều khiển viết lại harness. `LLMController.decide_next_harness` đưa tóm tắt ngân hàng, tín hiệu kết quả thay đổi, và mã hiện tại (≤200 dòng), với chỉ dẫn "chọn 1-3 can thiệp ưu tiên cao nhất … Giữ lớp tên HarnessImpl". Đầu ra được kiểm tra cấu trúc, và mã hiện tại được giữ khi thất bại.
  4. Một **cổng canary** (`_evaluate_candidate_with_canary`: 6 tác vụ canary cố định, delta phần thưởng tối thiểu −0.34, không tăng số blocker) bảo vệ khỏi hồi quy.
- Cấu hình được phát hành chỉ dùng `controller="codex"`. Mã ghi: "chuỗi experiment.json chỉ hỗ trợ harness.controller='codex'" (`CodexBundleController`, chỉnh các tệp bundle bằng Codex CLI).

### (e) Cách khởi chạy một lần chạy
`memoharness --config configs/experiment.json` hoặc `python -m memoharness.harbor.loop --config ... [--eval-only]`.

### (f) Phụ thuộc cứng
- Harbor + sandbox **Daytona** (`extra_harbor_args: ["--env","daytona"]`, key pool, `daytona_scheduler.py`).
- **Codex CLI** vừa là runtime agent vừa là bộ điều khiển.
- **Embedding** của OpenAI (`text-embedding-3-small`) cho độ tương đồng. `ExperienceBank` ném lỗi nếu không có embedder.
- Judge `gpt-4.1-mini` cho scorer `llm_judge`.
- Terminal-Bench. Không cần GPU.

### (g) Tái sử dụng hay chuyển thể
- **Không thể sao chép mã** (không có giấy phép).
- **Thuật toán có thể tái hiện:**
  - ngân hàng hai lớp (mục + mẫu + thống kê ca)
  - các điều kiện kích hoạt chưng cất (mỗi N mục / K lần thất bại liên tiếp)
  - *cấu trúc* prompt chưng cất (≤3 mẫu, ≥2 ca, mỗi mẫu một chiều)
  - chọn vòng lặp tốt nhất theo ưu tiên đúng đắn
  - điều chỉnh theo từng ca từ top-k các thành công/thất bại tương tự với ngân hàng đóng băng
  - cổng canary
- **Chuyển thể:**
  - thay embedding bằng **BM25** trên chỉ dẫn tác vụ (TASK.md cấm các embedding cục bộ không phải Qwen; thử BM25 trước)
  - ánh xạ D1–D6 lên 5 slot của chúng tôi cùng các tham số sinh. Các chỉnh sửa theo chiều D của chúng tôi trở thành chỉnh sửa biến thể slot/cấu hình.
  - thay bộ điều khiển Codex CLI bằng một lệnh gọi LLM OpenRouter trả về một đề xuất cấu hình/mã
  - thay Daytona bằng các adapter trong tiến trình

---

## 3. Meta-Harness (stanford-iris-lab)

### (a) Seed / H0 và vị trí của nó
- Track TB2: `reference_examples/terminal_bench_2/agents/baseline_kira.py::AgentHarness`, tức **KIRA**: một lớp con gọi tool gốc của `Terminus2` của Harbor.
  - `TOOLS` = `execute_commands(analysis, plan, commands[{keystrokes,duration}])`, `task_complete()`, `image_read(file_path, instruction)`.
  - Prompt `prompt-templates/terminus-kira.txt` (`{instruction}`, `{terminal_state}`; "kiểm tra các thay đổi trạng thái tối thiểu" trước `task_complete`).
  - Giới hạn đầu ra 30 KB.
  - Baseline thứ hai: `agents/baseline_terminus2.py` (`AgentHarness = Terminus2`).
- Track phân loại văn bản: các seed `agents/{no_memory,fewshot_all,fewshot_memory}.py` cài đặt `memory_system.py::MemorySystem` (`predict(input)->(answer, meta)`, `learn_from_batch(results)`, `get_state()/set_state()`).
- `experimental/harbor_meta_harness`: một seed `/app/harness.py` "chỉ dùng một lượt terminal" và được chấm điểm bởi một bộ điều khiển đáng tin qua một bộ kiểm thử.

### (b) Phân rã
- **Không có chủ đích.** "Không gian tìm kiếm là mã Python tùy ý" (`.claude/skills/meta-harness-terminal-bench-2/SKILL.md`).
- Hợp đồng duy nhất là "lớp tên `AgentHarness`, kế thừa `Terminus2`, nạp qua `agents.<name>:AgentHarness`".
- Skill liệt kê các điểm can thiệp dưới dạng *gợi ý*: `_call_llm_with_tools`, `_parse_tool_calls`, `_execute_commands`, `_run_agent_loop`, `_get_completion_confirmation_message`, `_get_prompt_template_path`, `_summarize_context`, `_execute_image_read`.

### (c) Cách seed được chọn lúc chạy
- `meta_harness.py::BASELINES = [("kira-baseline", "agents.baseline_kira:AgentHarness"), ("terminus2-baseline", ...)]`.
- Các baseline được đánh giá trước, và `frontier_val.json` được khởi tạo từ chúng.
- `render_task_prompt` nói với proposer "Bắt đầu từ agents/baseline_kira.py làm cha".

### (d) Cách tiến hóa chỉnh sửa nó
- Mỗi vòng lặp, `propose_claude` chạy **Claude Code** (`claude_wrapper.run`, model opus, effort max) với các tool Read/Glob/Grep/Agent/Write/Edit/Bash và skill làm prior cho proposer.
- Proposer có quyền truy cập hệ thống tệp tới `logs/evolution_summary.jsonl` (tỷ lệ đạt trung bình/theo tác vụ của từng ứng viên, giả thuyết, thay đổi, delta, rollout_metrics), `logs/frontier_val.json` (agent tốt nhất theo tác vụ + `_best`), `jobs/` (quỹ đạo Harbor đầy đủ), và mọi `agents/*.py`.
- Nó phải viết **một** tệp ứng viên mới `agents/<name>.py` với đúng một cơ chế, theo các quy tắc chống quá khớp: không có tên tác vụ, chỉ hướng dẫn tổng quát.
- Sau đó nó viết `logs/pending_eval.json` (`name`, `import_path`, `hypothesis`, `changes`, `expected_efficiency`).
- Vòng lặp ngoài:
  1. `validate_candidate` (kiểm tra import).
  2. `smoke_test` (1 lần thử trên `extract-elf`, 0 lỗi).
  3. `harbor_run` (89 tác vụ × 2 lần thử).
  4. `update_frontier` + `update_evolution_summary`.
  5. Một lần đánh giá 5 lần thử tùy chọn cho frontier.
- Mọi phiên Claude được `claude_wrapper` ghi log (stream-json → `logs/claude_sessions/`).

### (e) Cách khởi chạy một lần chạy
`uv run python meta_harness.py --iterations N [--trials 2] [--fresh] [--full-eval]`. Đánh giá một agent: `uv run bash scripts/run_eval.sh agents.baseline_kira:AgentHarness full 1 1 -i extract-elf`.

### (f) Phụ thuộc cứng
- **Claude Code CLI** làm proposer.
- Sandbox Harbor + **Runloop hoặc Modal** (`RUNLOOP_API_KEY` / token Modal).
- API Anthropic (Opus 4.6; "khoảng $500 mỗi vòng lặp").
- `anthropic_caching.py`. Không cần GPU.

### (g) Tái sử dụng hay chuyển thể
- **Tái sử dụng được (MIT):**
  - quy trình của proposer và văn bản skill (quy tắc chống quá khớp, một cơ chế cho mỗi ứng viên, định dạng STATE/HYPOTHESIS/CANDIDATE)
  - bố cục artifact trên đĩa (`evolution_summary.jsonl`, `frontier_val.json`, `pending_eval.json`, tệp ứng viên, vết)
  - vòng lặp kiểm tra → smoke → đánh giá → frontier
- **Chuyển thể:**
  - proposer Claude Code → model OpenRouter của chúng tôi, nhận một *bundle tệp đã render* (nó không thể chạy tool, nên chúng tôi đưa cho nó danh sách thư mục và các tệp/quỹ đạo được chọn, và nó trả về một tệp harness mới hoàn chỉnh).
  - Harbor/Runloop → các adapter trong tiến trình của chúng tôi.
  - hợp đồng lớp con Terminus2 → hợp đồng `Harness` của chúng tôi.

---

## 4. So sánh giữa các repo

| | ModularRSI | MemoHarness | Meta-Harness |
|---|---|---|---|
| Seed | Terminus-2 tách thành 5 module `baseline` | mẫu từ cấu hình D1–D6 tối giản (hoặc harness phong phú/bundle codex được cung cấp) | KIRA (Terminus2 + tool gốc) |
| Đơn vị chỉnh sửa | tệp biến thể mới trong một loại module bị khóa | viết lại toàn bộ `HarnessImpl` + cấu hình D1–D6; delta cấu hình theo ca lúc kiểm thử | toàn bộ tệp agent (tự do) |
| Chuyên biệt hóa theo tác vụ | LLMComposer chọn 1 biến thể/loại + tập con helper | `adapt_for_case` từ các ca tương tự được truy hồi | không có (một harness toàn cục) |
| Tín hiệu chọn lựa | bucket đối chiếu K-roll, cổng, xác nhận/hoàn tác ghép cặp | phần thưởng trung bình mỗi vòng (+ canary) | tỷ lệ đạt trung bình của frontier |
| Proposer | agent editor LLM có tool tệp | Codex CLI | Claude Code |
| Sandbox | Docker / e2b | Daytona | Runloop / Modal |

## 5. Khuyến nghị: H0 CỦA CHÚNG TÔI

H0 phải là một seed duy nhất mà cả ba baseline đều có thể bắt đầu từ đó. Nó phải phân rã được (B2 và HarnessGraph cần), chỉnh sửa được toàn bộ tệp (B1 cần), và cấu hình được theo các trục giống D (B3 cần).

1. **Năm slot với Protocol rõ ràng**, mô phỏng theo ModularRSI nhưng đặt tên theo các slot của TASK.md: `agent_loop`, `context_mgmt`, `tool_policy`, `memory`, `verifier`.
   - `observation` của ModularRSI gộp vào `tool_policy`, nơi sở hữu việc định dạng quan sát và cắt cụt cho mỗi kết quả tool.
   - `memory` là mới: nó xuyên episode, và không có tác dụng trong H0. D5 của MemoHarness được chia giữa `context_mgmt` (trong một episode) và `memory` (xuyên episode).
2. **Lõi không phụ thuộc benchmark, adapter mỏng.** Một adapter lộ ra một `Env`:
   - `reset(task_id) -> TaskSpec(instruction, initial_obs, tools: list[ToolSpec])`
   - `step(tool_name, args) -> StepResult(observation, done, info)`
   - `evaluate() -> (success, info)`
   - Schema tool là đặc tả hàm OpenAI gốc, do adapter sở hữu.
3. **Python đồng bộ, một client LLM duy nhất (`llm.py`), gọi tool gốc.** H0 = ReAct với tool:
   - một tool call mỗi bước
   - `finish(answer)` là tool hoàn thành
   - ngữ cảnh cửa sổ trượt
   - verifier = chấp nhận `finish` đầu tiên (hoặc `done` của env)
   - Các prompt seed theo sát các agent tham chiếu cho từng benchmark. *Chỉ dẫn* riêng của benchmark đến từ adapter, không phải từ harness.
4. **Registry giống ModularRSI:** `register(slot, name, factory, description, config_schema, niche)`. Các biến thể là tệp nằm dưới `h0/variants/<slot>/`.
   - `compose(task) -> Harness` là hook xác định. H0 = `DEFAULT_BUNDLE` (tất cả `default`), tương đương `StaticComposer` của ModularRSI.
   - Tồn tại một cơ chế ghi đè kiểu `active_bundle.json` cho các ứng viên đã tiến hóa.
   - composer có nhận biết tác vụ của B2 và composer của HarnessGraph cắm vào hook này.
5. **Góc nhìn toàn bộ harness dạng tệp cho B1:** một ứng viên là snapshot thư mục của `h0/variants/**` + `bundle.json`. B1 chỉnh sửa bất kỳ tệp nào; B2 thêm tệp biến thể theo slot; B3 chỉnh một bề mặt cấu hình kiểu D1–D6 ánh xạ lên cấu hình slot. Mọi ứng viên được đánh giá bởi cùng một bộ chạy, nên H0 giống hệt nhau giữa các baseline.

Giao diện đề xuất (đã cài đặt trong Giai đoạn 3, `h0/protocols.py`):
```python
class AgentLoop(Protocol):
    def run(self, task: TaskSpec, env: Env, h: "Harness", llm: LLM, rec: Recorder) -> LoopOutcome
class ContextMgmt(Protocol):
    def build(self, system: str, task: TaskSpec, history: list[dict], memory_notes: str) -> list[dict]
class ToolPolicy(Protocol):
    def tools(self, task: TaskSpec) -> list[dict]                 # schema được cung cấp cho LLM
    def parse(self, resp: LLMResponse) -> list[Action]            # tool call gốc (+ dự phòng văn bản)
    def format_observation(self, action: Action, result: StepResult) -> str
class Memory(Protocol):
    def recall(self, task: TaskSpec) -> str                       # ghi chú được chèn vào ngữ cảnh
    def update(self, task: TaskSpec, outcome: LoopOutcome) -> None  # chỉ lúc huấn luyện; đóng băng lúc kiểm thử
class Verifier(Protocol):
    def check(self, task: TaskSpec, action: Action, state: LoopState) -> Verdict  # accept | reject(feedback)
@dataclass
class Harness:            # bundle đã lắp ráp
    agent_loop: AgentLoop; context_mgmt: ContextMgmt; tool_policy: ToolPolicy
    memory: Memory; verifier: Verifier; bundle: dict[str, VariantSpec]; system_prompt: str
def compose(task: TaskSpec, bundle: dict | None = None) -> Harness   # H0: DEFAULT_BUNDLE
```
