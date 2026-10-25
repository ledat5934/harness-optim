# Các vấn đề mở và những gì một lần chạy thật cần

## Lần chạy smoke cho thấy gì và chưa cho thấy gì
- **Hạ tầng hoạt động xuyên suốt từ đầu đến cuối:**
  - 3 benchmark × (H0 + 3 baseline), 120 episode của agent trong các lần chạy cuối
  - mọi lệnh gọi LLM đều được ghi log với `usage.cost` thực
  - một sổ ngân sách bền vững
  - một H0 dùng chung (kiểm tra bằng hash) theo giao thức ngân sách ngang nhau
- **Điểm số không cho thấy phương pháp nào tốt hơn.** Với 3 tác vụ kiểm thử mỗi ô, một tác vụ = 33 điểm.
  - ALFWorld đạt trần ở mọi phương pháp (3/3).
  - AppWorld ở đáy (0/3).
  - BrowseComp-Plus chênh nhau một tác vụ.
  - Độ biến thiên giữa các lần chạy ở nhiệt độ 0 đã là một tác vụ trên 3 (xem `docs/checkpoint2.md`).

## Các vấn đề mở (sắp xếp theo mức đe dọa đối với một so sánh thật)
1. **Sức mạnh thống kê.** Một so sánh thật cần đầy đủ các tập kiểm thử, ≥3 seed cho mỗi ô, và kiểm định ghép cặp theo từng tác vụ (McNemar / bootstrap theo tác vụ). Các lần chạy lại H0 (AppWorld train 2/5 → 1/5) cho thấy tính không xác định do định tuyến nhà cung cấp, ngay cả ở nhiệt độ 0.
   - Ghim nhà cung cấp OpenRouter (`provider: {order: [...], allow_fallbacks: false}`) để loại bỏ phần biến thiên do nhà cung cấp. Việc này chưa được thực hiện.
   - Lỗi kiểm thử AppWorld của B3 đến từ một nhà cung cấp phía trên (DeepInfra), vốn từ chối JSON tool-call bị lỗi định dạng trong lịch sử. Một nhà cung cấp khác đã chấp nhận.
2. **Tập validation quá nhỏ để chọn lựa bất cứ điều gì.**
   - Với 3 tác vụ val, H0 đạt trần trên ALFWorld (3/3) và bằng 0 trên AppWorld/BC+ val, nên đa số "thăng hạng" được quyết định bởi luật phá hòa theo token, chứ không phải theo tỷ lệ thành công.
   - Cần ≥50 tác vụ val (AppWorld: tập dev có 57; BC+: tách ra ≥50 truy vấn; ALFWorld: các game train).
3. **Năng lực của proposer và hành vi đặc thù của model.** Model duy nhất của chúng tôi là một model "flash" nhỏ, đồng thời đóng vai proposer, editor, composer và judge.
   - Các phương pháp gốc dùng Claude Code (Opus), Codex CLI, hoặc một editor agent có công cụ thao tác tệp.
   - Model cũng phát ra lập luận ẩn có thể ăn hết toàn bộ ngân sách đầu ra (phản hồi rỗng). Cách xử lý của chúng tôi: thử lại một lần không dùng lập luận.
   - Trong các lần chạy cuối, đề xuất đầu tiên của B1 không qua kiểm tra hợp lệ trên ALFWorld và AppWorld; một lần sửa duy nhất đã qua.
   - Các investigator của B2 đánh dấu 2/5 (ALFWorld), 4/5 (AppWorld) và 2/5 (BC+) slot là thủ phạm, và 1–2 biến thể mới mỗi benchmark đã qua mọi cổng kiểm tra.
   - Với luận văn, cần quyết định liệu proposer có được phép là một model mạnh hơn agent hay không. Cả ba bài báo đều cho phép điều này.
4. **Một vòng duy nhất, không có dòng dõi.** Giá trị của ModularRSI đến từ các dòng dõi module bị khóa theo tuần tự, K=3 rolls, và xác nhận/hoàn tác ghép cặp; của MemoHarness đến từ 10 vòng tìm kiếm có chưng cất; của Meta-Harness đến từ nhiều vòng lặp. Chỉ 1 vòng thì mới chỉ kiểm tra đường ống hoạt động.
5. **Tín hiệu đối chiếu yếu ở nhiệt độ 0.** Với K=2 rolls, chỉ AppWorld tạo ra các nhóm hỗn hợp (cùng tác vụ, có cả đạt lẫn trượt) (2 trong 5 tác vụ). ALFWorld và BC+ không có nhóm nào, nên B2 quay về đối chiếu giữa các tác vụ khác nhau. Các phương án: nhiệt độ 0.3–0.7 cho các roll bằng chứng, hoặc K=3 như ModularRSI.
6. **Truy hồi và chưng cất của B3.**
   - BM25 trên các chỉ dẫn ngắn là một thước đo độ tương đồng giữa các ca yếu. Chỉ dẫn của ALFWorld/AppWorld có cấu trúc khuôn mẫu, nên việc truy hồi chủ yếu trả về cùng một loại tác vụ.
   - Chưng cất cho ra 3 mẫu trên ALFWorld và AppWorld nhưng 0 mẫu hợp lệ trên BrowseComp-Plus, nơi cả 10 lỗi đều được chẩn đoán là D1. Đầu ra thô của bộ chưng cất không được lưu trong lần chạy smoke, nên chưa xác minh được đây là lỗi phân tích cú pháp hay lỗi nội dung. Nay nó đã được lưu (`distill_raw` trong `log.json`, và đầy đủ trong transcript `--debug`); xem mục 13.
   - Nếu BM25 vẫn không đủ, nâng cấp được cho phép là Qwen3-Embedding-0.6B chạy trên CPU (TASK.md).
7. **Điều chỉnh của B3 có thể sao chép nội dung câu hỏi kiểm thử vào prompt đã điều chỉnh.** Việc này được phép lúc kiểm thử (agent thấy câu hỏi của chính nó; không dùng nhãn). Chúng tôi che nội dung này trong các bản ghi đã commit, vì các câu hỏi BrowseComp không được phép công bố.
8. **Judge và snippet của BrowseComp-Plus.** Judge là model flash của chúng tôi, không phải Qwen3-32B, và snippet dài 2000 ký tự thay vì 512 token Qwen. Các con số của chúng tôi không so sánh được với bảng xếp hạng. Với một lần chạy thật, cần chấm lại các câu trả lời cuối bằng judge chính thức (cần GPU, hoặc Qwen3-32B được host) và báo cáo cả hai.
9. **Ràng buộc nội tiến trình của AppWorld.**
   - Bộ bảo vệ an toàn toàn cục trong tiến trình và đồng hồ bị đóng băng buộc các episode phải tuần tự.
   - Song song hóa cần các *tiến trình* riêng biệt với tên `APPWORLD_EXPERIMENT` khác nhau (chưa được cài đặt).
   - Độ trễ được ghi log bên trong tiến trình AppWorld không có ý nghĩa (đồng hồ bị đóng băng).
10. **Chi tiết tính chi phí.** Chi phí mỗi episode bao gồm lệnh gọi judge của BC+. Các lệnh gọi không thuộc episode được đo riêng cho từng phương pháp trong `results/baseline_runs.jsonl` và theo tag trong `results/spend.json`: proposer, investigator, composer, điều chỉnh, chưng cất. Chúng không thuộc ngân sách *thực thi* ngang nhau. B2 và B3 thêm một lệnh gọi LLM cho mỗi tác vụ lúc kiểm thử (composer / điều chỉnh), đây là một phần của chính các phương pháp đó.
11. **Các khoảng sai lệch so với bản gốc.** Xem `docs/baseline_fidelity.md`. Quan trọng nhất:
    - Proposer của B1 không thể duyệt quỹ đạo (các bản tóm tắt được render vào prompt); hai bước phân tích và triển khai là hai lệnh gọi tới cùng một model.
    - Bộ điều khiển của B3 chỉ sửa bề mặt cấu hình D1–D6, không sửa mã (mã gốc sinh lại `HarnessImpl`). Chỉ một phần khóa D áp dụng được lên H0.
    - B2 đã vendor các module self-evo của ModularRSI không phụ thuộc Harbor: backlog, routing, clustering, proposals, portfolio, dual_implement, rebase, promotion, routing_probe, lease, dispositions, confirm (phần thống kê). Còn khác: không có điều phối nhiều cửa sổ, judge cùng can thiệp do chúng tôi viết, routing probe chỉ là chẩn đoán, không phải cổng: một lần viết lại mô tả rồi probe lại, kết quả ghi nhận nhưng không loại làn (bản gốc dùng `routing_proven` làm điều kiện thăng hạng), investigator không có tool. Investigator hiệu quả chạy nhưng kết quả không đưa vào chọn làn.
    - B2 không có tool: investigator và reviewer đọc quỹ đạo đã được render vào prompt.
12. **Các lần thử đã bị thay thế.** Nhiều lần chạy được làm lại sau các lỗi hạ tầng: bộ phân tích TextWorld không an toàn luồng, H0 không bao giờ trả lời trên BC+, Anserini trả về tài liệu null, proposer với lập luận rỗng, phân tích JSON của B3, và sự bất đối xứng trong sửa lỗi của B2. Bản ghi thô của các lần đó đã bị xoá khi dọn artifact; chi tiêu của chúng vẫn nằm trong tổng của `results/spend.json`.

13. **Sửa lỗi phân tích cú pháp sau lần chạy smoke (các con số smoke đã commit có trước các sửa này).**
    - **Trạng thái H0 hiện tại:** hash `c7e35268c202`. `results/h0_alfworld.jsonl` đã được tạo lại với hash này. `results/h0_appworld.jsonl` và `results/h0_browsecomp_plus.jsonl` vẫn mang hash cũ `885ec0b302b8` (16 bản ghi mỗi file), nên `run_baselines.py` sẽ từ chối chúng. Cần chạy lại H0 cho hai benchmark này trước khi chạy baseline; việc này tốn chi phí LLM và chưa được thực hiện.
    - Các chỗ sửa dưới đây là sửa cho mã trước khi vendor lại B1/B2/B3. Các parser nay là `extract_json`, `parse_files`, `loads_finding_block` và `validate_attrs` của mã gốc, nên các mục B2/B3 bên dưới không còn áp dụng theo tên hàm cũ. Chế độ debug (`run_baselines.py --debug`) đã làm lộ ra các lỗi phân tích đầu ra LLM. Chúng đã được kiểm tra lại ngoại tuyến dựa trên các đầu ra thô đã lưu và được sửa. Được bao phủ bởi `tests/test_parsers.py`.
    - **Chính sách tool của H0 (làm thay đổi hash của H0 `885ec0b302b8` → `c7e35268c202`):**
      - trên BrowseComp-Plus, 16 tool call dạng văn bản kiểu GLM (`<tool_call>search<arg_key>…</arg_key><arg_value>…</arg_value></tool_call>`) không được phân tích và bị tính là "không có hành động"
      - 5 câu trả lời cuối dạng văn bản thuần (`Exact Answer: …`) không được nhận là `finish`
      - nay cả 21 đều được phân tích đúng
      - cũng đã được xử lý: các khối `<function=…>` của Qwen, JSON có dấu ngoặc lồng nhau, đối số trong khối mã hoặc bị mã hóa kép
    - **B1:** proposer thường viết `### FILE:` mà không có khối mã rào. Bộ phân tích yêu cầu có khối rào, nên đề xuất `proposal_0` của AppWorld đã commit và cả hai đề xuất debug trên ALFWorld đều bị từ chối với thông báo "no files parsed". Nay tất cả đều được phân tích và biên dịch được.
    - **B2:**
      - JSON của investigator bị cắt bởi `max_tokens` đã bị loại bỏ. Việc này xảy ra với slot `memory` trên ALFWorld và BrowseComp-Plus, nơi có `is_culprit: true` (0.65 và 0.7), nên `memory` không bao giờ được chọn. Nay các trường đầy đủ được cứu lại.
      - `confidence: "high"` sẽ làm sập lần chạy; nay các chuỗi `"true"` được chấp nhận
      - `**VERDICT:** accept` nay được tính là chấp nhận
      - nhiều dạng phản hồi của composer hơn được chấp nhận
    - **B3:**
      - `bool("false")` là `True` trong bộ làm sạch cấu hình
      - `"4096 tokens"` bị bỏ qua
      - các giá trị `primary_dim` như `"d3"` / `"D3 Generation"`, và chẩn đoán dạng danh sách hoặc nằm dưới các id ca bị cắt cụt, đã bị loại bỏ
      - đầu ra thô của bộ chưng cất nay được lưu trong `log.json` (`distill_raw`), đóng mục đang mở ở 6
    - **Adapter:**
      - các đối số tool không giải mã được nay trả về một lỗi rõ ràng cho agent thay vì chạy một lệnh hoặc đoạn mã rỗng. AppWorld có 2 lệnh `execute_python` bị cắt cụt.
      - khối rào ```` ``` ```` bên trong mã AppWorld được gỡ bỏ
      - các alias đối số phổ biến được chấp nhận
      - phán quyết của judge BrowseComp-Plus được đọc từ dòng `correct: yes|no` cuối cùng và chịu được markdown. Mọi đầu ra judge đã lưu đều được phân tích giống hệt trước và sau thay đổi.
    - **Để làm mới các con số:** chạy lại các lần chạy H0 dùng chung rồi đến các baseline (`scripts/run_smoke.sh`). Cho đến lúc đó, `run_baselines.py` từ chối bằng chứng H0 cũ, trừ chế độ `--debug`, nơi nó chỉ cảnh báo.

## Ước tính chi phí cho một lần chạy thật (từ chi phí smoke đã đo; `python scripts/budget_estimate.py`)
Chi phí trung bình đo được cho mỗi episode của agent (mọi episode smoke cuối; BC+ bao gồm judge):

| benchmark | $/episode | token/episode | thời gian thực trung bình/episode |
|---|---|---|---|
| ALFWorld | 0.00046 | 46k | 52 s |
| AppWorld | 0.00229 | 211k | 73 s (tuần tự) |
| BrowseComp-Plus | 0.00487 | 493k | 88 s |

Giao thức thật được đề xuất cho mỗi benchmark:
- 4 phương pháp (B1, B2, B3, HarnessGraph), 10 vòng, 3 seed
- bằng chứng H0 dùng chung: 100 tác vụ train × 3 rolls (AppWorld: tất cả 90 tác vụ train) + 50 val
- mỗi phương pháp mỗi vòng: 2 lần thực thi kiểm tra + 50 lần thực thi val
- kiểm thử cuối trên toàn bộ tập test: ALFWorld seen+unseen 274, AppWorld test_normal+test_challenge 585, BC+ 680 truy vấn không dùng cho train/val, cho H0 và mọi phương pháp

| benchmark | episode H0 dùng chung | episode tiến hóa mỗi phương pháp | episode kiểm thử (H0 + 4 phương pháp) | tổng episode (×3 seed) | ước tính USD |
|---|---|---|---|---|---|
| ALFWorld | 350 | 520 | 1,370 | 11,400 | 5.21 |
| AppWorld | 320 | 520 | 2,925 | 15,975 | 36.66 |
| BrowseComp-Plus | 350 | 520 | 3,400 | 17,490 | 85.15 |
| **tổng** | | | | **44,865** | **127.02** |

- Cộng thêm khoảng 10 % cho các lệnh gọi không thuộc episode (chi phí đo được là $0.0207 cho toàn bộ smoke): **≈ $140 tổng cộng**.
- **Lưu ý:**
  - Các episode test_challenge của AppWorld có thể dài hơn các episode smoke của train/dev/test_normal, nên chi phí AppWorld có thể cao gấp 1.5–2 lần.
  - Một model proposer mạnh hơn sẽ tốn thêm chi phí riêng.
  - Chi phí BC+ tỷ lệ với giới hạn số bước (25) và kích thước snippet.
- **Thời gian thực trên máy laptop này:** khoảng 11,400×52 s / 3 + 15,975×73 s / 1 + 17,490×88 s / 3 ≈ 55 h + 324 h + 143 h ≈ **520 h**.
  - Số hạng AppWorld chiếm ưu thế vì chạy tuần tự. Với 4 tiến trình AppWorld, con số giảm xuống khoảng 81 h, tổng cộng khoảng 280 h ≈ 12 ngày.
  - Một lần chạy thật cần AppWorld đa tiến trình và có thể một máy mạnh hơn, hoặc ít seed/vòng hơn cho ALFWorld, nơi H0 đã gần trần.
- Ngân sách $1 của key hiện tại thấp hơn nhiều so với mức này. Một lần chạy thật cần ngân sách khoảng $150–300, tùy độ dài thử thách AppWorld và model proposer.
