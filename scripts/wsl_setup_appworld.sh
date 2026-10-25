#!/bin/bash
set -e
python3 -m venv /root/aw-venv
. /root/aw-venv/bin/activate
pip install -q -U pip wheel setuptools --timeout 60 --retries 10
pip install -q appworld requests --timeout 60 --retries 10
export APPWORLD_ROOT=/root/appworld_root
mkdir -p $APPWORLD_ROOT && cd $APPWORLD_ROOT
appworld install
appworld download data
appworld verify tests || echo "verify tests failed: $?"
appworld verify tasks || echo "verify tasks failed: $?"
pip freeze > /mnt/e/KLTN/requirements/appworld.freeze.txt
echo APPWORLD_SETUP_DONE
