#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile cerebramo.py
python3 -m unittest discover -s tests -v

# Repository policy: provider credentials must never be committed.
if grep -RInE --exclude-dir=.git --exclude='*.md' --exclude='.amo' \
  '(sk-ant-[A-Za-z0-9_-]{16,}|sk-or-v1-[A-Za-z0-9_-]{16,}|OPENROUTER_API_KEY[[:space:]]*=|ANTHROPIC_API_KEY[[:space:]]*=|MINIMAX_API_KEY[[:space:]]*=)' .; then
  echo 'Potential provider credential material found in repository.' >&2
  exit 1
fi

echo 'CerebrAMO AutoCheck PASS'
