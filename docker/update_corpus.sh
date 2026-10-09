#!/bin/sh
set -u
LOG="${PPH21_DATA:-/data}/log_perbarui_korpus.txt"
AWAL="${1:-}"
JALAN=1
[ -n "$AWAL" ] && JALAN=0
echo "== MULAI $(date '+%F %T') (awal: ${AWAL:--})" | tee -a "$LOG"

tahap() {
  nama="$1"; shift
  [ "$nama" = "$AWAL" ] && JALAN=1
  [ "$JALAN" = 1 ] || return 0
  echo "== TAHAP $nama MULAI $(date '+%T')" | tee -a "$LOG"
  if ! python "$@" >> "$LOG" 2>&1; then
    kode=$?
    echo "== TAHAP $nama GAGAL $(date '+%T') (exit $kode)" | tee -a "$LOG"
    exit "$kode"
  fi
  echo "== TAHAP $nama SELESAI $(date '+%T')" | tee -a "$LOG"
}

tahap jdih_daftar   pipeline/corpus_jdih.py list
tahap jdih_halaman  pipeline/corpus_jdih.py pages
tahap jdih_unduh    pipeline/corpus_jdih.py download
tahap pajak_daftar  pipeline/corpus_pajak.py list
tahap pajak_detail  pipeline/corpus_pajak.py detail
tahap mutu          pipeline/corpus_quality.py assess
tahap gabung        pipeline/merge_corpus.py
tahap relasi_klaim  pipeline/relation_claims.py
tahap relasi_bukti  pipeline/relation_evidence.py
tahap relasi_teks   pipeline/relation_text.py
tahap dasar_hukum   pipeline/legal_basis.py
tahap graf_tulis    pipeline/build_graph.py --write
tahap faq_graf      pipeline/faq.py graph
echo "== SEMUA SELESAI $(date '+%F %T')" | tee -a "$LOG"
