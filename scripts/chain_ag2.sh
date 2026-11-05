cd /home/user/harness-optim
export B4_RESUME=1 RESULTS_SUFFIX=ag2 LLM_MODEL=ag/gemini-3.8-flash APPWORLD_ROOT=/root/appworld_root
mkdir -p results/medium_ag2/logs; L=results/medium_ag2/logs
P=/home/user/harness-optim/results/medium_luna/runs/b4,/home/user/harness-optim/results/medium_luna/runs/b4s1
chain() { # $1 bench $2 python $3 short
  for ph in "train 1" "train 2" "train 3" "val 1" "test 1"; do set -- "$1" "$2" "$3" $ph
    $2 scripts/run_h0.py --bench $1 --phase $4 --roll $5 --protocol medium --workers 4 --redo-errors >> $L/h0_$3.log 2>&1
    set -- "$1" "$2" "$3"
  done
  $2 scripts/run_baselines.py --bench $1 --method b4 --protocol medium >> $L/b4_$3.log 2>&1 &
  B4_TAG=b4prior B4_PRIOR=$P $2 scripts/run_baselines.py --bench $1 --method b4 --protocol medium >> $L/b4prior_$3.log 2>&1 &
  wait
}
chain browsecomp_plus python3 bcp &
chain appworld /root/aw-venv/bin/python aw &
wait
