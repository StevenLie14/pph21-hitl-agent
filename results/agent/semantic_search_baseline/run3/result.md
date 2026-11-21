# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-19T21:11:16. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 40.0% |
| Akurasi ketat satu giliran | 40.0% |
| Token LLM masuk / keluar | 1671217 / 5009 |
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
| Rata-rata putaran / detik | 6.47 / 18.69 |

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
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Masih berlaku ketentuan **biaya jabatan sebesar 5% dari penghasilan bruto, maksimal Rp500.000 sebulan atau Rp6.000.000 setahun**. Rujukan yang tersedia untuk ketentuan tersebut adalah [PMK No. 168 Tahun 2023 Pasal 10 ayat (2)]. Jadi, untuk ketentuan ini rujukannya sudah ada di PMK No. 168 Tahun 2023

### gu-03 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'get_article', 'find_legal_basis', 'find_legal_basis', 'get_article', 'get_article', 'find_legal_basis']`
- Jawaban: Saya belum bisa memastikan apakah **PMK 262/PMK.03/2010 masih berlaku seluruhnya**. Hasil rujukan yang tersedia belum memuat status keberlakuan atau aturan yang mencabut/mengubah PMK tersebut. Yang dapat saya pastikan dari rujukan yang sudah diperoleh: **PP No. 80 Tahun 2010 Pasal 4 ayat (2)** menga

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'search_text']`
- Jawaban: Aturan yang dulu berlaku telah diperbarui. Untuk pegawai harian, batas agar PPh 21 terutang **0%** adalah upah bruto **sampai dengan Rp450.000 sehari**. Jika upah harian melebihi batas itu, pemotongan mengikuti tarif efektif harian; sedangkan jika upah sehari **lebih dari Rp2.500.000**, digunakan ta

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Tidak. PTKP dasar untuk diri Wajib Pajak orang pribadi adalah **Rp54.000.000 setahun**. Angka **Rp36.000.000 setahun** bukan PTKP dasar yang dirujuk di sini. Rujukan: UU PPh Pasal 7 ayat (1) dan PMK No. 101/PMK.010/2016.

### gu-06 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Rujukan yang saya temukan menyebut PTKP untuk diri wajib pajak orang pribadi sebesar Rp54 juta setahun, bukan Rp24,3 juta. Rujukannya adalah **UU PPh Pasal 7 ayat (1)** dan **PMK No. 101/PMK.010/2016**. Namun, hasil pencarian ini tidak menjelaskan aturan yang mencabut angka Rp24,3 juta secara spesif

### gu-07 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'get_article', 'get_article', 'find_legal_basis', 'search_text', 'report_possibly_stale', 'find_legal_basis']`
- Jawaban: Dari hasil yang tersedia, **belum dapat dipastikan peraturan apa yang mencabut PMK 137/PMK.03/2005**. Pencarian yang ada hanya menunjukkan bahwa PMK tersebut mencabut PMK 564/KMK.03/2004—bukan aturan yang mencabut PMK 137/PMK.03/2005. Rujukan PTKP yang ditemukan menyebut **PMK No. 101/PMK.010/2016**

### gu-08 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Kalau yang dimaksud aturan tahun 2009 tentang makanan dan minuman yang disediakan kantor bagi seluruh pegawai, saya tidak punya rujukan di hasil pencarian untuk memastikan apakah aturan tahun 2009 itu masih berlaku. Rujukan yang saya temukan untuk perlakuan saat ini menyebut bahwa makanan/minuman ya

### gu-09 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis']`
- Jawaban: Rujukan yang saya temukan untuk PPh final atas uang pesangon adalah **PP No. 68 Tahun 2009 Pasal 4** dan **PMK No. 16/PMK.03/2010**. Hasil rujukan tersebut tidak mencantumkan PP tahun 2000, jadi saya belum bisa memastikan apakah aturan PP tahun 2000 yang Anda maksud masih berlaku atau sudah digantik

### gu-15 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'search_text', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Saya belum bisa memastikan apakah **PMK 9/PMK.03/2021 masih berlaku saat ini**. Hasil rujukan yang tersedia belum memuat status keberlakuan atau aturan yang mencabut/mengubah PMK tersebut secara menyeluruh. Yang dapat dipastikan dari hasil yang ada: PMK itu mengatur insentif pajak bagi wajib pajak t
