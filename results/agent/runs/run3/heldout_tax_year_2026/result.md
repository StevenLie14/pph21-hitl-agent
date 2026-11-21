# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:41:43. Kasus: 14 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_2026.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 85.7% |
| Akurasi ketat satu giliran | 85.7% |
| Token LLM masuk / keluar | 921454 / 6171 |
| Kasus hitung yang bertanya balik padahal data lengkap | 1 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 77.8% |
| Hitung: akurasi per field | 93.3% |
| Hitung: angka akhir benar | 88.9% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | 80.0% |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 7 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.71 / 15.87 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 100.0% |
| dewan_komisaris | 1 | 100.0% |
| final | 1 | 100.0% |
| pegawai_tetap_bulanan | 2 | 100.0% |
| pegawai_tetap_masa_terakhir | 1 | 100.0% |
| pegawai_tidak_tetap | 1 | 100.0% |
| pensiunan | 1 | 0.0% |
| pph26 | 1 | 100.0% |
| tolak | 5 | 80.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_2026 | 14 | 85.7% |

## Kasus yang salah (2)

### t26-06 (hitung, pensiunan)
- Tool harapan: `calculate_pph21_pensioner_monthly`; dipanggil: `['lookup_ptkp', 'lookup_ptkp', 'find_legal_basis', 'calculate_pph21_pensioner_monthly']`
- Argumen `status_ptkp`: harapan `K/2`, aktual `K/0`
- PPh harapan 0, aktual None
- Argumen dikirim: `{'tahun_pajak': 2026, 'uang_pensiun': 6000000, 'status_ptkp': 'K/0', 'kutipan_status_ptkp': 'ibu masih ada, 2 adik sy masih sekolah ditanggung bapak', 'punya_npwp': True, 'masa_pajak': 6, 'penghasilan_lain': 0}`
- Jawaban: Saya belum bisa menghitung dengan “default” untuk status PTKP, karena status kawin dan tanggungan Bapak belum disebutkan secara pasti. Informasi bahwa Ibu masih ada dan dua adik ditanggung Bapak belum memastikan kode PTKP. Mohon sebutkan **kode PTKP Bapak** (misalnya K/0 atau K/2), atau status kawin

### t26-14 (tolak, tolak)
- Tool harapan: `None`; dipanggil: `['find_legal_basis', 'calculate_pph21_final', 'find_legal_basis']`
- Jawaban: Maaf, jawaban sebelumnya memakai kategori pajak yang keliru: omzet warung bukan pesangon dan bukan PPh Pasal 21. Saya tidak punya kalkulator PPh UMKM untuk memastikan pajak Anda. Perhitungan juga dapat bergantung pada jenis usaha dan apakah omzet memenuhi ketentuan skema UMKM. Agar saya bisa mengara
