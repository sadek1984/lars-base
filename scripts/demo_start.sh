#!/usr/bin/env bash
# Start everything for the voice demo and warm the semantic cache.
#
#   scripts/demo_start.sh        (stop with scripts/demo_stop.sh)
#
#   lars_service       :8090  ~/lars-base          LARS_SEMANTIC_MODE=live
#   LabSense server    :8080  labsense/server      VOICE_BACKEND=gemini
#   LabSense frontend  :5173  labsense             npm run dev
# Logs: ~/lars-base/logs/demo/. Streamlit is not part of the voice demo.
set -uo pipefail

LARS_DIR="${LARS_DIR:-$HOME/lars-base}"
LABSENSE_DIR="${LABSENSE_DIR:-/Users/a12/labsense}"
PYTHON="${DEMO_PYTHON:-/Users/a12/miniforge3/bin/python}"
UVICORN="${DEMO_UVICORN:-/Users/a12/miniforge3/bin/uvicorn}"
DB="$LARS_DIR/src/LARS/data/lars_data_demo.duckdb"
LOG_DIR="$LARS_DIR/logs/demo"
PID_FILE="$LOG_DIR/pids"
LARS_TAG="demo-semantic-2026-09"
LABSENSE_TAG="demo-voice-ok"
PORTS=(8090 8080 5173)
WAIT_S=60

fail() { echo "❌ $*"; exit 1; }
listeners() { lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u; }

# ── 1. Pre-checks ─────────────────────────────────────────────────────────────
echo "■ Pre-checks"
[ -f "$DB" ] || fail "database not found: $DB"
[ -x "$UVICORN" ] || fail "uvicorn not found: $UVICORN (set DEMO_UVICORN)"
[ -d "$LABSENSE_DIR/node_modules" ] || fail "no node_modules in $LABSENSE_DIR — run npm install there"

# Any process holding the demo DB (DBeaver, a notebook, …) — except our own
# services on the demo ports, which are restarted below.
ours=" $(for p in "${PORTS[@]}"; do listeners "$p"; done | tr '\n' ' ') "
for pid in $(lsof -t "$DB" 2>/dev/null | sort -u); do
  case "$ours" in *" $pid "*) continue;; esac
  fail "$(ps -o comm= -p "$pid" | xargs basename 2>/dev/null) (pid $pid) holds $DB
   Close it (in DBeaver: disconnect the connection or quit DBeaver) and run this again."
done
echo "  database free: $DB"

check_tag() {   # check_tag DIR TAG
  local head tag
  head=$(git -C "$1" rev-parse --short HEAD 2>/dev/null) || { echo "  ⚠️  $1 is not a git repository"; return; }
  tag=$(git -C "$1" rev-parse --short "$2^{commit}" 2>/dev/null) || { echo "  ⚠️  tag $2 not found in $1"; return; }
  if [ "$head" = "$tag" ]; then
    echo "  $(basename "$1") at $2 ($head)"
  else
    echo "  ⚠️  $(basename "$1") HEAD $head ≠ $2 ($tag)"
  fi
}
check_tag "$LARS_DIR" "$LARS_TAG"
check_tag "$LABSENSE_DIR" "$LABSENSE_TAG"

# ── 2. Free the ports ─────────────────────────────────────────────────────────
"$(dirname "$0")/demo_stop.sh" | sed 's/^/  /'

# ── 3. Start ─────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
: > "$PID_FILE"
start() {   # start LABEL LOG DIR ENV... -- CMD...
  local label="$1" log="$2" dir="$3"; shift 3
  local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
  ( cd "$dir" && exec env "${envs[@]}" nohup "$@" > "$log" 2>&1 ) &
  echo "$label $!" >> "$PID_FILE"
  echo "  started $label (pid $!) → $log"
}
echo "■ Starting services (logs in $LOG_DIR)"
start lars_service "$LOG_DIR/lars_service.log" "$LARS_DIR" \
  LARS_SEMANTIC_MODE=live -- "$UVICORN" lars_service:app --host 0.0.0.0 --port 8090
start labsense_server "$LOG_DIR/labsense_server.log" "$LABSENSE_DIR/server" \
  VOICE_BACKEND=gemini -- "$UVICORN" main:app --port 8080
start labsense_frontend "$LOG_DIR/labsense_frontend.log" "$LABSENSE_DIR" \
  BROWSER=none -- npm run dev -- --port 5173 --strictPort

# ── 4. Wait for the ports ─────────────────────────────────────────────────────
wait_port() {   # wait_port PORT LABEL PID_LABEL LOG — fails early if the process exited
  local code pid
  pid=$(awk -v l="$3" '$1 == l {print $2}' "$PID_FILE")
  for _ in $(seq 1 "$WAIT_S"); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://localhost:$1/" 2>/dev/null)
    if [ -n "$code" ] && [ "$code" != "000" ]; then echo "  :$1 $2 up"; return 0; fi
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      echo "❌ $2 exited before answering on :$1 — last 20 lines of $4:"; tail -n 20 "$4"; exit 1
    fi
    sleep 1
  done
  echo "❌ $2 did not answer on :$1 within ${WAIT_S}s — last 20 lines of $4:"
  tail -n 20 "$4"
  exit 1
}
echo "■ Waiting for services"
wait_port 8090 lars_service lars_service "$LOG_DIR/lars_service.log"
wait_port 8080 "LabSense server" labsense_server "$LOG_DIR/labsense_server.log"
wait_port 5173 "LabSense frontend" labsense_frontend "$LOG_DIR/labsense_frontend.log"

# ── 5. Health ─────────────────────────────────────────────────────────────────
echo "■ lars_service health"
health=$(curl -s --max-time 5 http://localhost:8090/health) || fail "no /health answer on :8090"
mode=$("$PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1]).get("semantic_mode"))' "$health" 2>/dev/null)
echo "  /health: $health"
[ "$mode" = "live" ] || { tail -n 20 "$LOG_DIR/lars_service.log"; fail "semantic_mode is '$mode', expected 'live'"; }
echo "  lars-base commit: $(git -C "$LARS_DIR" log -1 --format='%h %s' 2>/dev/null) [$(git -C "$LARS_DIR" describe --tags --always 2>/dev/null)]"
echo "  labsense  commit: $(git -C "$LABSENSE_DIR" log -1 --format='%h %s' 2>/dev/null) [$(git -C "$LABSENSE_DIR" describe --tags --always 2>/dev/null)]"

# ── 6. Warm the semantic cache ────────────────────────────────────────────────
echo "■ Warming the semantic cache"
warm() { "$PYTHON" "$LARS_DIR/scripts/warmup_demo.py" --url http://localhost:8090; }
warm_out=$(warm); warm_rc=$?
echo "$warm_out" | sed 's/^/  /'
if [ $warm_rc -ne 0 ]; then
  echo "■ Some questions did not settle — retrying the warmup once"
  warm_out=$(warm); warm_rc=$?
  echo "$warm_out" | sed 's/^/  /'
fi
summary=$(echo "$warm_out" | tail -n 1)
if [ $warm_rc -ne 0 ]; then
  echo "⚠️  Warmup: $summary — the questions marked '!!' above may be refused or slow in the demo."
else
  echo "  Warmup: $summary"
fi

# ── 7. Ready ─────────────────────────────────────────────────────────────────
echo
echo "✅ READY — open http://localhost:5173"
echo "   Use Chrome Incognito and allow the microphone."
echo "   🎤 Mic: iPhone Continuity Camera OFF; macOS Sound → Input = MacBook/headset; Chrome mic = same device"
echo "   Stop everything with: $LARS_DIR/scripts/demo_stop.sh"
