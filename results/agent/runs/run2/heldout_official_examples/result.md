# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T14:07:05. Kasus: 19 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_resmi.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 84.2% |
| Akurasi ketat satu giliran | 84.2% |
| Token LLM masuk / keluar | 879946 / 8714 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 89.5% |
| Hitung: tool benar (percobaan pertama) | 89.5% |
| Hitung: semua argumen benar | 84.2% |
| Hitung: akurasi per field | 98.5% |
| Hitung: angka akhir benar | 84.2% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 0 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.68 / 20.57 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 100.0% |
| natura | 5 | 80.0% |
| pegawai_tetap_bulanan | 5 | 100.0% |
| pegawai_tetap_masa_terakhir | 3 | 33.3% |
| pegawai_tidak_tetap | 3 | 100.0% |
| pensiunan | 1 | 100.0% |
| pph26 | 1 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 2 | 100.0% |
| uji_resmi | 19 | 84.2% |

## Kasus yang salah (3)

### ur-06 (hitung, pegawai_tetap_masa_terakhir)
- Tool harapan: `calculate_pph21_permanent_last_period`; dipanggil: `['lookup_ptkp', 'calculate_pph21_final']`
- PPh harapan 619065, aktual None
- Jawaban: Angka **PPh 21 yang sudah dipotong Januari–November** dan status keluarga tidak cukup untuk menghitung PPh 21 Desember dari seluruh penghasilan setahun. Saya perlu tahu **golongan PNS** serta apakah Rp12.017.000 itu **gaji ke-13 dan THR**. Honorarium PNS dari APBN/APBD menggunakan perhitungan PPh fi

### ur-08 (hitung, pegawai_tetap_masa_terakhir)
- Tool harapan: `calculate_pph21_permanent_last_period`; dipanggil: `['lookup_ptkp', 'find_legal_basis', 'calculate_pph21_permanent_last_period']`
- PPh harapan 877150, aktual -1342000
- Argumen dikirim: `{'tahun_pajak': 2024, 'gaji_pokok': 0, 'tunjangan_tetap': 17115000, 'tunjangan_tidak_tetap': 0, 'lembur': 0, 'bonus_thr_komisi': 0, 'tunjangan_pph': 0, 'premi_jkk_dibayar_perusahaan': 0, 'premi_jkm_dibayar_perusahaan': 0, 'premi_bpjs_kesehatan_dibayar_perusahaan': 0, 'natura_kena_pajak': 0, 'penghasilan_lain': 0, 'iuran_jht_dibayar_perusahaan': 0, 'iuran_jp_dibayar_perusahaan': 0, 'iuran_pensiun_dibayar_pegawai': 0, 'iuran_jht_dibayar_pegawai': 0, 'iuran_jp_dibayar_pegawai': 0, 'zakat_via_pemberi_kerja': 0, 'iuran_bpjs_kesehatan_dibayar_pegawai': 0, 'status_ptkp': 'K/1', 'kutipan_status_ptkp': 'udah nikah 1 anak', 'punya_npwp': True, 'bulan_masa_perolehan': 12, 'nilai_per_bulan': False, 'disetahunkan': False, 'neto_pemberi_kerja_sebelumnya': 107383250, 'fasilitas_ikn': False, 'pph_sudah_dipotong': 2219150, 'masa_pajak': 12, 'pph_dipotong_pemberi_kerja_sebelumnya': 2219150}`
- Jawaban: Data yang dihitung: PPh 21 pegawai tetap, masa pajak terakhir; tahun pajak 2024, 12 bulan masa perolehan; masa pajak terakhir Desember; status K/1; ber-NPWP; tunjangan tetap Rp17.115.000; neto pemberi kerja sebelumnya Rp107.383.250; pph sudah dipotong Rp2.219.150; pph dipotong pemberi kerja sebelumn

### ur-17 (hitung, natura)
- Tool harapan: `calculate_taxable_natura`; dipanggil: `['find_legal_basis', 'find_regulation']`
- PPh harapan 0, aktual None
- Jawaban: Belum bisa menghitung PPh 21 dari data yang ada. Informasi yang disebutkan hanya bingkisan Imlek senilai Rp500.000 pada Februari 2024; belum ada keterangan bahwa bingkisan itu diberikan kepada seluruh karyawan. Jika bingkisan diberikan kepada seluruh karyawan sebagai bingkisan hari raya keagamaan, b
