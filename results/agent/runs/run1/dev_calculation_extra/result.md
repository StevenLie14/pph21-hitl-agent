# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T12:43:37. Kasus: 18 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_holdout.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 100.0% |
| Akurasi ketat satu giliran | 100.0% |
| Token LLM masuk / keluar | 618985 / 8207 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 100.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 100.0% |
| Tanya balik benar | 100.0% |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | 100.0% |
| Total galat tool | 1 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.0 / 8.84 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 2 | 100.0% |
| dewan_komisaris | 1 | 100.0% |
| final | 1 | 100.0% |
| info | 1 | 100.0% |
| pasal17_langsung | 1 | 100.0% |
| pegawai_tetap_bulanan | 2 | 100.0% |
| pegawai_tetap_masa_terakhir | 3 | 100.0% |
| pegawai_tetap_tahunan | 1 | 100.0% |
| pegawai_tidak_tetap | 1 | 100.0% |
| pensiunan | 1 | 100.0% |
| pph26 | 1 | 100.0% |
| tanya_balik | 1 | 100.0% |
| tolak | 2 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 3 | 100.0% |

## Kasus yang salah (0)
