#!/bin/sh
LOG="${PPH21_DATA:-/data}/korpus_jdih/log_ocr.txt"
mkdir -p "$(dirname "$LOG")"
while true; do
  python pipeline/ocr_corpus.py --follow --max-documents 20 "$@" >> "$LOG" 2>&1
  kode=$?
  [ "$kode" = 3 ] || break
done
echo "SELESAI (kode keluar $kode)" | tee -a "$LOG"
exit "$kode"
