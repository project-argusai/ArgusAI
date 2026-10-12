#!/bin/sh
# Start/stop/status/cleanup for event_frame_collector.py (user-level, no sudo).
# Usage: collector_ctl.sh start|stop|status|cleanup
OUT="$HOME/argus-bench-frames"; RUN="$HOME/.argus-bench"; BACKEND="$HOME/ArgusAI/backend"
case "$1" in
  start)
    mkdir -m700 -p "$OUT" "$RUN"; rm -f "$OUT/STOP"
    cd "$BACKEND" && ARGUS_BACKEND="$BACKEND" nohup nice -n 10 venv/bin/python "$RUN/scripts/event_frame_collector.py" < /dev/null >> "$RUN/collector.log" 2>&1 &
    echo $! > "$RUN/collector.pid"; echo "started pid $(cat "$RUN/collector.pid")" ;;
  stop)
    touch "$OUT/STOP" 2>/dev/null; [ -f "$RUN/collector.pid" ] && kill "$(cat "$RUN/collector.pid")" 2>/dev/null; pkill -f "$RUN/scripts/event_frame_collector.py" 2>/dev/null; rm -f "$RUN/collector.pid"; echo stopped ;;
  status)
    P=$(pgrep -f "$RUN/scripts/event_frame_collector.py"); [ -n "$P" ] && echo "running pid $P" || echo "not running"
    echo "events: $(cat "$OUT/index.jsonl" 2>/dev/null | wc -l | tr -d " ")  size: $(du -sh "$OUT" 2>/dev/null | cut -f1)" ;;
  cleanup)
    "$0" stop; rm -rf "$OUT" "$RUN"; echo "frames and collector removed" ;;
  *) echo "usage: $0 start|stop|status|cleanup"; exit 1 ;;
esac
