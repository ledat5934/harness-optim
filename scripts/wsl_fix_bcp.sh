#!/bin/bash
. /root/bcp-venv/bin/activate
for i in $(seq 1 8); do
  err=$(python -c "from pyserini.search.lucene import LuceneSearcher; print('LUCENE_OK')" 2>&1)
  if echo "$err" | grep -q LUCENE_OK; then echo "LUCENE_OK after $i"; break; fi
  mod=$(echo "$err" | grep -oP "No module named '\K[^'.]+" | head -1)
  echo "missing: ${mod:-?}"; echo "$err" | tail -2
  [ -z "$mod" ] && break
  case $mod in torch|transformers) echo "HEAVY_DEP_REQUIRED $mod"; break;; sklearn) mod=scikit-learn;; yaml) mod=pyyaml;; esac
  pip install -q "$mod" --timeout 60 --retries 10
done
pip freeze > /mnt/e/KLTN/requirements/browsecomp_plus.freeze.txt
