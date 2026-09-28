#!/usr/bin/env bash
# Stop the demo: whatever listens on the demo ports, plus the processes
# demo_start.sh recorded (e.g. the npm parent of Vite).
#
#   scripts/demo_stop.sh
set -uo pipefail

LARS_DIR="${LARS_DIR:-$HOME/lars-base}"
PID_FILE="$LARS_DIR/logs/demo/pids"
PORTS=(8090 8080 5173)            # lars_service, LabSense server, LabSense frontend

name_of() { case "$1" in 8090) echo "lars_service";; 8080) echo "LabSense server";; 5173) echo "LabSense frontend";; esac; }

stop_pids() {   # stop_pids LABEL PID... — TERM, wait up to 10 s, then KILL
  local label="$1"; shift
  [ $# -eq 0 ] && return 0
  kill "$@" 2>/dev/null
  for _ in $(seq 1 20); do
    local alive=0
    for p in "$@"; do kill -0 "$p" 2>/dev/null && alive=1; done
    [ $alive -eq 0 ] && { echo "  stopped $label (pid $*)"; return 0; }
    sleep 0.5
  done
  kill -9 "$@" 2>/dev/null
  echo "  killed $label (pid $*) — did not stop within 10 s"
}

echo "■ Stopping demo services"
for port in "${PORTS[@]}"; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ')
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    stop_pids "$(name_of "$port") on :$port" $pids
  else
    echo "  :$port already free"
  fi
done

if [ -f "$PID_FILE" ]; then
  while read -r label pid; do
    [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && stop_pids "$label" "$pid"
  done < "$PID_FILE"
  rm -f "$PID_FILE"
fi
echo "■ Demo stopped"
