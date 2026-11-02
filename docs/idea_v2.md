# Harness repertoire: ý tưởng bản 2

Bản này sửa lại ý tưởng "repertoire các component, ghép theo task" dựa trên các failure quan sát được khi chạy B1 (Meta-Harness), B2 (ModularRSI) và B3 (MemoHarness) với ba model: ling, luna và ag/gemini-3.8-flash. Các số liệu dẫn ra lấy từ `docs/medium_results.md` và `docs/luna_results.md`, cùng lần chạy ag.

**Nguyên tắc chung:** mọi cải tiến, của ý tưởng lẫn của harness được sinh ra, phải mang tính khái quát. Không hardcode ID tác vụ, tên test, chuỗi đáp án, tên file hay đường dẫn của benchmark. Nguyên tắc này được cưỡng chế bằng máy ở bước Generalization gate (mục 3.1), không chỉ là lời dặn.

---

## 1. Bài học từ các baseline

Mỗi dòng dưới đây là một failure đã thấy và yêu cầu thiết kế rút ra từ nó.

| # | Failure quan sát được | Ở đâu | Yêu cầu thiết kế |
|---|---|---|---|
| F1 | **Thắng nhờ nhiễu.** Ứng viên thắng val 30 task (1 roll) nhưng không hơn trên test. B3 chọn bản train 83% thì test 65%. B1 AppWorld r5 rơi xuống 60% mà không rõ nguyên nhân. | B1, B3, cả 3 model | Đánh giá **ghép cặp** (cùng task, cùng seed, base và candidate), nhiều roll, kiểm định tuần tự. Chỉ thăng hạng khi cận dưới của khoảng tin cậy > 0. |
| F2 | **Mã chết hoặc crash.** Thay đổi BCP r2 của B1 không bao giờ chạy. Có crash ở bước smoke, mỗi lần mất một vòng. | B1, B2 | **Hợp đồng candidate:** biên dịch được, smoke test, và **telemetry kích hoạt** (hook log mỗi lần fire). Candidate không fire thì không nhận credit. |
| F3 | **Biến thể có hại vẫn vào thư viện.** `goal_satisfied` chỉ qua cổng chứ không phải qua reward, được chọn cho 54 task và kém H0 6 task. | B2 ling | Thăng hạng dựa trên reward. Lưu **bằng chứng âm** và có cơ chế loại bỏ. |
| F4 | **Composer chọn theo mô tả,** không theo kết quả. Có biến thể không bao giờ được chọn, có biến thể có hại lại được chọn nhiều. | B2 | Router học từ **outcome đã quan sát**. Điều kiện áp dụng phải **chạy được** (predicate trên trạng thái), không phải văn bản để LLM đoán. |
| F5 | **Bước chẩn đoán phụ thuộc mức "dễ dãi" của model.** Ling đề xuất nhiều và gây hại. Luna đứng yên 15/15 vòng vì đòi một "thủ phạm duy nhất" có bằng chứng phản thực. | B2 | Không bắt chẩn đoán phải chỉ ra một thủ phạm duy nhất. Dùng nhiều nguồn tín hiệu (mục 3.2) và **hiệu chỉnh** chẩn đoán theo kết quả thật. |
| F6 | **Chi phí bùng nổ.** B3 tốn 1,6–2,2 lần token so với H0. `adapt_for_case` gọi LLM ở mỗi ca, và 3–10 ca mỗi benchmark trả JSON hỏng. | B3 | Đưa chi phí vào hàm mục tiêu. **Kích hoạt lười** (chỉ chèn khi trigger fire). Không viết lại prompt bằng LLM ở mỗi ca. |
| F7 | **Ghi đè cùng tên.** Biến thể r5 đè lên biến thể r4. | B2 (lỗi mã) | Candidate **bất biến, có version**, có quan hệ `derived_from`. |
| F8 | **Model mạnh nâng mặt bằng nhiều hơn mọi baseline.** H0 AppWorld 6% với ling, 75% với luna, 87% với ag. Thứ hạng các baseline **đảo chiều theo model**. | cả 3 | Harness phải được chọn **có điều kiện theo hành vi model** (mục 4). Giá trị chính nằm ở các *niche* failure còn lại, không ở trung bình. |
| F9 | **Truy hồi theo văn bản task yếu.** BM25 trên chỉ dẫn mang tính khuôn mẫu chỉ trả về cùng loại task. | B3 | Đặc trưng để chọn component nên lấy từ **hành vi trong trajectory** (lặp lại, bỏ cuộc, lỗi tool), không chỉ từ văn bản đề bài. |
| F10 | **Các thay đổi thắng đều nhỏ và tổng quát.** Ví dụ: "từ chối đáp án bỏ cuộc khi còn bước", "gọi admissible_commands sau nhiều lần Nothing happens", "kiểm tra hậu điều kiện trước complete_task". | B1, B3 | Đây là đơn vị nên lưu: **mechanism** gồm điều kiện → hành động. Bằng chứng ủng hộ việc giữ tầng Mechanism. |
| F11 | **Lỗi tầng giao tiếp model.** Tool call dạng văn bản GLM không được parse. Reasoning ẩn ăn hết ngân sách nên câu trả lời rỗng hoặc bị cắt. Cooldown 503 không được nhận ra. | hạ tầng, cả 3 model | Thêm slot **model adapter** (mục 2). Đây là phần phụ thuộc model rõ nhất. |

---

## 2. Taxonomy component: các slot nên có

Năm slot hiện tại của H0 (`agent_loop`, `context_mgmt`, `tool_policy`, `memory`, `verifier`) được gộp với sáu nhóm trong ảnh, rồi bổ sung thêm những gì các failure ở trên cho thấy còn thiếu. Mỗi slot có một **hook point** cố định trong vòng lặp, để telemetry biết slot nào đã fire.

| Slot | Thuộc nhóm (ảnh) | Hook | Ví dụ mechanism | Vì sao cần |
|---|---|---|---|---|
| **S1 Context assembly** | Context assembly | trước mỗi lời gọi model | ghép chỉ dẫn, ví dụ, tài liệu truy xuất; nén lịch sử | có sẵn (`context_mgmt`) |
| **S2 Action interface** | Tool interaction | lúc khai báo tool | mô tả tool, schema đối số, alias, tool phụ trợ (ví dụ `admissible_commands`) | ALFWorld: lợi lớn nhất đến từ việc làm cho agent *dùng* tool có sẵn |
| **S3 Tool policy** | Tool interaction | trước mỗi lần thực thi tool | khi nào search, lấy bao nhiêu kết quả, khi nào đọc toàn văn | BCP: luna search 4 lần, ling 20 lần |
| **S4 Observation processing** | *(thêm mới)* | sau mỗi lần tool trả kết quả | cắt hoặc tóm tắt output, chuẩn hoá lỗi, làm nổi bật mã lỗi (401/422) | AppWorld `auth_recovery`. Khác với output processing ở bước cuối. |
| **S5 Error recovery** | *(thêm mới, thuộc Orchestration)* | khi phát hiện lỗi hoặc vòng lặp | replan khi lỗi lặp lại, phá vòng lặp, thử cách khác | `repetition_breaker`, "Nothing happens" |
| **S6 Orchestration** | Orchestration | cấu trúc vòng lặp | plan → act → verify; tách sub-agent; todo list | `todo_plan` trên BCP |
| **S7 Budget & termination** | *(thêm mới)* | mỗi bước, và khi agent muốn dừng | biết ngân sách bước, **từ chối bỏ cuộc sớm**, dừng khi lặp vô ích | thay đổi thắng của B1 trên luna BCP; `budget_aware` của B2 trên ag AppWorld |
| **S8 Verification** | Output processing | trước khi nộp hoặc trả lời | kiểm tra hậu điều kiện, kiểm tra định dạng, tự kiểm chứng | có sẵn (`verifier`) |
| **S9 Memory** | Memory management | giữa các bước và giữa các task | nhớ chỗ đã tìm, ghi chú tiến độ, kinh nghiệm chéo task | có sẵn |
| **S10 Generation control** | Generation control | tham số decode | temperature, `max_tokens`, reasoning on/off/low | F11: reasoning ẩn ăn hết ngân sách |
| **S11 Model adapter** | *(thêm mới)* | quanh lời gọi model | parse tool call theo dialect, fallback khi bị cắt, retry | F11; phụ thuộc model nhiều nhất |

Ba điểm gộp và bỏ:

- **"Output processing" tách đôi:** phần xử lý output của tool thành S4, phần trả lời cuối thành S8. Hai việc này có hook và failure khác nhau.
- **Skills** không là slot riêng. Một skill là *nội dung* cắm vào S1 (khi dạng hướng dẫn) hoặc S2 (khi dạng tool). Tránh trùng lặp.
- **Sub-agent** là một mechanism của S6, không là slot riêng.

Quy tắc đặt vị trí (placement rule, theo ảnh 1), cưỡng chế ở gate:

- thay đổi **năng lực** → S2, tool mới;
- thay đổi **cưỡng chế** ("không được X") → middleware ở S3/S5/S7/S8, chạy bằng mã;
- **phân rã việc** → S6;
- **hướng dẫn hành vi** → S1 hoặc S9, ở prompt hoặc memory.

Bằng chứng: "từ chối bỏ cuộc" chạy được vì là middleware cưỡng chế. Nếu chỉ là một câu trong prompt thì model mạnh dễ bỏ qua (F8).

---

## 3. Các thành phần kỹ thuật, bản đã sửa

### 3.1 Generalization gate (constrained evolution)

Mọi candidate phải qua gate trước khi được chạy. Gate có ba tầng, rẻ trước, đắt sau:

1. **Lint tĩnh, không tốn LLM.** Từ chối candidate có:
   - chuỗi trùng với ID task, tên test hay đường dẫn trong tập train/val;
   - n-gram dài (≥ 6 từ) trùng với văn bản đề bài hay đáp án train;
   - literal so khớp entity cụ thể (tên người, sản phẩm) không xuất hiện trong mô tả tool chung.
2. **Dạng nguyên tắc.** Candidate phải khai báo `precondition` (điều kiện quan sát được trên trạng thái), `action` và `rationale`. `precondition` phải là **predicate chạy được** trên trajectory, ví dụ "≥ 3 lần tool trả lỗi giống nhau" hoặc "agent định trả lời trong khi còn > 30% bước". Không chấp nhận "nếu task là về Spotify".
3. **Kiểm tra chéo cụm (leave-cluster-out).** Đánh giá trên cả các cụm task *không* sinh ra failure gốc. Candidate tổng quát thì không được gây hại ở đó (kiểm tra không-hại).

Thêm một cờ: candidate chỉ giúp đúng các task đã sinh ra nó, và không giúp task nào khác cùng `precondition`, sẽ bị đánh dấu nghi overfit.

### 3.2 Proactive feedback: blind và hindsight report

Sau mỗi episode trong vòng tiến hoá (không làm lúc test), gọi thêm một lần rẻ:

- **Blind report**, *trước* khi agent biết kết quả. Agent tự đánh giá:
  - có chắc chắn hay không;
  - chỗ khó nằm ở đâu;
  - harness cản trở ở điểm nào, với các nhãn: thiếu tool, output tool khó đọc, chỉ dẫn mâu thuẫn, hết bước.

  Report này không có hindsight bias. Nó còn là **tín hiệu hành vi**: độ tự tin so với kết quả thật cho biết model có calibrated hay không, xem mục 4.
- **Hindsight report**, *sau* khi biết là sai. Agent phân loại nguyên nhân: harness, suy luận, đề mơ hồ hay môi trường.

Cách dùng:

- Report chỉ là **đặc trưng, không phải phán quyết**. Mỗi nhãn nguyên nhân được hiệu chỉnh theo việc sửa harness tương ứng có thật sự cải thiện hay không. Đây là cách giải F5: không phụ thuộc một investigator khắt khe hay dễ dãi.
- Failure mà hindsight gán cho "suy luận" hay "đề mơ hồ" **không được dùng để sinh candidate harness**. Như vậy tránh được việc vá những thứ harness không chữa được, ví dụ AppWorld với ling.

### 3.3 Component-wise optimization và R³ merge

Mỗi vòng, từ một harness cha và một failure mode đã chọn, sinh **hai nhánh song song**:

- **Nhánh structural** sửa S2–S8 ở tầng mã: tool, middleware, sub-agent.
- **Nhánh guidance** sửa S1/S9 ở tầng văn bản: prompt, skill, mô tả tool, memory.

Hai nhánh được đánh giá ghép cặp với cha trên cùng tập task. Bước merge (R³) gồm:

1. giữ các thay đổi có Δ dương với khoảng tin cậy đủ;
2. ghép các thay đổi được giữ;
3. đánh giá lại **chỉ trên các task mà cả hai thay đổi cùng fire**. Đây là chỗ duy nhất phát sinh tương tác.
4. nếu bản ghép kém hơn bản đơn lẻ tốt nhất thì ghi cạnh `conflicts_with` và giữ bản tốt hơn.

Cách này cho credit theo từng component (giải điểm "credit assignment thô") mà không cần ablation toàn phần.

### 3.4 Lưu trữ: Evidence ledger thay vì knowledge graph đầy đủ

Graph Task → Failure → Mechanism → Candidate cùng các cạnh helps/hurts/compatible/conflicts **không cần là nơi lưu chính**. Nguồn sự thật nên là một bảng bằng chứng phẳng, chỉ thêm dòng:

```
evidence(candidate_id, slot, task_id, task_cluster, failure_mode, model_profile_id,
         fired: bool, outcome, base_outcome (cặp), tokens, base_tokens,
         behavior_delta {give_up_rate, n_tool_calls, loop_count, ...}, seed)
```

Graph là một **view được dẫn xuất** từ bảng này: `helps` hay `hurts` là Δ có điều kiện theo cluster, `conflicts` là kết quả của bước merge. Lợi ích: không phải giữ đồng bộ nhiều cấu trúc, và mọi cạnh của graph đều có số liệu gốc để kiểm tra lại.

Các tầng giữ lại, vì có bằng chứng ủng hộ:

- **Mechanism** (F10): một mechanism là một cặp `precondition → action` trừu tượng. Nhiều candidate (mã hoặc prompt, cho từng model) có thể hiện thực cùng một mechanism.
- **Failure mode**: được định nghĩa bằng **chữ ký hành vi** trên trajectory (F9), không bằng văn bản đề bài.

### 3.5 Router: chọn theo bằng chứng, bảo thủ, kích hoạt lười

Thay công thức `argmax [Σ U + λ Σ Compat − β Cost]` bằng các bước đơn giản hơn:

1. **Mặc định là H0 cho từng slot.** Một slot chỉ đổi sang candidate khác khi **cận dưới** của Δ (theo cluster và model profile) > 0 sau khi trừ chi phí. Đây là nguyên tắc "do no harm" (F3, F8). Model mạnh thường chỉ cần ít thay đổi.
2. **Tham lam theo slot,** rồi loại các cặp có cạnh `conflicts_with`. Không cần beam search khi số candidate được tin cậy mỗi slot nhỏ.
3. **Kích hoạt lười.** Phần lớn candidate là middleware có `precondition`. Chúng được *nạp* sẵn nhưng chỉ *fire* khi điều kiện thoả trong trajectory. Router upfront chỉ cần quyết định những slot không thể kích hoạt lười, như S6 orchestration và S10 generation control. Việc này vừa giảm token (F6), vừa tránh phải đoán từ văn bản đề bài (F9).

**Bỏ** phần "sinh candidate mới lúc inference từ task thật". Lúc test không có reward, nên mọi candidate sinh ra lúc đó không qua được gate bằng chứng. Nếu muốn học online thì chỉ được học từ tín hiệu không cần nhãn (ví dụ "lỗi tool lặp lại"), và việc đó phải được báo cáo như một điều kiện thí nghiệm riêng.

**Exploration kiểu bandit** chỉ dùng trong vòng tiến hoá (có reward), để phân bổ ngân sách đánh giá cho các candidate có độ bất định cao. Không dùng lúc test.

### 3.6 Quản lý pool

- **Bất biến và có version** (F7): sửa một candidate tạo ra candidate mới có `derived_from`.
- **Prune**: candidate có cận trên của Δ < 0 trên mọi cluster thì được lưu trữ (archive), không xoá, vì có thể hợp với một model khác.
- **Consolidate**: hai candidate cùng mechanism, cùng slot và có Δ tương đương thì giữ bản rẻ hơn.

---

## 4. Chọn harness có điều kiện theo hành vi model

Ý tưởng: lưu xem **component tác động thế nào lên một hành vi**, không chỉ lên điểm số. Khi gặp model mới, đo hành vi của model đó rồi chọn những component chữa đúng các hành vi xấu mà model mới thực sự có.

### 4.1 Behavior profile

Một vector số đo được từ trajectory, không cần nhãn:

| Hành vi | Cách đo | Ví dụ từ các lần chạy |
|---|---|---|
| Kiên trì tìm kiếm | số lời gọi tool trước khi trả lời | BCP: ling ~20 lần search, luna ~4 |
| Bỏ cuộc sớm | tỉ lệ trả lời "không xác định" khi còn bước | luna BCP |
| Lặp vòng | số hành động lặp liên tiếp | ALFWorld "Nothing happens" |
| Tuân thủ định dạng tool | tỉ lệ tool call parse được | GLM xuất tool call dạng văn bản |
| Tuân thủ chỉ dẫn | Δ hành vi khi chèn một chỉ dẫn chuẩn (probe) | model mạnh bỏ qua hướng dẫn thừa |
| Ngân sách reasoning | tỉ lệ câu trả lời rỗng hoặc bị cắt vì reasoning | ag và luna (F11) |
| Hoàn thành sớm | gọi `complete` hay `finish` khi hậu điều kiện chưa thoả | AppWorld |
| Calibration | blind confidence so với kết quả thật | mục 3.2 |
| Độ dài mỗi bước | token mỗi bước | luna 24k/câu, ling 500k/câu |

### 4.2 Lưu gì

Với mỗi candidate, ledger lưu `behavior_delta`: candidate làm thay đổi hành vi nào, theo hướng nào, trên profile nào. Ví dụ: "S7/refuse-early-giveup làm giảm give-up rate 30% và tăng accuracy với profile *give-up cao*; không có tác dụng với profile *search dai*".

Đơn vị chuyển giao giữa các model là **cặp (hành vi, mechanism)**, không phải tên model.

### 4.3 Inference cross-model

1. **Probe:** chạy model mới trên một bộ hiệu chỉnh nhỏ cố định, khoảng 10–20 task train, chỉ với H0. Thu behavior profile và một ít outcome.
2. **Ghép profile:** tìm các profile đã biết gần nhất, mỗi chiều được chuẩn hoá. Prior cho Δ của mỗi candidate lấy từ các profile đó, có trọng số theo khoảng cách.
3. **Lọc theo hành vi:** candidate nhắm vào một hành vi mà model mới *không có* (ví dụ chống bỏ cuộc cho một model vốn search dai) thì bị hạ ưu tiên, dù trung bình nó tốt.
4. **Xác nhận nhanh:** đánh giá ghép cặp vài candidate có prior cao nhất trên bộ hiệu chỉnh trước khi dùng.

**Đường cơ sở cần báo cáo:**
- dùng harness tốt nhất của model nguồn;
- dùng H0;
- tiến hoá lại từ đầu cho model mới.

Chỉ số chính: lượng tăng đạt được trên tổng ngân sách dùng cho model mới.

---

## 5. Những gì nên bỏ hoặc gộp so với bản 1

| Bản 1 | Đề xuất | Lý do |
|---|---|---|
| Knowledge graph là nơi lưu chính | Evidence ledger phẳng, graph là view | ít cấu trúc phải đồng bộ hơn; mọi cạnh có số liệu gốc |
| Composition `argmax` với λ, β và beam | mặc định H0, tham lam theo cận dưới, loại xung đột, kích hoạt lười | ít tham số phải chỉnh; bảo thủ (F3) |
| Selective causal ablation là cơ chế riêng | là một phần của merge (3.3) và đánh giá ghép cặp | cùng một phép đo, khỏi làm hai lần |
| Bandit reuse/explore lúc inference | chỉ trong vòng tiến hoá | lúc test không có reward |
| Sinh candidate lúc inference | bỏ, hoặc tách thành thí nghiệm riêng | không qua được gate bằng chứng |
| Chọn router theo đặc trưng văn bản task | đặc trưng hành vi và predicate trên trajectory | F9 |
| Tools và skills là phần thêm sau | skill là nội dung của S1/S2; tool là S2 | tránh slot trùng |

---

## 6. Kế hoạch implement tối thiểu

Làm theo thứ tự này, để mỗi bước đều chạy và đo được trước khi sang bước sau:

1. **Telemetry và hook.** Tách vòng lặp H0 thành 11 hook (mục 2). Mỗi hook log `slot, candidate, fired`. Thêm tính behavior profile từ trajectory (4.1). *Kiểm thử:* chạy H0 với ba model đã có dữ liệu để có ba profile đầu tiên.
2. **Evidence ledger** cùng đánh giá ghép cặp K roll, kiểm định tuần tự (dừng sớm khi đủ chắc). Lấy lại phần thống kê `confirm` của B2.
3. **Generalization gate**: lint tĩnh, schema precondition/action, kiểm tra không-hại chéo cụm.
4. **Proposer hai nhánh** structural và guidance, kèm blind/hindsight report. Đầu vào gồm trajectory, chữ ký failure mode và report. Proposer chỉ được sinh candidate có precondition chạy được.
5. **R³ merge** và router bảo thủ có kích hoạt lười.
6. **Cross-model:** probe → ghép profile → prior → xác nhận nhanh.

**Giao thức đánh giá** (rút từ F1):
- ≥ 3 seed;
- val ≥ 50 task, hoặc dùng train nhiều roll cho đánh giá ghép cặp;
- kiểm định ghép cặp theo task (McNemar hoặc bootstrap);
- báo cáo theo **từng model**, vì F8 cho thấy thứ hạng đảo chiều.

**Ablation cần có:**
- không gate;
- harness toàn cục (không routing);
- routing theo văn bản thay vì hành vi;
- không có behavior profile (cross-model);
- không kích hoạt lười, để đo chi phí.

**Benchmark:** bỏ ALFWorld với model mạnh vì H0 đạt trần (ag 100%). Nếu cần thêm, chọn benchmark mà model mạnh vẫn còn failure niche rõ ràng.

## 9. Bài học từ 4 lần chạy B4 trên luna (v1, v2 × BCP, AppWorld) và đề xuất v3

Số liệu: `results/medium_luna/runs/{b4v1,b4}/*/{pool,log}.json`, `docs/luna_results.md` mục 6–7.

| Quan sát | Bằng chứng | Hệ quả cho ý tưởng |
|---|---|---|
| O1. Ghép thêm cơ chế vào bộ hiện tại **luôn** làm val giảm | 9/9 lần thử bộ ≥ 2 cơ chế sau vòng đầu đều thấp hơn bộ cũ (v2 AppWorld: +m7 1W/4L, +m9 0W/5L) dù từng cơ chế đều qua sàng lọc | Sàng lọc đứng riêng trên H0 không đo được tương tác. "Compatibility-aware composition" của ý tưởng gốc là cần thiết, nhưng phải đo bằng thực nghiệm chứ không suy ra từ đồ thị |
| O2. Toàn bộ lợi ích đến từ vòng 1 | Bộ cuối của cả 4 lần chạy = bộ chọn ở vòng 1 hoặc 2; vòng 3–5 đổ ~60% ngân sách mà không gộp được gì | Cần dừng sớm / chuyển ngân sách sang việc khác (seed, val lớn hơn) khi lợi ích cận biên ≈ 0 |
| O3. Proposer kẹt ở một failure mode | BCP: `early_stop` 4 vòng liên tiếp ở cả v1 và v2, không cơ chế nào được gộp | Thiếu cơ chế "từ bỏ" một mode sau k lần thất bại |
| O4. Hindsight report không đáng tin để lọc | AppWorld: LLM quy 29/30 lỗi cho "reasoning", nhưng cơ chế harness (m3) vẫn tăng +4 điểm; blind confidence đảo ngược (đúng 0,35 < sai 0,43) | Tự đánh giá của model chỉ dùng để **sinh giả thuyết**, không dùng để **loại bằng chứng**. Quy trách nhiệm phải bằng can thiệp (sàng lọc), không bằng lời kể |
| O5. Cơ chế có điều kiện hẹp tổng quát tốt hơn guidance toàn cục | v2 AppWorld: 5/5 guidance bị loại; bộ cuối 1 inject có điều kiện → test 78,8 (v1 với 2 guidance: 71,7) | Giữ "placement rule", nhưng ưu tiên mặc định cho precondition hẹp |
| O6. Nhiễu lớn ngang hiệu ứng | Cùng cấu hình, BCP 33 vs 28; tăng sàng lọc +0,3 vẫn rớt val | Mọi quyết định cần khoảng tin cậy, không dùng điểm trung bình |

### Đề xuất v3 (đều là nguyên tắc chung)

1. **Sàng lọc cận biên (marginal screening) thay cho sàng lọc độc lập.** Ứng viên chạy trên *bộ hiện tại* (không phải H0),
   trên task mà *bộ hiện tại* thất bại; task an toàn = task bộ hiện tại luôn giải. Giải quyết trực tiếp O1. Ghi vào ledger
   cặp (cơ chế, bộ nền) → dần dần có ma trận tương thích thực nghiệm, đúng tinh thần "compatibility-aware composition".
2. **Lịch failure mode có ngân sách (bandit).** Mỗi mode có điểm = tần suất lỗi × xác suất sửa được (ước lượng từ lịch sử
   sàng lọc). Sau k = 2 vòng không gộp được gì, mode bị "đóng băng" và ghi lại là *không sửa được bằng harness với model này*
   — đây chính là thông tin hành vi cần cho chọn harness đa model (mục 4.1). Giải quyết O3.
3. **Dừng sớm và tái phân bổ ngân sách.** Khi 2 vòng liên tiếp không gộp, dừng tiến hóa; dùng ngân sách còn lại để chạy lại
   val với roll thứ 2 cho bộ cuối và 1–2 bộ dự phòng tốt nhất trong pool, chọn theo LCB. Giải quyết O2, O6.
4. **Quy trách nhiệm bằng can thiệp.** Bỏ bước loại bằng chứng theo hindsight; giữ report làm đầu vào sinh giả thuyết.
   Thêm phân tích ex post trên test/val: tỉ lệ thành công khi cơ chế *kích hoạt* vs *không kích hoạt* (đã log `mech`)
   để cập nhật độ tin cậy của từng cơ chế mà không tốn thêm episode. Giải quyết O4.
5. **Repertoire liên phiên, chọn theo hồ sơ hành vi.** Giữ pool qua các model; với model mới, đo hồ sơ hành vi trên vài task
   train bằng H0, rồi thử trước các cơ chế đã thắng trên model có hồ sơ gần nhất (khoảng cách trên `profile()`); chỉ đề xuất
   cơ chế mới cho failure mode chưa có cơ chế phù hợp. Đây là phần ý tưởng chưa được kiểm chứng; cần thêm ít nhất một model
   thứ hai (ví dụ ag hoặc ling, đã có kết quả H0) để đánh giá.
6. **Giữ nguyên** các thành phần đã chứng minh có ích: DSL precondition khai báo, cổng khái quát hóa (không vi phạm lần nào
   trong 40 ứng viên), ngân sách gây hại theo phạm vi, biên ghép cặp khi gộp.

Thứ tự ưu tiên triển khai: (1) → (3) → (2) → (4) → (5). (1) và (3) rẻ (chỉ đổi tập task và vòng lặp), và nhắm vào hai
nguồn lãng phí lớn nhất quan sát được.
