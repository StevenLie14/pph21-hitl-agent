# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T14:12:51. Kasus: 22 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_alami.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 86.4% |
| Akurasi ketat satu giliran | 63.6% |
| Token LLM masuk / keluar | 1278622 / 11220 |
| Kasus hitung yang bertanya balik padahal data lengkap | 5 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 100.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 100.0% |
| Tanya balik benar | 80.0% |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | 83.3% |
| Total galat tool | 0 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.23 / 15.21 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 3 | 100.0% |
| final | 1 | 100.0% |
| info | 12 | 83.3% |
| pegawai_tetap_bulanan | 1 | 100.0% |
| tanya_balik | 5 | 80.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_alami | 22 | 86.4% |

## Kasus yang salah (3)

### al-06 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis']`
- Jawaban: Kalau di soal tidak mencantumkan iuran pensiun, biasanya **jangan mengada-adakan nominal iuran**—catat tidak ada atau Rp0, kecuali ada keterangan lain. **Biaya jabatan berbeda:** untuk karyawan swasta berstatus pegawai tetap, biaya jabatan umumnya tetap diperhitungkan sebagai pengurang dalam perhitu

### al-21 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis']`
- Jawaban: Secara umum, **pemotongan PPh 21 pada April dengan metode TER merupakan pemotongan selama masa pajak tersebut**. Untuk pegawai tetap, pajak dihitung kembali pada masa pajak terakhir—biasanya Desember—berdasarkan penghasilan setahun dan dikurangi PPh 21 yang sudah dipotong sebelumnya. Jadi, jika hasi

### al-22 (tanya_balik, tanya_balik)
- Tool harapan: `None`; dipanggil: `['lookup_ptkp', 'calculate_pph21_non_permanent']`
- Jawaban: Data yang dihitung: PPh 21 pegawai tidak tetap; tahun pajak 2026; status K/2; ber-NPWP; upah per periode Rp9.130.000; skema: bulanan; 1 hari; penghasilan bruto yang dihitung Rp9.130.000. Untuk data tersebut, PPh 21 terutang **Rp91.300**, dengan tarif TER bulanan kategori B sebesar **1%**. Jadi poton
