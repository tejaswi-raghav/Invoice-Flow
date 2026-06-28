#!/usr/bin/env bash
# Local dev server
set -e
pip install -r requirements.txt
uvicorn app.api:app --reload --port 8000
