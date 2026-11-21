# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:46:04. Kasus: 15 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_graf.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 66.7% |
| Akurasi ketat satu giliran | 66.7% |
| Token LLM masuk / keluar | 1169700 / 4586 |
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
| Rata-rata putaran / detik | 4.4 / 16.69 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| graf_relasi | 5 | 80.0% |
| graf_status | 10 | 60.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_graf | 15 | 66.7% |

## Kasus yang salah (5)

### gu-02 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_regulation']`
- Jawaban: Masih berlaku. Rujukan yang tersedia saat ini adalah PMK 168 Tahun 2023 Pasal 10 ayat (2): biaya jabatan sebesar 5% dari penghasilan bruto, paling banyak Rp500.000 sebulan atau Rp6.000.000 setahun. PMK tersebut berstatus **berlaku** pada tanggal pemeriksaan. [PMK 168 Tahun 2023 Pasal 10 ayat (2), hl

### gu-04 (graf, graf_relasi)
- Tool harapan: `None`; dipanggil: `['find_legal_basis']`
- Jawaban: Batas upah harian yang dikenai **PPh 21 sebesar 0% adalah sampai dengan Rp450.000 per hari**. Dasarnya: [PMK 168/2023 Pasal 12 ayat (2), hlm. 13](https://jdih.kemenkeu.go.id/api/download/E60A82E0-B218-40F5-9D18-B924AA1E11CE/2023pmkeuangan168.pdf#page=13). Ketentuan terkait pegawai tidak tetap juga d

### gu-05 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'find_regulation']`
- Jawaban: Tidak. **PTKP dasar untuk diri Wajib Pajak orang pribadi adalah Rp54.000.000 setahun**, bukan Rp36.000.000. PMK 101 Tahun 2016 berstatus **berlaku** per 17 November 2026. Untuk status kawin atau tanggungan, PTKP dapat bertambah sesuai ketentuan. Dasar: UU PPh Pasal 7 ayat (1) dan [PMK 101 Tahun 2016

### gu-08 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_regulation', 'report_possibly_stale', 'search_text', 'find_regulation']`
- Jawaban: Ya. Jika yang Anda maksud **PER-51/PJ/2009**, peraturan itu tercatat **berlaku per 17 November 2026**. Namun, untuk ketentuan bahwa makanan/minuman yang disediakan kantor bagi seluruh pegawai dikecualikan dari objek PPh, rujukan yang ditemukan juga ada di **PMK 66 Tahun 2023 Pasal 4 huruf a dan Pasa

### gu-09 (graf, graf_status)
- Tool harapan: `None`; dipanggil: `['find_regulation', 'find_legal_basis', 'find_regulation']`
- Jawaban: Jika yang Anda maksud **PP 68 Tahun 2000**, hasil penelusuran menunjukkan peraturan itu **berstatus berlaku** per 17 November 2026, tetapi tidak tersedia teksnya di sumber yang saya akses. Untuk aturan pemotongan PPh 21 atas pesangon, rujukan yang ditemukan adalah [PP 68 Tahun 2009 Pasal 4](https://
