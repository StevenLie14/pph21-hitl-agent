# Evaluasi pemantau: lengan aturan vs LLM vs hibrida

- model: azure:gpt-6-luna
- prompt: v1-2026-10-06
- ulangan: 3
- batas per set: semua
- jawaban LLM tidak valid (masuk review, gagal aman): 0
- catatan: aturan = classifier v2 sekarang (in-sample di pajakgoid); prompt LLM tidak disetel dari set uji
- prompt teks: teks-v1-2026-10-06
- prompt teks kata kunci: teks-v2-kata-kunci-2026-10-19
- ulangan teks: 3
- cakupan teks per set: {'kurasi': '22/22', 'feed': '97/98', 'pajakgoid': '1214/1214'}
- sumber teks per set (JDIH dulu): {'kurasi': {'jdih': 19, 'pajak.go.id': 3}, 'feed': {'jdih': 82, 'jdih (perlu_dicek)': 15}, 'pajakgoid': {'pajak.go.id': 957, 'jdih': 200, 'pajak.go.id (perlu_dicek)': 57}}
- catatan teks: item tanpa teks memakai lengan judul; kandidat pelabelan pajakgoid = ditandai aturan ATAU teks menyebut Pasal 21, jadi teks_pasal21 diuntungkan

## Biner (perlu ditinjau atau tidak), CI95 Wilson

| set | lengan | ditandai | TP | FP | FN | presisi [CI95] | recall [CI95] | F1 |
|---|---|---|---|---|---|---|---|---|
| kurasi | aturan | 16 | 16 | 0 | 0 | 100.0% [81-100%] | 100.0% [81-100%] | 100.0% |
| kurasi | llm | 15 | 15 | 0 | 1 | 100.0% [80-100%] | 93.8% [72-99%] | 96.8% |
| kurasi | hibrida | 16 | 16 | 0 | 0 | 100.0% [81-100%] | 100.0% [81-100%] | 100.0% |
| kurasi | teks_pasal21 | 16 | 14 | 2 | 2 | 87.5% [64-97%] | 87.5% [64-97%] | 87.5% |
| kurasi | llm_teks | 17 | 16 | 1 | 0 | 94.1% [73-99%] | 100.0% [81-100%] | 97.0% |
| kurasi | aturan+llm_teks | 17 | 16 | 1 | 0 | 94.1% [73-99%] | 100.0% [81-100%] | 97.0% |
| kurasi | llm_teks_kunci | 17 | 16 | 1 | 0 | 94.1% [73-99%] | 100.0% [81-100%] | 97.0% |
| kurasi | aturan+llm_teks_kunci | 17 | 16 | 1 | 0 | 94.1% [73-99%] | 100.0% [81-100%] | 97.0% |
| feed | aturan | 0 | 0 | 0 | 0 | - [0-0%] | - [0-0%] | - |
| feed | llm | 0 | 0 | 0 | 0 | - [0-0%] | - [0-0%] | - |
| feed | hibrida | 0 | 0 | 0 | 0 | - [0-0%] | - [0-0%] | - |
| feed | teks_pasal21 | 18 | 0 | 18 | 0 | 0.0% [0-18%] | - [0-0%] | - |
| feed | llm_teks | 1 | 0 | 1 | 0 | 0.0% [0-79%] | - [0-0%] | - |
| feed | aturan+llm_teks | 1 | 0 | 1 | 0 | 0.0% [0-79%] | - [0-0%] | - |
| feed | llm_teks_kunci | 1 | 0 | 1 | 0 | 0.0% [0-79%] | - [0-0%] | - |
| feed | aturan+llm_teks_kunci | 1 | 0 | 1 | 0 | 0.0% [0-79%] | - [0-0%] | - |
| pajakgoid | aturan | 81 | 36 | 45 | 5 | 44.4% [34-55%] | 87.8% [74-95%] | 59.0% |
| pajakgoid | llm | 63 | 33 | 30 | 8 | 52.4% [40-64%] | 80.5% [66-90%] | 63.5% |
| pajakgoid | hibrida | 96 | 38 | 58 | 3 | 39.6% [30-50%] | 92.7% [81-97%] | 55.5% |
| pajakgoid | teks_pasal21 | 159 | 33 | 126 | 8 | 20.8% [15-28%] | 80.5% [66-90%] | 33.0% |
| pajakgoid | llm_teks | 84 | 38 | 46 | 3 | 45.2% [35-56%] | 92.7% [81-97%] | 60.8% |
| pajakgoid | aturan+llm_teks | 114 | 40 | 74 | 1 | 35.1% [27-44%] | 97.6% [87-100%] | 51.6% |
| pajakgoid | llm_teks_kunci | 89 | 40 | 49 | 1 | 44.9% [35-55%] | 97.6% [87-100%] | 61.5% |
| pajakgoid | aturan+llm_teks_kunci | 115 | 40 | 75 | 1 | 34.8% [27-44%] | 97.6% [87-100%] | 51.3% |

## McNemar eksak (kebenaran biner berpasangan)

| set | A | B | hanya A benar | hanya B benar | p |
|---|---|---|---|---|---|
| kurasi | aturan | llm | 1 | 0 | 1.0000 |
| kurasi | aturan | hibrida | 0 | 0 | 1.0000 |
| kurasi | aturan | teks_pasal21 | 4 | 0 | 0.1250 |
| kurasi | aturan | llm_teks | 1 | 0 | 1.0000 |
| kurasi | aturan | aturan+llm_teks | 1 | 0 | 1.0000 |
| kurasi | aturan | llm_teks_kunci | 1 | 0 | 1.0000 |
| kurasi | aturan | aturan+llm_teks_kunci | 1 | 0 | 1.0000 |
| kurasi | llm | hibrida | 0 | 1 | 1.0000 |
| kurasi | llm | teks_pasal21 | 4 | 1 | 0.3750 |
| kurasi | llm | llm_teks | 1 | 1 | 1.0000 |
| kurasi | llm | aturan+llm_teks | 1 | 1 | 1.0000 |
| kurasi | llm | llm_teks_kunci | 1 | 1 | 1.0000 |
| kurasi | llm | aturan+llm_teks_kunci | 1 | 1 | 1.0000 |
| kurasi | hibrida | teks_pasal21 | 4 | 0 | 0.1250 |
| kurasi | hibrida | llm_teks | 1 | 0 | 1.0000 |
| kurasi | hibrida | aturan+llm_teks | 1 | 0 | 1.0000 |
| kurasi | hibrida | llm_teks_kunci | 1 | 0 | 1.0000 |
| kurasi | hibrida | aturan+llm_teks_kunci | 1 | 0 | 1.0000 |
| kurasi | teks_pasal21 | llm_teks | 1 | 4 | 0.3750 |
| kurasi | teks_pasal21 | aturan+llm_teks | 1 | 4 | 0.3750 |
| kurasi | teks_pasal21 | llm_teks_kunci | 1 | 4 | 0.3750 |
| kurasi | teks_pasal21 | aturan+llm_teks_kunci | 1 | 4 | 0.3750 |
| kurasi | llm_teks | aturan+llm_teks | 0 | 0 | 1.0000 |
| kurasi | llm_teks | llm_teks_kunci | 0 | 0 | 1.0000 |
| kurasi | llm_teks | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| kurasi | aturan+llm_teks | llm_teks_kunci | 0 | 0 | 1.0000 |
| kurasi | aturan+llm_teks | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| kurasi | llm_teks_kunci | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| feed | aturan | llm | 0 | 0 | 1.0000 |
| feed | aturan | hibrida | 0 | 0 | 1.0000 |
| feed | aturan | teks_pasal21 | 18 | 0 | 0.0000 |
| feed | aturan | llm_teks | 1 | 0 | 1.0000 |
| feed | aturan | aturan+llm_teks | 1 | 0 | 1.0000 |
| feed | aturan | llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | aturan | aturan+llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | llm | hibrida | 0 | 0 | 1.0000 |
| feed | llm | teks_pasal21 | 18 | 0 | 0.0000 |
| feed | llm | llm_teks | 1 | 0 | 1.0000 |
| feed | llm | aturan+llm_teks | 1 | 0 | 1.0000 |
| feed | llm | llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | llm | aturan+llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | hibrida | teks_pasal21 | 18 | 0 | 0.0000 |
| feed | hibrida | llm_teks | 1 | 0 | 1.0000 |
| feed | hibrida | aturan+llm_teks | 1 | 0 | 1.0000 |
| feed | hibrida | llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | hibrida | aturan+llm_teks_kunci | 1 | 0 | 1.0000 |
| feed | teks_pasal21 | llm_teks | 1 | 18 | 0.0001 |
| feed | teks_pasal21 | aturan+llm_teks | 1 | 18 | 0.0001 |
| feed | teks_pasal21 | llm_teks_kunci | 1 | 18 | 0.0001 |
| feed | teks_pasal21 | aturan+llm_teks_kunci | 1 | 18 | 0.0001 |
| feed | llm_teks | aturan+llm_teks | 0 | 0 | 1.0000 |
| feed | llm_teks | llm_teks_kunci | 0 | 0 | 1.0000 |
| feed | llm_teks | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| feed | aturan+llm_teks | llm_teks_kunci | 0 | 0 | 1.0000 |
| feed | aturan+llm_teks | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| feed | llm_teks_kunci | aturan+llm_teks_kunci | 0 | 0 | 1.0000 |
| pajakgoid | aturan | llm | 18 | 30 | 0.1114 |
| pajakgoid | aturan | hibrida | 13 | 2 | 0.0074 |
| pajakgoid | aturan | teks_pasal21 | 129 | 45 | 0.0000 |
| pajakgoid | aturan | llm_teks | 31 | 32 | 1.0000 |
| pajakgoid | aturan | aturan+llm_teks | 29 | 4 | 0.0000 |
| pajakgoid | aturan | llm_teks_kunci | 30 | 30 | 1.0000 |
| pajakgoid | aturan | aturan+llm_teks_kunci | 30 | 4 | 0.0000 |
| pajakgoid | llm | hibrida | 28 | 5 | 0.0001 |
| pajakgoid | llm | teks_pasal21 | 127 | 31 | 0.0000 |
| pajakgoid | llm | llm_teks | 27 | 16 | 0.1263 |
| pajakgoid | llm | aturan+llm_teks | 49 | 12 | 0.0000 |
| pajakgoid | llm | llm_teks_kunci | 30 | 18 | 0.1114 |
| pajakgoid | llm | aturan+llm_teks_kunci | 52 | 14 | 0.0000 |
| pajakgoid | hibrida | teks_pasal21 | 125 | 52 | 0.0000 |
| pajakgoid | hibrida | llm_teks | 23 | 35 | 0.1480 |
| pajakgoid | hibrida | aturan+llm_teks | 21 | 7 | 0.0125 |
| pajakgoid | hibrida | llm_teks_kunci | 24 | 35 | 0.1925 |
| pajakgoid | hibrida | aturan+llm_teks_kunci | 24 | 9 | 0.0135 |
| pajakgoid | teks_pasal21 | llm_teks | 33 | 118 | 0.0000 |
| pajakgoid | teks_pasal21 | aturan+llm_teks | 59 | 118 | 0.0000 |
| pajakgoid | teks_pasal21 | llm_teks_kunci | 34 | 118 | 0.0000 |
| pajakgoid | teks_pasal21 | aturan+llm_teks_kunci | 58 | 116 | 0.0000 |
| pajakgoid | llm_teks | aturan+llm_teks | 28 | 2 | 0.0000 |
| pajakgoid | llm_teks | llm_teks_kunci | 14 | 13 | 1.0000 |
| pajakgoid | llm_teks | aturan+llm_teks_kunci | 38 | 11 | 0.0001 |
| pajakgoid | aturan+llm_teks | llm_teks_kunci | 10 | 35 | 0.0002 |
| pajakgoid | aturan+llm_teks | aturan+llm_teks_kunci | 10 | 9 | 1.0000 |
| pajakgoid | llm_teks_kunci | aturan+llm_teks_kunci | 26 | 0 | 0.0000 |

## Variansi LLM antar-ulangan (temperature 0)

- kurasi (judul): 3 ulangan, keputusan biner berbalik pada 0/22 item; recall per ulangan: 93.8%, 93.8%, 93.8%
- feed (judul): 3 ulangan, keputusan biner berbalik pada 0/98 item; recall per ulangan: -, -, -
- pajakgoid (judul): 3 ulangan, keputusan biner berbalik pada 19/1214 item; recall per ulangan: 80.5%, 75.6%, 80.5%
- kurasi (teks): 3 ulangan, keputusan biner berbalik pada 0/22 item; recall per ulangan: 100.0%, 100.0%, 100.0%
- feed (teks): 3 ulangan, keputusan biner berbalik pada 0/98 item; recall per ulangan: -, -, -
- pajakgoid (teks): 3 ulangan, keputusan biner berbalik pada 23/1214 item; recall per ulangan: 92.7%, 95.1%, 97.6%
- kurasi (teks kata kunci): 3 ulangan, keputusan biner berbalik pada 0/22 item; recall per ulangan: 100.0%, 100.0%, 100.0%
- feed (teks kata kunci): 3 ulangan, keputusan biner berbalik pada 1/98 item; recall per ulangan: -, -, -
- pajakgoid (teks kata kunci): 3 ulangan, keputusan biner berbalik pada 25/1214 item; recall per ulangan: 97.6%, 100.0%, 100.0%

## Positif di set `kurasi`: siapa yang menangkap

| id | label | aturan | llm | hibrida | teks_pasal21 | llm_teks | aturan+llm_teks | llm_teks_kunci | aturan+llm_teks_kunci | judul |
|---|---|---|---|---|---|---|---|---|---|---|
| `101/PMK.010/2016` | dasar | dasar | dasar | dasar | **lewat** | dasar | dasar | dasar | dasar | PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK |
| `122/PMK.010/2015` | dasar | dasar | dasar | dasar | **lewat** | dasar | dasar | dasar | dasar | PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK |
| `PP 58 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | TARIF PEMOTONGAN PAJAK PENGHASII.AN PASAL 21 ATAS PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN, |
| `PMK 168 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PETUNJUK PELAKSANAAN PEMOTONGAN PAJAK ATAS PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN, JASA,  |
| `PMK 66 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PERLAKUAN PAJAK PENGHASILAN ATAS PENGGANTIAN ATAU IMBALAN SEHUBUNGAN DENGAN PEKERJAAN ATAU |
| `PP 68 Tahun 2009` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | TARIF PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN BERUPA UANG PESANGON, UANG MANFAAT PENSI |
| `PP 80 Tahun 2010` | dasar | dasar | dasar | dasar | perlu_ditinjau | fasilitas | dasar | fasilitas | dasar | TARIF PEMOTONGAN DAN PENGENAAN PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN YANG MENJADI BE |
| `250/PMK.03/2008` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | BESARNYA BIAYA JABATAN ATAU BIAYA PENSIUN YANG DAPAT DIKURANGKAN DARI PENGHASILAN BRUTO PE |
| `252/PMK.03/2008` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PETUNJUK PELAKSANAAN PEMOTONGAN PAJAK ATAS PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN , JASA  |
| `PMK 10 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN TERTENTU YANG DITANGGUNG PEMERINTAH DALAM RANG |
| `PMK 72 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PERUBAHAN ATAS PERATURAN MENTERI KEUANGAN NOMOR 10 TAHUN 2025 TENTANG PAJAK PENGHASILAN PA |
| `PMK 105 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN TERTENTU YANG DITANGGUNG PEMERINTAH DALAM RANG |
| `PER-2/PJ/2024` | prosedural | prosedural | prosedural | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | BENTUK DAN TATA CARA PEMBUATAN BUKTI PEMOTONGAN PAJAK PENGHASILAN PASAL 21 DAN/ATAU PAJAK  |
| `PER-11/PJ/2025` | prosedural | prosedural | **lewat** | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | KETENTUAN PELAPORAN PAJAK PENGHASILAN, PAJAK PERTAMBAHAN NILAI, PAJAK PENJUALAN ATAS BARAN |
| `86/PMK.03/2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |
| `9/PMK.03/2021` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |

## Positif di set `pajakgoid`: siapa yang menangkap

| id | label | aturan | llm | hibrida | teks_pasal21 | llm_teks | aturan+llm_teks | llm_teks_kunci | aturan+llm_teks_kunci | judul |
|---|---|---|---|---|---|---|---|---|---|---|
| `PMK 114 Tahun 2025` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PERLAKUAN ATAS BANTUAN ATAU SUMBANGAN TERMASUK ZAKAT ATAU SUMBANGAN KEAGAMAAN YANG SIFATNY |
| `PMK 105 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN TERTENTU YANG DITANGGUNG PEMERINTAH DALAM RANG |
| `PER-23/PJ/2025` | dasar | **lewat** | dasar | dasar | **lewat** | dasar | dasar | **lewat** | **lewat** | PENENTUAN SUBJEK PAJAK DALAM NEGERI DAN SUBJEK PAJAK LUAR NEGERI |
| `PMK 72 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PERUBAHAN ATAS PERATURAN MENTERI KEUANGAN NOMOR 10 TAHUN 2025 TENTANG PAJAK PENGHASILAN PA |
| `PER-11/PJ/2025` | prosedural | prosedural | **lewat** | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | KETENTUAN PELAPORAN PAJAK PENGHASILAN, PAJAK PERTAMBAHAN NILAI, PAJAK PENJUALAN ATAS BARAN |
| `PMK 10 Tahun 2025` | fasilitas | fasilitas | fasilitas | fasilitas | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN TERTENTU YANG DITANGGUNG PEMERINTAH DALAM RANG |
| `PMK 81 Tahun 2024` | prosedural | **lewat** | **lewat** | **lewat** | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | KETENTUAN PERPAJAKAN DALAM RANGKA PELAKSANAAN SISTEM INTI ADMINISTRASI PERPAJAKAN |
| `PER-5/PJ/2024` | prosedural | prosedural | prosedural | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | PERUBAHAN ATAS PERATURAN DIREKTUR JENDERAL PAJAK NOMOR PER-17/PJ/2021 TENTANG BENTUK DAN T |
| `PMK 28 Tahun 2024` | fasilitas | perlu_ditinjau | **lewat** | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | FASILITAS PERPAJAKAN DAN KEPABEANAN DI IBU KOTA NUSANTARA |
| `PER-2/PJ/2024` | prosedural | prosedural | prosedural | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | BENTUK DAN TATA CARA PEMBUATAN BUKTI PEMOTONGAN PAJAK PENGHASILAN PASAL 21 DAN/ATAU PAJAK  |
| `PMK 168 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PETUNJUK PELAKSANAAN PEMOTONGAN PAJAK ATAS PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN, JASA,  |
| `PP 58 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | TARIF PEMOTONGAN PAJAK PENGHASII.AN PASAL 21 ATAS PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN, |
| `PER-7/PJ/2023` | prosedural | **lewat** | **lewat** | **lewat** | **lewat** | dasar | dasar | dasar | dasar | PENGAJUAN KEBERATAN DAN PERPANJANGAN SURAT KEPUTUSAN PENETAPAN BERLOKASI USAHA DI DAERAH T |
| `PMK 66 Tahun 2023` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PERLAKUAN PAJAK PENGHASILAN ATAS PENGGANTIAN ATAU IMBALAN SEHUBUNGAN DENGAN PEKERJAAN ATAU |
| `PP 12 Tahun 2023` | fasilitas | **lewat** | **lewat** | **lewat** | perlu_ditinjau | fasilitas | fasilitas | fasilitas | fasilitas | PEMBERIAN PERIZINAN BERUSAHA, KEMUDAHAN BERUSAHA, DAN FASILITAS PENANAMAN MODAL BAGI PELAK |
| `PP 55 Tahun 2022` | dasar | perlu_ditinjau | dasar | perlu_ditinjau | perlu_ditinjau | dasar | perlu_ditinjau | dasar | perlu_ditinjau | PENYESUAIAN PENGATURAN DI BIDANG PAJAK PENGHASILAN |
| `PMK 3 Tahun 2022` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |
| `UU 7 Tahun 2021` | dasar | perlu_ditinjau | dasar | perlu_ditinjau | perlu_ditinjau | dasar | perlu_ditinjau | dasar | perlu_ditinjau | HARMONISASI PERATURAN PERPAJAKAN |
| `PMK 149 Tahun 2021` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PERUBAHAN KEDUA ATAS PERATURAN MENTERI KEUANGAN NOMOR 9/PMK.03/2021 TENTANG INSENTIF PAJAK |
| `PER-17/PJ/2021` | prosedural | prosedural | prosedural | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | BENTUK DAN TATA CARA PEMBUATAN BUKTI PEMOTONGAN DAN/ATAU PEMUNGUTAN PAJAK, SERTA BENTUK, I |
| `PMK 83 Tahun 2021` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | **lewat** | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PERUBAHAN ATAS PERATURAN MENTER! KEUANGAN NOMOR 239/PMK.03/2020 TENTANG PEMBERIAN FASILITA |
| `PMK 82 Tahun 2021` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PERUBAHAN ATAS PERATURAN MENTERI KEUANGAN NOMOR 9/PMK.03/2021 TENTANG INSENTIF PAJAK UNTUK |
| `PMK 9 Tahun 2021` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |
| `PMK 239 Tahun 2020` | fasilitas | perlu_ditinjau | **lewat** | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PEMBERIAN FASILITAS PAJAK TERHADAP BARANG DAN JASA YANG DIPERLUKAN DALAM RANGKA PENANGANAN |
| `UU 11 Tahun 2020` | dasar | perlu_ditinjau | dasar | perlu_ditinjau | **lewat** | **lewat** | perlu_ditinjau | dasar | perlu_ditinjau | CIPTA KERJA (KLASTER KEMUDAHAN BERUSAHA BIDANG PERPAJAKAN) |
| `PMK 143 Tahun 2020` | fasilitas | perlu_ditinjau | **lewat** | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PEMBERIAN FASILITAS PAJAK TERHADAP BARANG DAN JASA YANG DIPERLUKAN DALAM RANGKA PENANGANAN |
| `PMK 110 Tahun 2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PERUBAHAN ATAS PERATURAN MENTERI KEUANGAN NOMOR 86/PMK.03/2020 TENTANG INSENTIF PAJAK UNTU |
| `PMK 86 Tahun 2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |
| `PMK 68 Tahun 2020` | dasar | **lewat** | dasar | dasar | **lewat** | **lewat** | **lewat** | dasar | dasar | PERLAKUAN PAJAK PENGHASILAN ATAS BEASISWA YANG MEMENUHI PERSYARATAN TERTENTU DAN SISA LEBI |
| `PP 29 Tahun 2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | FASILITAS PAJAK PENGHASILAN DALAM RANGKA PENANGANAN CORONA VIRUS DISEASE 2019 |
| `PMK 44 Tahun 2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK PANDEMI CORONA VIRUS DISEASE 2019 |
| `PMK 28 Tahun 2020` | fasilitas | perlu_ditinjau | **lewat** | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | PEMBERIAN FASILITAS PAJAK TERHADAP BARANG DAN JASA YANG DIPERLUKAN DALAM RANGKA PENANGANAN |
| `PMK 23 Tahun 2020` | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | perlu_ditinjau | fasilitas | perlu_ditinjau | fasilitas | perlu_ditinjau | INSENTIF PAJAK UNTUK WAJIB PAJAK TERDAMPAK WABAH VIRUS CORONA |
| `KEP-158/PJ/2020` | prosedural | prosedural | prosedural | prosedural | perlu_ditinjau | prosedural | prosedural | prosedural | prosedural | PENGECUALIAN PENGENAAN SANKSI ADMINISTRASI BERUPA DENDA ATAS KETERLAMBATAN PENYAMPAIAN SUR |
| `PMK 167 Tahun 2018` | dasar | dasar | dasar | dasar | **lewat** | dasar | dasar | dasar | dasar | PENYEDIAAN MAKANAN DAN MINUMAN BAGI SELURUH PEGAWAI SERTA PENGGANTIAN ATAU IMBALAN DALAM B |
| `PMK 40 Tahun 2017` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | TATA CARA PELAPORAN DAN PENGHITUNGAN PEMOTONGAN PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILA |
| `PP 73 Tahun 2016` | dasar | perlu_ditinjau | dasar | perlu_ditinjau | **lewat** | **lewat** | perlu_ditinjau | dasar | perlu_ditinjau | PAJAK PENGHASILAN ATAS PROGRAM JAMINAN SOSIAL YANG DISELENGGARAKAN BADAN PENYELENGGARA JAM |
| `PP 41 Tahun 2016` | dasar | dasar | dasar | dasar | perlu_ditinjau | fasilitas | dasar | dasar | dasar | PERLAKUAN PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN PEGAWAI DARI PEMBERI KERJA DENGAN KR |
| `PER-16/PJ/2016` | dasar | prosedural | dasar | prosedural | perlu_ditinjau | dasar | prosedural | dasar | prosedural | PEDOMAN TEKNIS TATA CARA PEMOTONGAN, PENYETORAN DAN PELAPORAN PAJAK PENGHASILAN PASAL 21 D |
| `PMK 102 Tahun 2016` | dasar | dasar | dasar | dasar | perlu_ditinjau | dasar | dasar | dasar | dasar | PENETAPAN BAGIAN PENGHASILAN SEHUBUNGAN DENGAN PEKERJAAN DARI PEGAWAI HARIAN DAN MINGGUAN  |
| `PMK 101 Tahun 2016` | dasar | dasar | dasar | dasar | **lewat** | dasar | dasar | dasar | dasar | PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK |
