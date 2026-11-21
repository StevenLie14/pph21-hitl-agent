# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-19T21:01:45. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 13.3% |
| Akurasi ketat satu giliran | 13.3% |
| Token LLM masuk / keluar | 1246450 / 3921 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | - |
| Hitung: tool benar (percobaan pertama) | - |
| Hitung: semua argumen benar | - |
| Hitung: akurasi per field | - |
| Hitung: angka akhir benar | - |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 3 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 4.93 / 14.92 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| graf_relasi | 5 | 20.0% |
| graf_status | 10 | 10.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_graf | 15 | 13.3% |

## Kasus yang salah (13)

### gu-01 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Tidak, juklak pemotongan PPh 21 dari tahun 2008 bukan rujukan yang sebaiknya dipakai untuk pemotongan karyawan saat ini. Untuk pegawai tetap, sejak masa pajak Januari 2024, pemotongan pada masa selain masa pajak terakhir menggunakan TER. Pada masa pajak terakhir, PPh dihitung ulang dengan tarif Pasa

### gu-02 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Ya, ketentuan biaya jabatan sebesar 5% dari penghasilan bruto dengan batas maksimum Rp500.000 sebulan atau Rp6.000.000 setahun masih berlaku. Rujukan yang saya temukan adalah PMK No. 168 Tahun 2023 Pasal 10 ayat (2), bukan aturan tahun 2008. **Asumsi yang dipakai** - Pertanyaan Anda merujuk pada bia

### gu-03 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'get_article']`
- Jawaban: Tidak semuanya masih berlaku. Yang dapat dipastikan dari rujukan yang tersedia: [PMK 168 Tahun 2023 Pasal 24, hlm. 22](https://jdih.kemenkeu.go.id/api/download/E60A82E0-B218-40F5-9D18-B924AA1E11CE/2023pmkeuangan168.pdf#page=22) mencabut bagian tertentu dari PMK 262/PMK.03/2010, yaitu Pasal 5, Pasal 

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'search_text', 'find_legal_basis']`
- Jawaban: Aturan **tahun 2015** sudah digantikan oleh **PP No. 58 Tahun 2023** dan **PMK No. 168 Tahun 2023**. Untuk pegawai harian, upah **sampai dengan Rp450.000 sehari** dikenakan PPh 21 **0%**. Jika upah sehari melebihi Rp450.000, pemotongan mengikuti tarif efektif harian; bila melebihi Rp2.500.000 sehari

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Tidak. PTKP untuk diri Wajib Pajak orang pribadi adalah **Rp54.000.000 setahun**, bukan Rp36.000.000. Tambahan PTKP adalah **Rp4.500.000** untuk Wajib Pajak yang kawin dan **Rp4.500.000 per tanggungan yang memenuhi ketentuan**, paling banyak tiga orang. Rujukan: **UU PPh Pasal 7 ayat (1)** dan **PMK

### gu-06 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Rujukan yang saya temukan untuk PTKP adalah **UU PPh Pasal 7 ayat (1)** dan **PMK No. 101/PMK.010/2016**. Hasil pencarian menyebut PTKP diri sendiri **Rp54.000.000 setahun**, bukan Rp24.300.000. Namun, hasil tersebut tidak menyebut aturan yang secara khusus mencabut ketentuan PTKP Rp24.300.000. Jadi

### gu-07 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Saya tidak menemukan rujukan yang memastikan peraturan mana secara khusus mencabut PMK 137/PMK.03/2005. Rujukan PTKP yang tersedia bagi saya menyebut UU PPh Pasal 7 ayat (1) dan PMK No. 101/PMK.010/2016, tetapi tidak menjelaskan hubungan pencabutan dengan PMK yang Anda tanyakan. Saya tidak punya ruj

### gu-08 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Kalau yang dimaksud aturan lama tahun 2009 tentang makan dan minum yang disediakan di tempat kerja untuk seluruh pegawai, saya belum menemukan rujukan yang memastikan status aturan tahun 2009 itu sendiri. Rujukan yang tersedia saat ini adalah **UU HPP, PP No. 55 Tahun 2022, dan PMK No. 66 Tahun 2023

### gu-09 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Rujukan yang saya temukan untuk PPh final atas uang pesangon adalah **PP No. 68 Tahun 2009 Pasal 4** dan **PMK No. 16/PMK.03/2010**. Namun, hasil rujukan ini tidak memastikan apakah aturan tersebut masih berlaku saat ini, dan tidak mencantumkan PP tahun 2000. Jadi, saya belum bisa memastikan bahwa a

### gu-10 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: KMK 112/KMK.03/2001 tidak tercantum dalam rujukan yang tersedia, jadi saya tidak dapat memastikan secara langsung aturan yang mencabut atau menggantikannya. Untuk PPh final atas uang pesangon, rujukan yang tersedia adalah **PP No. 68 Tahun 2009 Pasal 4** dan **PMK No. 16/PMK.03/2010**. Namun, hasil 

### gu-12 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'report_possibly_stale', 'search_text', 'get_article']`
- Jawaban: Saya **tidak dapat memastikan dari rujukan yang ditemukan apakah PER-32/PJ/2015 telah dicabut secara formal**. Namun, sebagai pedoman penghitungan PPh 21 saat ini, jangan mengandalkannya tanpa mencocokkan ketentuannya dengan aturan yang lebih baru: ketentuan pemotongan PPh 21 kini dirujuk dalam [PMK

### gu-13 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Bentuk bukti potong yang diatur dalam **PER-14/PJ/2013 tidak lagi menjadi acuan bentuk yang dipakai saat ini**. Rujukan yang tersedia untuk kode objek pajak bukti potong sekarang adalah **PER-11/PJ/2025 Lampiran (Daftar Kode Objek Pajak dan Objek Pajak)**. Untuk memastikan bentuk/formulir spesifik y

### gu-15 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Saya belum bisa memastikan apakah **PMK 9/PMK.03/2021** masih berlaku. Hasil rujukan yang tersedia tidak membahas peraturan tersebut atau insentif pajak COVID-19 secara khusus, jadi status berlakunya belum sempat saya cek.
