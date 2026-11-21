# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:14:31. Kasus: 18 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_holdout.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 94.4% |
| Akurasi ketat satu giliran | 94.4% |
| Token LLM masuk / keluar | 638521 / 8107 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 92.9% |
| Hitung: tool benar (percobaan pertama) | 92.9% |
| Hitung: semua argumen benar | 92.9% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 92.9% |
| Tanya balik benar | 100.0% |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | 100.0% |
| Total galat tool | 1 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.06 / 10.37 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 2 | 50.0% |
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

## Kasus yang salah (1)

### h-06 (hitung, bukan_pegawai)
- Tool harapan: `calculate_pph21_non_employee`; dipanggil: `['calculate_pph21_direct_pasal_17']`
- PPh harapan 375000, aktual None
- Jawaban: Data yang dihitung: PPh 21 tarif Pasal 17 langsung; tahun pajak 2025; ber-NPWP; jenis: peserta_kegiatan; jenis kegiatan: lainnya; penghasilan bruto Rp15.000.000; penghasilan bruto yang dihitung Rp15.000.000. PPh 21 terutang adalah **Rp750.000**. | Rincian | Nilai | |---|---:| | Penghasilan bruto (Pe
