# NOTE: these runs used luna, not gemini

`llm.py` loads `.env` with override, and `.env` has `LLM_MODEL=cx/gpt-6-luna`, so the exported
`LLM_MODEL=ag/gemini-3.8-flash` of `scripts/chain_ag2.sh` was silently replaced. 9router usage history confirms
only gpt-6-luna traffic for these runs (2026-11-04 14:00 .. 2026-11-05 22:30 UTC). Treat everything here as an extra
luna repeat (fresh H0 + B4 scratch + B4 with luna priors on luna = self-transfer), NOT as a cross-model result.
Fix: `DOTENV_KEEP=LLM_MODEL` (llm.py) and every record now stores `model`.
