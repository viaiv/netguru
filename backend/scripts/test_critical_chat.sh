#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source venv/bin/activate

PYTHONPATH=. pytest -q \
  tests/test_playbook_service.py \
  tests/test_chat_playbook_integration.py \
  tests/test_attachment_context_service.py \
  tests/test_chat_attachment_context_integration.py \
  tests/test_memory_service.py \
  tests/test_chat_memory_integration.py \
  tests/test_config_diff_service.py \
  tests/test_pre_change_review_service.py \
  tests/test_chat_cancellation.py \
  tests/test_agent_tool_call_ids.py \
  tests/test_agent_tools.py
