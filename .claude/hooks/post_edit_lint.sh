#!/usr/bin/env bash
# PostToolUse hook: run ruff format + lint after editing a Python file.
# Claude Code passes a JSON payload on stdin with tool_input.file_path.

input=$(cat)
file=$(echo "$input" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)

if [[ "$file" == *.py ]]; then
    cd /home/martijn/dev/aibm
    uv run ruff format "$file"
    uv run ruff check "$file" --fix
fi
