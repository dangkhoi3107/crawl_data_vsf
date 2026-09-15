#!/usr/bin/env bash
# Chạy một lệnh crawl kéo dài nhiều ngày, không cần ngồi canh:
#   - bị chặn liên tiếp (crawl.py thoát mã 75) → nghỉ COOLDOWN_HOURS giờ rồi chạy tiếp từ chỗ dừng
#   - lỗi khác (mạng, trình duyệt crash)       → nghỉ 10 phút rồi chạy tiếp
#   - chạy xong (mã 0) hoặc Ctrl+C (mã 130)    → dừng
#
# Ví dụ:
#   ./run_forever.sh booking-hotels --fast --concurrency 3
#   COOLDOWN_HOURS=6 ./run_forever.sh booking-attractions --fast --concurrency 2
#   xvfb-run -a ./run_forever.sh booking-hotels --fast --concurrency 3    # server không có màn hình
set -u
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
COOLDOWN_HOURS="${COOLDOWN_HOURS:-3}"

while true; do
  echo "[run_forever] $(date '+%F %T') chạy: $PY crawl.py $*"
  "$PY" crawl.py "$@"
  code=$?
  case "$code" in
    0)   echo "[run_forever] $(date '+%F %T') xong."; exit 0 ;;
    130) echo "[run_forever] $(date '+%F %T') dừng theo yêu cầu."; exit 130 ;;
    75)  echo "[run_forever] $(date '+%F %T') bị chặn – nghỉ ${COOLDOWN_HOURS} giờ rồi chạy tiếp."
         sleep "$((COOLDOWN_HOURS * 3600))" ;;
    *)   echo "[run_forever] $(date '+%F %T') lỗi (mã $code) – thử lại sau 10 phút."
         sleep 600 ;;
  esac
done
