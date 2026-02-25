#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Lecture Recording Status
# @raycast.mode inline
# @raycast.icon 📋

# Optional parameters:
# @raycast.packageName lecture-to-obsidian

PYTHON="/Users/aidanwu/lecture2obsidian/venv/bin/python"
CLI="/Users/aidanwu/lecture2obsidian/app/cli.py"

"$PYTHON" "$CLI" status
