# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:11:04. Kasus: 47 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 97.9% |
| Akurasi ketat satu giliran | 97.9% |
| Token LLM masuk / keluar | 1738031 / 20346 |
| Kasus hitung yang bertanya balik padahal data lengkap | 0 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 100.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 100.0% |
| Tanya balik benar | 100.0% |
| Tolak (di luar cakupan) benar | 100.0% |
| Info (cari dasar hukum) benar | 50.0% |
| Total galat tool | 1 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 2.15 / 10.03 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 4 | 100.0% |
| dewan_komisaris | 2 | 100.0% |
| final | 3 | 100.0% |
| info | 2 | 50.0% |
| pasal17_langsung | 3 | 100.0% |
| pegawai_tetap_bulanan | 8 | 100.0% |
| pegawai_tetap_masa_terakhir | 5 | 100.0% |
| pegawai_tetap_tahunan | 2 | 100.0% |
| pegawai_tidak_tetap | 4 | 100.0% |
| pensiunan | 5 | 100.0% |
| pph26 | 2 | 100.0% |
| tanya_balik | 4 | 100.0% |
| tolak | 3 | 100.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| butuh_aritmetika | 2 | 100.0% |
| resmi | 23 | 100.0% |

## Kasus yang salah (1)

### inf-02 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis']`
- Jawaban: Tidak. Honorarium dokter praktik sebagai **bukan pegawai** dihitung untuk masa pajak yang bersangkutan, **bukan secara kumulatif lintas masa pajak**. Dasar pengenaan pajaknya adalah **50% dari penghasilan bruto masa pajak tersebut**, lalu dikenakan tarif Pasal 17. PTKP tidak digunakan. Dasar hukum: 
