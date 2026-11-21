# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T13:02:02. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 73.3% |
| Akurasi ketat satu giliran | 73.3% |
| Token LLM masuk / keluar | 1127324 / 4416 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | - |
| Hitung: tool benar (percobaan pertama) | - |
| Hitung: semua argumen benar | - |
| Hitung: akurasi per field | - |
| Hitung: angka akhir benar | - |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 2 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 4.2 / 14.42 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| graf_relasi | 5 | 80.0% |
| graf_status | 10 | 70.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_graf | 15 | 73.3% |

## Kasus yang salah (4)

### gu-02 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_regulation']`
- Jawaban: Masih berlaku, tetapi **sudah ada aturan yang lebih baru daripada aturan tahun 2008**: ketentuan biaya jabatan saat ini dirujuk dalam **PMK 168 Tahun 2023 Pasal 10 ayat (2)**. Besarnya tetap 5% dari penghasilan bruto pegawai tetap, paling banyak Rp500.000 sebulan atau Rp6.000.000 setahun. [PMK 168/2

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Batas upah harian yang dikenai PPh 21 sebesar **Rp450.000 per hari**: upah harian sampai jumlah itu dikenai tarif **0%**. Penghitungan didasarkan pada upah sehari (atau rata-rata upah sehari untuk periode pembayaran), bukan akumulasi pembayaran dalam bulan yang sama. Aturan yang dirujuk sekarang ada

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_regulation']`
- Jawaban: Ya, **PTKP Rp36 juta setahun masih berlaku hanya sebagai nilai dasar untuk wajib pajak lajang tanpa tanggungan pada ketentuan lama—bukan nilai PTKP yang berlaku sekarang**. Rujukan yang tersedia menyatakan PTKP dasar saat ini **Rp54 juta setahun**. [PMK 101 Tahun 2016](https://jdih.kemenkeu.go.id/do

### gu-08 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_regulation', 'amendment_chain', 'search_text', 'find_regulation']`
- Jawaban: Tidak. Jika yang Anda maksud **PER-31/PJ/2009**, peraturan itu **dicabut sejak 1 Januari 2013** oleh PER-31/PJ/2012. PER-31/PJ/2012 kemudian dicabut oleh PER-32/PJ/2015. Untuk **makanan dan minuman yang disediakan kantor di tempat kerja bagi seluruh pegawai**, ketentuan yang berlaku saat ini menyebu
