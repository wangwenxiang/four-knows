#!/bin/zsh
set -u

ROOT="/Users/jay/Documents/ai-coder/four-knows"
FROM="${1:-}"
TARGET="${2:-}"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/vanish-forward.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export TZ="Asia/Shanghai"

timestamp() {
  date "+%Y-%m-%d %H:%M:%S %Z %z"
}

mkdir -p "$LOG_DIR"

{
  echo "[$(timestamp)] START from=$FROM target=$TARGET"

  if [[ -z "$FROM" || -z "$TARGET" ]]; then
    echo "[$(timestamp)] ERROR missing from/target arguments"
    exit 2
  fi

  cd "$ROOT" || exit 10
  /opt/homebrew/bin/node scripts/vanish_z007_cdp.js --send --from "$FROM" --to "$TARGET"
  rc=$?

  echo "[$(timestamp)] END from=$FROM target=$TARGET rc=$rc"
  exit "$rc"
} >> "$LOG_FILE" 2>&1
