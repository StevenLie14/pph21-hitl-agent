# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T14:22:40. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 1 pada 1 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 80.0% |
| Akurasi ketat satu giliran | 80.0% |
| Token LLM masuk / keluar | 1183127 / 4001 |
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
| Rata-rata putaran / detik | 4.4 / 17.28 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| graf_relasi | 5 | 80.0% |
| graf_status | 10 | 80.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_graf | 15 | 80.0% |

## Kasus yang salah (3)

### gu-02 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Biaya jabatan **masih sebesar 5% dari penghasilan bruto, maksimal Rp500.000 sebulan atau Rp6.000.000 setahun**. Rujukan yang lebih baru untuk ketentuan ini adalah [PMK No. 168 Tahun 2023 Pasal 10 ayat (2), hlm. 11](https://jdih.kemenkeu.go.id/api/download/E60A82E0-B218-40F5-9D18-B924AA1E11CE/2023pmk

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_regulation', 'search_text', 'find_regulation', 'get_article', 'get_article', 'get_article', 'search_text', 'find_legal_basis']`
- Jawaban: Ya, ketentuan lama yang memakai batas **Rp450.000 per hari** dan batas kumulatif **Rp4.500.000 per bulan** sudah berbeda dengan aturan yang berlaku sekarang. Untuk pegawai tidak tetap yang dibayar harian, mingguan, satuan, atau borongan, aturan yang berlaku sekarang menggunakan **upah sehari atau ra

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'skill_value']`
- Jawaban: Tidak. **PTKP untuk diri Wajib Pajak orang pribadi saat ini Rp54.000.000 setahun**, bukan Rp36.000.000. Rujukan: [PMK No. 101/PMK.010/2016](https://jdih.kemenkeu.go.id/dok/101-pmk-010-2016); ketentuan terkait juga tercantum dalam UU PPh Pasal 7 ayat (1).
