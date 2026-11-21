# Evaluasi agent PPh 21: azure / gpt-6-luna

Waktu: 2026-11-17T15:37:43. Kasus: 22 (galat API tersisa: 0; galat API yang diulang sampai terjawab: 0 pada 0 kasus). Dataset: `taxagent/taxes/pph21/data/kasus_agent_uji_alami.yaml`.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Akurasi keseluruhan (maks. 1 klarifikasi) | 81.8% |
| Akurasi ketat satu giliran | 59.1% |
| Token LLM masuk / keluar | 1430966 / 12752 |
| Kasus hitung yang bertanya balik padahal data lengkap | 5 |
| Hitung: tool benar (akhir) | 100.0% |
| Hitung: tool benar (percobaan pertama) | 100.0% |
| Hitung: semua argumen benar | 100.0% |
| Hitung: akurasi per field | 100.0% |
| Hitung: angka akhir benar | 100.0% |
| Tanya balik benar | 80.0% |
| Tolak (di luar cakupan) benar | - |
| Info (cari dasar hukum) benar | 75.0% |
| Total galat tool | 0 |
| Kasus dengan tool halusinasi | 0 |
| Rata-rata putaran / detik | 3.55 / 18.4 |

## Per kategori

| Kategori | n | Benar |
|---|---|---|
| bukan_pegawai | 3 | 100.0% |
| final | 1 | 100.0% |
| info | 12 | 75.0% |
| pegawai_tetap_bulanan | 1 | 100.0% |
| tanya_balik | 5 | 80.0% |

## Per tag

| Tag | n | Benar |
|---|---|---|
| uji_alami | 22 | 81.8% |

## Kasus yang salah (4)

### al-06 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis']`
- Jawaban: Kalau di soal **tidak mencantumkan iuran pensiun**, jangan mengada-adakan nominalnya—anggap **tidak ada atau Rp0**, kecuali ada keterangan lain. **Biaya jabatan berbeda:** untuk karyawan swasta yang berstatus pegawai tetap, biaya jabatan umumnya tetap menjadi pengurang dalam perhitungan PPh 21, mesk

### al-22 (tanya_balik, tanya_balik)
- Tool harapan: `None`; dipanggil: `['lookup_ptkp', 'calculate_pph21_non_permanent']`
- Jawaban: Data yang dihitung: PPh 21 pegawai tidak tetap; tahun pajak 2026; status K/2; ber-NPWP; upah per periode Rp9.130.000; skema: bulanan; 1 hari; penghasilan bruto yang dihitung Rp9.130.000. Untuk data tersebut, tarif yang dipakai **1%**, sehingga PPh 21 terutang **Rp91.300**. Jadi, potongan **1,75%** t

### al-25 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_legal_basis', 'find_legal_basis', 'find_legal_basis']`
- Jawaban: Selamat sore. Untuk **pegawai tetap berstatus PKWT**, sepanjang perlakuan pajaknya sebagai pegawai tetap: - **Desember atau masa pajak terakhir:** PPh 21 dihitung ulang menggunakan **tarif Pasal 17**, lalu dikurangi PPh 21 yang telah dipotong pada masa sebelumnya. Jadi, bukan sekadar menerapkan TER 

### al-26 (info, info)
- Tool harapan: `find_legal_basis`; dipanggil: `['find_regulation', 'search_text', 'find_regulation', 'search_text', 'amendment_chain']`
- Jawaban: Om Pimpa, **untuk uang pesangon dan manfaat pensiun/THT/JHT yang dibayarkan sekaligus, acuannya masih PP 68/2009**—peraturan itu berstatus **berlaku** pada tanggal 17 November 2026. Ketentuan tarif khususnya tercantum di [PP 68 Tahun 2009 Pasal 4, halaman PDF tidak dicantumkan](https://jdih.kemenkeu
