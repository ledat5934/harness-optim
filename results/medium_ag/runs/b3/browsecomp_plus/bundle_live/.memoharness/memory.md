# Rolling Memory

Updated after iteration 0.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D4] Cases in browsecomp_plus consistently fail with zero reward under D4, indicating that the react_loop workflow with env_done_or_accepted_finish_or_max_steps terminates prematurely or fails to orchestrate multi-step web browsing trajectories effectively.
  Effect: Eliminates all progress (0.0 reward across 6 runs). Recommend altering D4 workflow to an exploratory plan-and-solve or multi-turn agent loop with explicit retry handling.
  Evidence: 770, 772