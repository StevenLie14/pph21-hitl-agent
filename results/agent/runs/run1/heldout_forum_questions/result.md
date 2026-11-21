# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T12:55:12. Kasus: 22 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_alami.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 68.2% |
| Akurasi ketat satu giliran | 54.5% |
| Token LLM masuk / keluar | 1471711 / 12742 |
| Kasus hitung yang bertanya balik padahal data lengkap | 5 |
| Hitung: tool benar (akhir) | 60.0% |
| Hitung: tool benar (percobaan pertama) | 80.0% |
| Hitung: semua argumen benar | 80.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 80.0% |
| Tanya balik benar | 80.0% |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | 66.7% |
| Total galat tool | 1 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.64 / 14.54 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 3 | 66.7% |
| final | 1 | 100.0% |
| info | 12 | 66.7% |
| pegawai_tetap_bulanan | 1 | 0.0% |
| tanya_balik | 5 | 80.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_alami | 22 | 68.2% |

## Kasus yang salah (7)

### al-06 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis']`
- Jawaban: Kalau soal **tidak mencantumkan iuran pensiun**, jangan mengada-adakan angkanya—biasanya dianggap **tidak ada atau Rp0**, kecuali ada keterangan lain. **Biaya jabatan berbeda:** untuk karyawan, biaya jabatan merupakan pengurang yang diperhitungkan dalam penghitungan PPh 21, meskipun soal tidak menul

### al-16 (hitung, bukan_pegawai)
- Tool harapan: `calculate_pph21_non_employee`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- PPh harapan 16500000, aktual None
- Jawaban: Belum bisa saya hitung dengan informasi yang ada. “Pakai default” tidak menentukan **status Anisa** (orang pribadi atau badan usaha) maupun **jenis hubungan dan dasar pembayaran komisi**. Hal-hal itu menentukan apakah pembayaran masuk PPh 21 bukan pegawai atau perlakuan pajak lainnya. Saya juga tida

### al-17 (hitung, pegawai_tetap_bulanan)
- Tool harapan: `calculate_pph21_permanent_monthly`; dipanggil: `['find_legal_basis', 'search_faq', 'lookup_ptkp', 'calculate_pph21_permanent_monthly', 'calculate_pph21_permanent_last_period', 'calculate_pph21_permanent_last_period']`
- PPh harapan 2160000, aktual 2160000
- Argumen dikirim: `{'tahun_pajak': 2024, 'gaji_pokok': 4000000, 'bonus_thr_komisi': 20000000, 'status_ptkp': 'TK/0', 'kutipan_status_ptkp': 'TK/0', 'masa_pajak': 6}`
- Jawaban: **Data yang dihitung:** PPh 21 pegawai tetap, satu masa pajak (TER); masa pajak Juni 2024; status TK/0; ber-NPWP; gaji pokok Rp4.000.000; bonus thr komisi Rp20.000.000; penghasilan bruto yang dihitung Rp24.000.000. Pada contoh itu, **PPh 21 bulan bonus adalah Rp2.160.000**. | Langkah | Hasil | |---|

### al-19 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Secara umum, **THR tidak dihitung terpisah dari gaji**. Pada bulan THR dibayarkan, gaji, lembur, dan THR menjadi penghasilan bruto pada bulan itu untuk menghitung pemotongan PPh 21. Untuk pegawai tetap, bulan seperti Maret menggunakan **tarif efektif rata-rata (TER)** atas penghasilan bruto bulan te

### al-22 (tanya_balik, tanya_balik)
- Tool harapan: `None`; dipanggil: `['lookup_ptkp', 'calculate_pph21_non_permanent']`
- Jawaban: Data yang dihitung: PPh 21 pegawai tidak tetap; tahun pajak 2026; status K/2; ber-NPWP; upah per periode Rp9.130.000; skema: bulanan; 1 hari; penghasilan bruto yang dihitung Rp9.130.000. Dengan asumsi Anda dibayar secara bulanan sebagai pegawai tidak tetap, PPh 21 terutang adalah **Rp91.300**. Tarif

### al-25 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'search_text']`
- Jawaban: Selamat sore. Untuk **pegawai PKWT yang diperlakukan sebagai pegawai tetap dalam pemotongan PPh 21**, jawabannya: 1. **Desember menggunakan tarif Pasal 17**, bukan TER bulanan. Desember merupakan masa pajak terakhir: pajak dihitung kembali atas penghasilan selama tahun atau bagian tahun, lalu dikura

### al-26 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_regulation', 'find_regulation', 'search_text']`
- Jawaban: Om Pimpa, **untuk pemotongan PPh Pasal 21 atas pesangon atau santunan/manfaat hari tua yang dibayarkan sekaligus, PP 68/2009 masih berstatus berlaku** pada tanggal pengecekan ini. Jadi, UU HPP bukan berarti PP 68/2009 otomatis tidak lagi digunakan. Rujukan yang ditemukan juga mencantumkan **PMK 16 T
