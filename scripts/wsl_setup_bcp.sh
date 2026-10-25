#!/bin/bash
set -e
python3 -m venv /root/bcp-venv
. /root/bcp-venv/bin/activate
pip install -q -U pip wheel setuptools --timeout 60 --retries 10
pip install -q --no-deps pyserini --timeout 60 --retries 10
pip install -q "pyjnius>=1.7.0" numpy requests pyarrow tqdm --timeout 60 --retries 10
python -c "from pyserini.search.lucene import LuceneSearcher; print('lucene import ok')" || echo "LUCENE_IMPORT_FAILED"
pip freeze > /mnt/e/KLTN/requirements/browsecomp_plus.freeze.txt
echo BCP_SETUP_DONE
