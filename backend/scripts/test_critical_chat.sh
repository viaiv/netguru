#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source venv/bin/activate

PYTHONPATH=. pytest -q \
  tests/test_chat_cancellation.py \
  tests/test_agent_tool_call_ids.py \
  tests/test_agent_tools.py
