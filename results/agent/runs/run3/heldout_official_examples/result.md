# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:30:45. Kasus: 19 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_resmi.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 89.5% |
| Akurasi ketat satu giliran | 84.2% |
| Token LLM masuk / keluar | 896569 / 9303 |
| Kasus hitung yang bertanya balik padahal data lengkap | 2 |
| Hitung: tool benar (akhir) | 94.7% |
| Hitung: tool benar (percobaan pertama) | 94.7% |
| Hitung: semua argumen benar | 79.0% |
| Hitung: akurasi per field | 95.6% |
| Hitung: angka akhir benar | 89.5% |
| Tanya balik benar | - |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | - |
| Total galat tool | 1 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.74 / 12.66 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 1 | 100.0% |
| natura | 5 | 100.0% |
| pegawai_tetap_bulanan | 5 | 80.0% |
| pegawai_tetap_masa_terakhir | 3 | 66.7% |
| pegawai_tidak_tetap | 3 | 100.0% |
| pensiunan | 1 | 100.0% |
| pph26 | 1 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 2 | 50.0% |
| uji_resmi | 19 | 89.5% |

## Kasus yang salah (2)

### ur-02 (hitung, pegawai_tetap_bulanan)
- Tool harapan: `calculate_pph21_permanent_monthly`; dipanggil: `['lookup_ptkp', 'calculate_pph21_permanent_monthly']`
- Argumen `gaji_pokok`: harapan `30000000`, aktual `2000`
- PPh harapan 3300000, aktual 0
- Argumen dikirim: `{'tahun_pajak': 2024, 'gaji_pokok': 2000, 'status_ptkp': 'K/3', 'kutipan_status_ptkp': 'nikah anak 3', 'punya_npwp': True, 'masa_pajak': 1}`
- Jawaban: Data yang dihitung: PPh 21 pegawai tetap, satu masa pajak (TER); masa pajak Januari 2024; status K/3; ber-NPWP; gaji pokok Rp2.000; penghasilan bruto yang dihitung Rp2.000. **PPh 21 yang terhitung: Rp0.** Namun, angka ini memakai gaji pokok Rp2.000 karena nilai gaji dalam USD dan kurs yang Anda beri

### ur-06 (hitung, pegawai_tetap_masa_terakhir)
- Tool harapan: `calculate_pph21_permanent_last_period`; dipanggil: `['lookup_ptkp', 'calculate_pph21_final', 'find_legal_basis', 'calculate_pph21_final']`
- PPh harapan 619065, aktual None
- Jawaban: Data yang dihitung: PPh 21 final; tahun pajak 2024; ber-NPWP; jenis: honorarium_pns; jumlah bruto Rp12.017.000; golongan: III; penghasilan bruto yang dihitung Rp12.017.000. **PPh 21 final atas komponen gaji ke-13/14 yang disebutkan adalah Rp600.850.** | Rincian | Nilai | |---|---:| | Jumlah bruto ya
