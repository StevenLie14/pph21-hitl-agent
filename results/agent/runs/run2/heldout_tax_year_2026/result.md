# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T14:17:51. Kasus: 14 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_2026.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 85.7% |
| Akurasi ketat satu giliran | 85.7% |
| Token LLM masuk / keluar | 968513 / 6640 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 77.8% |
| Hitung: tool benar (percobaan pertama) | 77.8% |
| Hitung: semua argumen benar | 66.7% |
| Hitung: akurasi per field | 95.8% |
| Hitung: angka akhir benar | 77.8% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 7 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.79 / 19.82 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 0.0% |
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
| uji_2026 | 14 | 85.7% |

## Kasus yang salah (2)

### t26-04 (hitung, bukan_pegawai)
- Tool harapan: `calculate_pph21_non_employee`; dipanggil: `['calculate_pph21_direct_pasal_17']`
- PPh harapan 187500, aktual None
- Jawaban: Data yang dihitung: PPh 21 tarif Pasal 17 langsung; tahun pajak 2026; ber-NPWP; jenis: peserta_kegiatan; jenis kegiatan: pendidikan_pelatihan; penghasilan bruto Rp7.500.000; penghasilan bruto yang dihitung Rp7.500.000. PPh 21 yang dipotong adalah **Rp375.000**. | Rincian | Nilai | |---|---:| | Pengh

### t26-06 (hitung, pensiunan)
- Tool harapan: `calculate_pph21_pensioner_monthly`; dipanggil: `['lookup_ptkp']`
- PPh harapan 0, aktual None
- Jawaban: Status PTKP bapak tidak bisa diisi dengan default karena wajib diketahui untuk menghitung PPh 21 pensiunan. Keterangan “ibu masih ada, 2 adik masih sekolah ditanggung bapak” belum memastikan apakah bapak berstatus kawin dan apakah kedua adik tersebut memenuhi syarat sebagai tanggungan PTKP. Mohon se
