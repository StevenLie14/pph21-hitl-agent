# Analisis dampak: aturan vs LLM vs LLM + graf

- model: azure:gpt-6-luna
- prompt: dampak-v2-2026-10-06
- harga (USD per 1 juta token, asumsi): masuk 0.4, keluar 1.6
- label diverifikasi: 16/16
- positif tanpa teks (dilewati): -
- sumber teks (JDIH dulu): {'KEP-158/PJ/2020': 'pajak.go.id', 'PER-11/PJ/2025': 'jdih', 'PER-16/PJ/2016': 'pajak.go.id', 'PER-17/PJ/2021': 'pajak.go.id', 'PER-2/PJ/2024': 'pajak.go.id', 'PER-23/PJ/2025': 'pajak.go.id', 'PER-5/PJ/2024': 'pajak.go.id', 'PER-7/PJ/2023': 'pajak.go.id', 'PMK 10 Tahun 2025': 'jdih', 'PMK 101 Tahun 2016': 'jdih', 'PMK 102 Tahun 2016': 'pajak.go.id', 'PMK 105 Tahun 2025': 'jdih', 'PMK 110 Tahun 2020': 'jdih', 'PMK 114 Tahun 2025': 'jdih', 'PMK 143 Tahun 2020': 'pajak.go.id', 'PMK 149 Tahun 2021': 'pajak.go.id', 'PMK 167 Tahun 2018': 'jdih', 'PMK 168 Tahun 2023': 'jdih', 'PMK 23 Tahun 2020': 'jdih', 'PMK 239 Tahun 2020': 'pajak.go.id', 'PMK 28 Tahun 2020': 'jdih', 'PMK 28 Tahun 2024': 'pajak.go.id', 'PMK 3 Tahun 2022': 'jdih', 'PMK 40 Tahun 2017': 'pajak.go.id', 'PMK 44 Tahun 2020': 'pajak.go.id', 'PMK 66 Tahun 2023': 'jdih', 'PMK 68 Tahun 2020': 'pajak.go.id', 'PMK 72 Tahun 2025': 'pajak.go.id', 'PMK 81 Tahun 2024': 'pajak.go.id', 'PMK 82 Tahun 2021': 'jdih', 'PMK 83 Tahun 2021': 'pajak.go.id', 'PMK 86 Tahun 2020': 'jdih', 'PMK 9 Tahun 2021': 'pajak.go.id', 'PP 12 Tahun 2023': 'pajak.go.id', 'PP 29 Tahun 2020': 'pajak.go.id', 'PP 41 Tahun 2016': 'pajak.go.id', 'PP 55 Tahun 2022': 'pajak.go.id', 'PP 58 Tahun 2023': 'jdih', 'PP 73 Tahun 2016': 'pajak.go.id', 'UU 11 Tahun 2020': 'pajak.go.id', 'UU 7 Tahun 2021': 'jdih'}

## Kualitas: key yang langsung diatur (dokumen dasar) dan keamanan (fasilitas/prosedural)

| lengan | presisi | recall | F1 | set tepat | fasilitas/prosedural diberi key | key palsu |
|---|---|---|---|---|---|---|
| aturan | 80.0% | 48.0% | 60.0% | 4/16 | 0/25 | 0 |
| gabungan_utuh | 50.0% | 80.0% | 61.5% | 7/16 | 0/25 | 0 |

## Biaya dan latensi (per dokumen; latensi LLM diukur saat dipanggil, cache menyimpan angka aslinya)

| lengan | panggilan LLM | token masuk | token keluar | biaya total USD | biaya/dokumen USD | latensi median s | p90 s | non-LLM median ms |
|---|---|---|---|---|---|---|---|---|
| aturan | 0/41 | 0 | 0 | 0.0000 | 0.00000 | 0.00 | 0.01 | 2.0 |
| gabungan_utuh | 37/41 | 1,041,760 | 4,518 | 0.4239 | 0.01034 | 2.35 | 9.91 | 6.5 |

Key dibuang karena kutipan tidak ada di teks: gabungan_utuh 1; tidak valid: gabungan_utuh 0.

## Per dokumen

| id | label | benar | aturan | gabungan_utuh | turunan dari graf (gabungan_utuh) |
|---|---|---|---|---|---|
| `PER-16/PJ/2016` | dasar | bukan_pegawai, mekanisme_pemotongan | - | biaya_jabatan, biaya_pensiun, bukan_pegawai, mekanisme_pemotongan, natura, non_npwp, pembulatan_pkp, pph26, ptkp, tarif_pasal_17, ter_harian | kategori_ter, ter_bulanan |
| `PER-23/PJ/2025` | dasar | mekanisme_pemotongan | - | - | - |
| `PMK 101 Tahun 2016` | dasar | ptkp | ptkp | ptkp | kategori_ter, ter_bulanan |
| `PMK 102 Tahun 2016` | dasar | ter_harian | - | ter_harian | - |
| `PMK 114 Tahun 2025` | dasar | mekanisme_pemotongan | - | mekanisme_pemotongan | - |
| `PMK 167 Tahun 2018` | dasar | natura | natura | natura | - |
| `PMK 168 Tahun 2023` | dasar | biaya_jabatan, biaya_pensiun, bukan_pegawai, mekanisme_pemotongan, ter_harian | biaya_jabatan, biaya_pensiun, mekanisme_pemotongan | biaya_jabatan, biaya_pensiun, bukan_pegawai, kategori_ter, mekanisme_pemotongan, natura, pembulatan_pkp, pph26 | ter_bulanan |
| `PMK 40 Tahun 2017` | dasar | mekanisme_pemotongan | - | mekanisme_pemotongan | - |
| `PMK 66 Tahun 2023` | dasar | natura | natura | mekanisme_pemotongan, natura | - |
| `PMK 68 Tahun 2020` | dasar | mekanisme_pemotongan | - | - | - |
| `PP 41 Tahun 2016` | dasar | mekanisme_pemotongan | - | tarif_pasal_17 | - |
| `PP 55 Tahun 2022` | dasar | natura | - | natura, tarif_pasal_17 | - |
| `PP 58 Tahun 2023` | dasar | kategori_ter, ter_bulanan, ter_harian | kategori_ter, pph_final_honorarium_pns, ter_bulanan, ter_harian | kategori_ter, pph_final_honorarium_pns, tarif_pasal_17, ter_bulanan, ter_harian | - |
| `PP 73 Tahun 2016` | dasar | mekanisme_pemotongan | - | mekanisme_pemotongan | - |
| `UU 11 Tahun 2020` | dasar | mekanisme_pemotongan | natura, pph26 | natura, pph26 | - |
| `UU 7 Tahun 2021` | dasar | natura, ptkp, tarif_pasal_17 | natura, ptkp, tarif_pasal_17 | natura, ptkp, tarif_pasal_17 | kategori_ter, ter_bulanan |
| `KEP-158/PJ/2020` | prosedural | - | - | - | - |
| `PER-11/PJ/2025` | prosedural | - | - | - | - |
| `PER-17/PJ/2021` | prosedural | - | - | - | - |
| `PER-2/PJ/2024` | prosedural | - | - | - | - |
| `PER-5/PJ/2024` | prosedural | - | - | - | - |
| `PER-7/PJ/2023` | prosedural | - | - | - | - |
| `PMK 10 Tahun 2025` | fasilitas | - | - | - | - |
| `PMK 105 Tahun 2025` | fasilitas | - | - | - | - |
| `PMK 110 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 143 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 149 Tahun 2021` | fasilitas | - | - | - | - |
| `PMK 23 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 239 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 28 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 28 Tahun 2024` | fasilitas | - | - | - | - |
| `PMK 3 Tahun 2022` | fasilitas | - | - | - | - |
| `PMK 44 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 72 Tahun 2025` | fasilitas | - | - | - | - |
| `PMK 81 Tahun 2024` | prosedural | - | - | - | - |
| `PMK 82 Tahun 2021` | fasilitas | - | - | - | - |
| `PMK 83 Tahun 2021` | fasilitas | - | - | - | - |
| `PMK 86 Tahun 2020` | fasilitas | - | - | - | - |
| `PMK 9 Tahun 2021` | fasilitas | - | - | - | - |
| `PP 12 Tahun 2023` | fasilitas | - | - | - | - |
| `PP 29 Tahun 2020` | fasilitas | - | - | - | - |

## Contoh keluaran graf untuk reviewer (dokumen dasar)

- `PER-16/PJ/2016`: key ['biaya_jabatan', 'biaya_pensiun', 'bukan_pegawai', 'mekanisme_pemotongan', 'natura', 'non_npwp', 'pembulatan_pkp', 'pph26', 'ptkp', 'tarif_pasal_17', 'ter_harian']; turunan ['kategori_ter', 'ter_bulanan']; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `PMK 101 Tahun 2016`: key ['ptkp']; turunan ['kategori_ter', 'ter_bulanan']; 10 fungsi hitung; test: test_monitor_impact.py, test_properties.py, test_validation.py
- `PMK 102 Tahun 2016`: key ['ter_harian']; turunan -; 1 fungsi hitung; test: test_monitor_impact.py
- `PMK 114 Tahun 2025`: key ['mekanisme_pemotongan']; turunan -; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `PMK 167 Tahun 2018`: key ['natura']; turunan -; 1 fungsi hitung; test: -
- `PMK 168 Tahun 2023`: key ['biaya_jabatan', 'biaya_pensiun', 'bukan_pegawai', 'kategori_ter', 'mekanisme_pemotongan', 'natura', 'pembulatan_pkp', 'pph26']; turunan ['ter_bulanan']; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `PMK 40 Tahun 2017`: key ['mekanisme_pemotongan']; turunan -; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `PMK 66 Tahun 2023`: key ['mekanisme_pemotongan', 'natura']; turunan -; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `PP 41 Tahun 2016`: key ['tarif_pasal_17']; turunan -; 13 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_properties.py, test_validation.py
- `PP 55 Tahun 2022`: key ['natura', 'tarif_pasal_17']; turunan -; 14 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_properties.py, test_validation.py
- `PP 58 Tahun 2023`: key ['kategori_ter', 'pph_final_honorarium_pns', 'tarif_pasal_17', 'ter_bulanan', 'ter_harian']; turunan -; 14 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_properties.py, test_validation.py; dari relasi teks: ['pph_final_honorarium_pns']
- `PP 73 Tahun 2016`: key ['mekanisme_pemotongan']; turunan -; 17 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_progressive_brackets.py, test_properties.py, test_rates.py, test_validation.py
- `UU 11 Tahun 2020`: key ['natura', 'pph26']; turunan -; 2 fungsi hitung; test: -; dari relasi teks: ['natura', 'pph26']
- `UU 7 Tahun 2021`: key ['natura', 'ptkp', 'tarif_pasal_17']; turunan ['kategori_ter', 'ter_bulanan']; 15 fungsi hitung; test: test_ikn_third_year_object_codes.py, test_monitor_impact.py, test_properties.py, test_validation.py; dari relasi teks: ['natura', 'ptkp', 'tarif_pasal_17']
