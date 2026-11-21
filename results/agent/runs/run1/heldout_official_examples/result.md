# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T12:49:40. Kasus: 19 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_resmi.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 94.7% |
| Akurasi ketat satu giliran | 89.5% |
| Token LLM masuk / keluar | 826683 / 9125 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 94.7% |
| Hitung: tool benar (percobaan pertama) | 94.7% |
| Hitung: semua argumen benar | 84.2% |
| Hitung: akurasi per field | 97.1% |
| Hitung: angka akhir benar | 94.7% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 0 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.53 / 9.92 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 100.0% |
| natura | 5 | 100.0% |
| pegawai_tetap_bulanan | 5 | 100.0% |
| pegawai_tetap_masa_terakhir | 3 | 66.7% |
| pegawai_tidak_tetap | 3 | 100.0% |
| pensiunan | 1 | 100.0% |
| pph26 | 1 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 2 | 100.0% |
| uji_resmi | 19 | 94.7% |

## Kasus yang salah (1)

### ur-06 (hitung, pegawai_tetap_masa_terakhir)
- Tool harapan: `calculate_pph21_permanent_last_period`; dipanggil: `['lookup_ptkp', 'calculate_pph21_final']`
- PPh harapan 619065, aktual None
- Jawaban: Data yang dihitung: PPh 21 final; tahun pajak 2024; ber-NPWP; jenis: honorarium_pns; jumlah bruto Rp12.017.000; golongan: III; penghasilan bruto yang dihitung Rp12.017.000. PPh 21 final atas pembayaran gaji ke-13 dan ke-14 yang disebutkan adalah **Rp600.850**. | Rincian | Nilai | |---|---:| | Jumlah
