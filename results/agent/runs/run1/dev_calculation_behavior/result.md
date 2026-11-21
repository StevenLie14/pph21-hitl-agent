# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T12:40:43. Kasus: 47 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 100.0% |
| Akurasi ketat satu giliran | 100.0% |
| Token LLM masuk / keluar | 1840228 / 21193 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 100.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 100.0% |
| Tanya balik benar | 100.0% |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | 100.0% |
| Total galat tool | 0 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.23 / 9.17 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 4 | 100.0% |
| dewan_komisaris | 2 | 100.0% |
| final | 3 | 100.0% |
| info | 2 | 100.0% |
| pasal17_langsung | 3 | 100.0% |
| pegawai_tetap_bulanan | 8 | 100.0% |
| pegawai_tetap_masa_terakhir | 5 | 100.0% |
| pegawai_tetap_tahunan | 2 | 100.0% |
| pegawai_tidak_tetap | 4 | 100.0% |
| pensiunan | 5 | 100.0% |
| pph26 | 2 | 100.0% |
| tanya_balik | 4 | 100.0% |
| tolak | 3 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 2 | 100.0% |
| resmi | 23 | 100.0% |

## Kasus yang salah (0)
