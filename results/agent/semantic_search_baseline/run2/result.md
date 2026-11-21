# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-19T21:06:33. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 40.0% |
| Akurasi ketat satu giliran | 40.0% |
| Token LLM masuk / keluar | 1563463 / 4755 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | - |
| Hitung: tool benar (percobaan pertama) | - |
| Hitung: semua argumen benar | - |
| Hitung: akurasi per field | - |
| Hitung: angka akhir benar | - |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 4 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 6.07 / 19.06 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| graf_relasi | 5 | 40.0% |
| graf_status | 10 | 40.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_graf | 15 | 40.0% |

## Kasus yang salah (9)

### gu-02 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Sudah ada aturan baru. Rujukan yang saya temukan adalah **PMK No. 168 Tahun 2023 Pasal 10 ayat (2)**: biaya jabatan bagi pegawai tetap sebesar 5% dari penghasilan bruto, paling banyak **Rp500.000 sebulan atau Rp6.000.000 setahun**. Saya tidak memiliki rujukan yang memastikan apakah ketentuan dalam a

### gu-03 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'get_article', 'find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Saya belum bisa memastikan apakah **PMK 262/PMK.03/2010 masih berlaku seluruhnya**. Hasil yang tersedia mengonfirmasi isi dan keberlakuan awalnya—peraturan itu mulai berlaku pada 1 Januari 2011—tetapi belum memberikan status terkini atau riwayat perubahan/pencabutannya. Jadi, saya juga belum dapat m

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'search_text']`
- Jawaban: Untuk pegawai harian, upah bruto **sampai dengan Rp450.000 sehari** dikenai PPh 21 **0%**. Jika upah sehari **lebih dari Rp450.000 sampai dengan Rp2.500.000**, PPh 21 dihitung memakai tarif efektif harian (TER). Jika **lebih dari Rp2.500.000 sehari**, dasar hitungnya 50% dari bruto dengan tarif Pasa

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Tidak. PTKP dasar **Rp36 juta setahun** bukan nilai yang dirujuk saat ini. PTKP untuk diri Wajib Pajak orang pribadi adalah **Rp54 juta setahun**. Tambahan **Rp4,5 juta** berlaku untuk Wajib Pajak kawin dan untuk setiap tanggungan yang memenuhi ketentuan, paling banyak tiga orang. Rujukan: **UU PPh 

### gu-06 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: PTKP **Rp24,3 juta setahun** digantikan oleh PTKP yang ditetapkan dalam **PMK No. 101/PMK.010/2016**. Rujukan dasarnya adalah **UU PPh Pasal 7 ayat (1)**. Rujukan yang saya temukan menyebut PTKP diri sendiri sebesar **Rp54 juta setahun**.

### gu-07 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Dari hasil penelusuran yang tersedia, **PMK 137/PMK.03/2005 tidak terlihat dicabut oleh aturan lain**. Pasal penutupnya justru menyatakan bahwa PMK tersebut mencabut PMK 564/KMK.03/2004 dan mulai berlaku pada 1 Januari 2006. Saya belum dapat memastikan aturan yang kemudian mencabut PMK 137/PMK.03/20

### gu-08 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Jika yang dimaksud aturan tahun 2009 tentang makanan dan minuman yang disediakan di tempat kerja, saya tidak memiliki rujukan yang cukup untuk memastikan status aturan tersebut secara khusus. Untuk ketentuan yang berlaku saat ini, makanan/minuman di tempat kerja yang disediakan bagi seluruh pegawai 

### gu-13 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Bentuk bukti potong berdasarkan PER-14/PJ/2013 **bukan lagi acuan yang dipakai untuk bukti potong PPh 21/26 saat ini**. Rujukan terbaru yang saya temukan untuk kode objek dan jenis bukti potong adalah **PER-11/PJ/2025 Lampiran**, yang mencantumkan BPA1, BP21, BP21 final, dan BP26. Saya tidak menemuk

### gu-15 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Saya belum dapat memastikan apakah **PMK 9/PMK.03/2021** masih berlaku. Hasil yang tersedia menunjukkan bahwa peraturan tersebut mengatur insentif pajak bagi wajib pajak terdampak pandemi COVID-19, tetapi tidak memastikan status berlakunya saat ini atau apakah peraturan itu telah dicabut atau digant
