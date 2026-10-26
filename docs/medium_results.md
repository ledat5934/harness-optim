# Kết quả lần chạy MEDIUM (1 seed, tập test 100 tác vụ) và nhận xét từng baseline

Ngày chạy: 2026-10-25. Số liệu tính bằng `python scripts/analyze_medium.py` từ `results/medium/*.jsonl` (bảng đầy đủ: `results/medium/analysis.md`). Model `inclusionai/ling-3.0-flash` cho agent, proposer và judge BrowseComp-Plus. Chi phí lần chạy: **$9,39**.

Giao thức: 5 vòng tiến hóa, 50 tác vụ train × 3 roll, 30 tác vụ val, 2 tác vụ kiểm tra mỗi vòng, tập test cố định 100 tác vụ mỗi benchmark (`benchmarks/<bench>/test100.json`). Episode lỗi hạ tầng tính là thất bại; episode HTTP 402 (key hết tiền) bị loại khỏi mẫu. McNemar: chính xác, hai phía, trên các tác vụ mà đúng một trong hai phương pháp thành công.

## 1. Kết quả test

| benchmark | H0 | B1 Meta-Harness | B2 ModularRSI | B3 MemoHarness |
|---|---|---|---|---|
| ALFWorld (100) | 73% | **86%** (+18/−5, p = 0,011) | 70% (+11/−14, p = 0,69) | 81% (+18/−10, p = 0,19) |
| BrowseComp-Plus (100) | 17% | không có kết quả hợp lệ ¹ | 15% (p = 0,73) | 18% (p = 1,0) |
| AppWorld TGC (99) | 6,1% | không có kết quả hợp lệ ¹ | 4,0% ² | 7,0% trên 57 tác vụ ³ |

¹ Hai lần chạy B1 đầu bị lỗi bản port (mục 3); lần chạy lại sau khi sửa bị dừng vì key hết tiền.
² Harness cuối của B2 trên AppWorld thực chất là H0 (biến thể memory không có tác dụng, mục 3).
³ Key hết tiền khi B3 đang chạy test: 57/99 tác vụ có kết quả.

Chi phí mỗi episode test (USD) và token:

| benchmark | H0 | B1 | B2 | B3 |
|---|---|---|---|---|
| ALFWorld | 0,00066 (62,6k tok) | **0,00054** (51,4k) | 0,00072 (67,1k) | 0,00060 (52,5k) |
| BrowseComp-Plus | 0,00471 (526k) | – | 0,00451 (497k) | 0,00685 (392k) ⁴ |
| AppWorld | 0,00198 (186k) | – | 0,00192 (183k) | 0,00256 (160k) ⁴ |

⁴ B3 nâng `max_tokens` lên 4096: ít token hơn nhưng nhiều token output hơn (đắt gấp 3), nên $/episode cao hơn.

**Độ nhiễu giữa hai lần chạy** (cùng một harness có hành vi y hệt H0, chạy lại trên cùng tác vụ):

| benchmark | H0 | lần chạy lại | số tác vụ đổi kết quả |
|---|---|---|---|
| ALFWorld | 73% | 69% | 30/100 (13 sang đúng, 17 sang sai) |
| BrowseComp-Plus | 17% | 21% | 10/100 (7 / 3) |
| AppWorld | 4,5% | 4,5% (66 tác vụ) | 0/66 |

Nghĩa là chênh lệch tổng ±4 điểm là nhiễu thuần túy, và kết quả từng tác vụ rất ngẫu nhiên. Chỉ B1 trên ALFWorld vượt mức nhiễu một cách có ý nghĩa thống kê.

## 2. Diễn biến tiến hóa

- **ALFWorld.** B1: cả 5 vòng qua cổng, harness cuối (r5, cha r1) thêm vào `agent_loop/default.py` khoảng 20 dòng: sau 3 quan sát "Nothing happens" liên tiếp thì nhắc gọi `admissible_commands()`. Cải thiện lớn nhất ở pick_heat (10→15/17) và pick_two (4→10/13). B2: chỉ vòng 2 thăng hạng (`agent_loop/recovery_after_repeat_failures`, cùng ý tưởng với B1), 3 vòng "no open proposal". B3: vòng 1 bị canary loại (luật success −0,5 không kèm reward), vòng 2–5 qua; chọn r5 (temperature 0,7, max_tokens 4096, giữ 12 lượt, các đoạn chiến lược trong system prompt).
- **BrowseComp-Plus.** B2: vòng 2 thăng hạng `verifier/require_substantive_answer` (val 17% so với 13%), composer chọn nó cho 54/100 tác vụ test; tỉ lệ không nộp đáp án giảm 13→9 nhưng accuracy không tăng. B3: canary qua cả 5 vòng; val dao động 7–17% giữa các vòng.
- **AppWorld.** H0 rất thấp (train 11/150, val 1/30). B2: 3/5 vòng không có biến thể qua cổng; vòng 4 thăng hạng `memory/token_recall` (val 13% so với 0%). B3: val theo vòng 3%, 13%, 17%, 13%, 7%.

## 3. Lỗi bản port phát hiện trong lần chạy (đã sửa, ghi ở `docs/baseline_fidelity.md`)

1. **Token `<arg_value>`**: model không xuất được token gọi tool của chính nó, trả về `">`, làm hỏng mọi bản chép `tool_policy/default.py`. B1 mất 3/5 vòng ALFWorld vì lỗi này ở lần chạy đầu. Sửa ở `proposer_io.restore_special_tokens`.
2. **Biến thể mới phải được `bundle.json` chọn**: trong Meta-Harness mỗi ứng viên là file agent mới nên luôn chạy; trong H0 file biến thể mới vô tác dụng nếu không được chọn, và prompt B1 không nói điều này. Harness cuối của B1 trên BrowseComp-Plus và AppWorld vì thế y hệt H0. Sửa bằng SKILL thay đổi 9 và cổng `unselected_variants`.
3. **`memory.update` không bao giờ được gọi trong H0** (mỗi episode dựng harness mới; bộ nhớ xuyên episode chỉ có khi bên gọi truyền vào, như B3). Giao thức slot mà B1 và B2 nhận được lại mô tả `update(...)`, nên các biến thể memory của B1 (`SearchMemory`) và B2 (`token_recall`) đều không có tác dụng. SKILL của B1 đã ghi rõ; prompt của B2 chưa sửa (B2 không chạy lại).
4. **HTTP 429/520** khi chạy song song: tăng số lần thử lại (`LLM_MAX_RETRIES=8`) và thử lại mã 52x; các baseline bị ảnh hưởng ở lượt đầu đã chạy lại. Còn 3 episode val lỗi 520 (B2 ALFWorld r3, B2 BrowseComp-Plus r1, B1 BrowseComp-Plus r3 cũ), mỗi cái 1/30 tác vụ val của một vòng.

## 4. Nhận xét từng baseline

### B1 Meta-Harness (tiến hóa mã tự do, toàn cục)
**Điểm mạnh**
- Kết quả tốt nhất và là kết quả duy nhất có ý nghĩa thống kê: ALFWorld 86% so với 73% (p = 0,011), đồng thời rẻ hơn H0 (ít bước hơn, $0,00054 so với $0,00066 mỗi episode).
- Thay đổi nhỏ, chung, đọc được: một cơ chế phục hồi 20 dòng rút ra trực tiếp từ việc đọc trajectory thất bại (agent lặp lệnh vô hiệu). Không gắn với tác vụ cụ thể.
- Linh hoạt: có thể sửa bất kỳ slot nào và tích lũy qua các vòng (r5 lấy r1 làm cha).

**Điểm yếu**
- Mong manh với lớp vận hành: hai lỗi port (token `<arg_value>`, biến thể không được chọn) làm B1 mất phần lớn số vòng hoặc tạo ra harness không đổi gì. Proposer không có cách tự kiểm tra rằng mã mới thực sự chạy (không có tool, chỉ có cổng tĩnh + toy run).
- Luật chọn trên val nhỏ chọn theo nhiễu: ở BrowseComp-Plus và AppWorld, các ứng viên vô tác dụng vẫn thành "new incumbent" vì val 4/30 > 1/30.
- Hiểu sai ngữ nghĩa runtime (bộ nhớ xuyên episode) khi mô tả giao thức không khớp với runtime thật.
- Chưa có kết quả hợp lệ trên BrowseComp-Plus và AppWorld.

### B2 ModularRSI (đề xuất theo module, cổng nhiều tầng, composer chọn theo tác vụ)
**Điểm mạnh**
- Chẩn đoán đúng hướng: trên ALFWorld tìm ra cùng cơ chế với B1 (phục hồi sau lỗi lặp); trên BrowseComp-Plus nhắm đúng hiện tượng "không nộp đáp án".
- Cổng chặt: nhiều biến thể bị review/cổng loại (AppWorld 3/5 vòng) nên ít khi thăng hạng thứ hỏng; chi phí tìm kiếm thấp nhất (ít lần chạy val).
- Thư viện chỉ cộng thêm, `default` luôn còn, nên không làm harness tệ đi nhiều (mọi kết quả test nằm trong mức nhiễu).

**Điểm yếu**
- Composer chọn biến thể cho từng tác vụ dựa trên mô tả trước khi chạy, nên cơ chế dùng chung (phục hồi) gần như không bao giờ được chọn: ALFWorld 100/100 tác vụ test dùng `default`, val vòng 2 là 30/30. Thăng hạng dựa trên val mà biến thể không hề chạy. Routing probe đã báo `routing_unproven`, nhưng trong bản port routing chỉ là chẩn đoán.
- Nhiều vòng không sinh được đề xuất ("no open proposal": ALFWorld 3/5, BrowseComp-Plus 2/5), một phần do bản port chỉ chẩn đoán `MAX_DIAG = 4` tác vụ mỗi vòng.
- Khi tác vụ thất bại cả 3 roll (đa số ở AppWorld, BrowseComp-Plus), không có cặp thành công/thất bại để đối chiếu, nên mất lợi thế chính của phương pháp.
- Không cải thiện được benchmark nào (70%, 15%, 4%).

### B3 MemoHarness (ngân hàng kinh nghiệm + tìm kiếm D1–D6 + thích nghi theo ca)

> **Lưu ý: bản port B3 hẹp hơn MemoHarness gốc.** Trong mã gốc, controller duy nhất được hỗ trợ (`controller="codex"`, `CodexBundleController`) là Codex CLI sửa trực tiếp bundle harness: chỉ dẫn agent (`AGENTS.override.md`), `policy.json` (D1–D6), `.memoharness/playbook.md` và `memory.md`. Mã còn có `LLMController.decide_next_harness`, sinh lại toàn bộ mã Python `HarnessImpl`. Prompt chỉ-cấu-hình `_CONFIG_ONLY_DOC` trong mã gốc chỉ dùng cho `adapt_for_case` lúc test. Bản port dùng prompt chỉ-cấu-hình cho cả bước tìm kiếm toàn cục, nên kết quả dưới đây là của biến thể hẹp này, không phải của MemoHarness đầy đủ (`docs/baseline_fidelity.md`, B3 (c)).

**Điểm mạnh** (của bản port)
- Ổn định và rẻ khi tìm kiếm: bản port chỉ đổi cấu hình, không viết mã hay văn bản tự do, nên không bao giờ hỏng harness.
- Cải thiện trên ALFWorld (81%, +8) và nhỉnh hơn H0 ở hai benchmark còn lại, dù chưa có ý nghĩa thống kê.
- Canary với luật thứ ba (port từ mã gốc) đã loại một đề xuất tệ ở ALFWorld.

**Điểm yếu** (phần lớn do bản port)
- Không gian tìm kiếm hẹp: chỉ 3 số (temperature, max_tokens, số lượt giữ) và văn bản chiến lược có tác dụng trên H0. Phần lớn chẩn đoán nhắm vào núm của Harbor không tồn tại trong H0 (`stop_rule`, `tool_protocol='alfworld'`, `tool_access=bash`), nên văn bản chiến lược mô tả những thay đổi không xảy ra.
- Không tách được nguồn cải thiện (temperature 0,7? giữ 12 lượt? văn bản chiến lược?) nếu không ablation.
- Canary 2 tác vụ quá yếu khi tỉ lệ thành công thấp: qua cả 5 vòng ở BrowseComp-Plus.
- Thích nghi theo ca gần như không hoạt động (đổi cấu hình ở 8/100 tác vụ ALFWorld, 4/100 BrowseComp-Plus).
- Nâng `max_tokens` làm tăng chi phí mỗi episode (+45% ở BrowseComp-Plus) dù số token giảm.

## 5. Nhận xét chung
- **Val 30 tác vụ là điểm nghẽn của cả ba phương pháp.** Với mức nhiễu đo được (30/100 tác vụ ALFWorld đổi kết quả giữa hai lần chạy cùng harness), chênh 1–3 tác vụ val không nói lên gì; cả B1, B2, B3 đều có lúc chọn ứng viên theo nhiễu. Nên tăng val (hoặc chạy val nhiều roll) và yêu cầu chênh tối thiểu khi thăng hạng.
- **Khi tỉ lệ thành công nền rất thấp** (AppWorld 6%, BrowseComp-Plus 17%), cả ba phương pháp học từ lỗi để sinh đề xuất, nhưng bước kiểm chứng gần như không phân biệt được tốt/xấu.
- **Cần kiểm tra "thay đổi có thực sự chạy không"** (biến thể được chọn, hàm được gọi) như một cổng chung cho mọi phương pháp: các lần thăng hạng vô tác dụng ở lần chạy này (B1 trên BrowseComp-Plus và AppWorld, B2 trên ALFWorld và AppWorld) lẽ ra bị chặn sớm.

## 6. Chưa hoàn thành
- B1 trên BrowseComp-Plus và AppWorld (sau khi sửa lỗi port): cần chạy lại, ước khoảng $1,8.
- 42 tác vụ test còn lại của B3 trên AppWorld: khoảng $0,1.
- B2 với prompt giao thức memory đã sửa và `MAX_DIAG` lớn hơn: tùy chọn, khoảng $1–2.
