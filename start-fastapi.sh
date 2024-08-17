#!/bin/bash
conda init
source ~/.bashrc
conda activate gpu
pip install -r requirements.txt
python3 -m uvicorn api.index:app --port 8001 --reload --timeout-keep-alive 120 --workers 4