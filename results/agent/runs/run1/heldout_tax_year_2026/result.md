# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T12:58:17. Kasus: 14 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_2026.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 92.9% |
| Akurasi ketat satu giliran | 92.9% |
| Token LLM masuk / keluar | 985598 / 6148 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 88.9% |
| Hitung: tool benar (percobaan pertama) | 88.9% |
| Hitung: semua argumen benar | 77.8% |
| Hitung: akurasi per field | 96.2% |
| Hitung: angka akhir benar | 88.9% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 6 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.86 / 12.25 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 100.0% |
| dewan_komisaris | 1 | 100.0% |
| final | 1 | 100.0% |
| pegawai_tetap_bulanan | 2 | 100.0% |
| pegawai_tetap_masa_terakhir | 1 | 100.0% |
| pegawai_tidak_tetap | 1 | 100.0% |
| pensiunan | 1 | 0.0% |
| pph26 | 1 | 100.0% |
| tolak | 5 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_2026 | 14 | 92.9% |

## Kasus yang salah (1)

### t26-06 (hitung, pensiunan)
- Tool harapan: `calculate_pph21_pensioner_monthly`; dipanggil: `['lookup_ptkp', 'lookup_ptkp', 'lookup_ptkp']`
- PPh harapan 0, aktual None
- Jawaban: Saya belum bisa menghitung dengan data yang ada: status kawin bapak belum disebutkan. Keterangan bahwa ibu masih ada tidak memastikan apakah bapak berstatus kawin, dan dua adik yang ditanggung belum cukup untuk menentukan kode PTKP tanpa informasi status tersebut. Mohon sebutkan apakah bapak berstat
