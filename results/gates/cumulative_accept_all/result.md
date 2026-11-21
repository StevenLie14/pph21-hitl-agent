# Replay kumulatif tanpa manusia

Dibuat oleh `pph21 draft-backtest --kumulatif`. Model LLM: azure:gpt-6-luna. Tabel pembanding tiap langkah adalah keluaran sistem sendiri di langkah sebelumnya (draf `siap` diterapkan, draf `tahan` tidak); selisih = daun nilai yang berbeda dari riwayat berlabel.

| dokumen | tanggal | peran | keputusan | key diterapkan | selisih sebelum | selisih sesudah |
|---|---|---|---|---|---|---|
| KMK 564 Tahun 2004 | 2004-11-29 | peristiwa | siap | - | 0 | 3 |
| PMK 10 Tahun 2005 | 2005-01-31 | peristiwa | siap | ter_harian | 3 | 3 |
| PMK 137 Tahun 2005 | 2005-12-30 | peristiwa | siap | ptkp | 3 | 1 |
| PMK 138 Tahun 2005 | 2005-12-30 | peristiwa | siap | - | 1 | 1 |
| UU 36 Tahun 2008 | 2008-09-23 | peristiwa | siap | ptkp | 1 | 9 |
| PMK 250 Tahun 2008 | 2008-12-31 | peristiwa | siap | - | 9 | 15 |
| PMK 254 Tahun 2008 | 2008-12-31 | peristiwa | siap | ter_harian | 9 | 14 |
| PER-31/PJ/2009 | 2009-05-25 | tanpa_perubahan | siap | biaya_jabatan, biaya_pensiun | 14 | 9 |
| PP 68 Tahun 2009 | 2009-11-16 | peristiwa | siap | pph_final_manfaat_pensiun | 9 | 16 |
| PMK 16 Tahun 2010 | 2010-01-25 | tanpa_perubahan | siap | - | 16 | 16 |
| PP 80 Tahun 2010 | 2010-12-20 | peristiwa | siap | pph_final_honorarium_pns | 16 | 16 |
| PMK 262 Tahun 2010 | 2010-12-31 | tanpa_perubahan | siap | - | 16 | 16 |
| PMK 162 Tahun 2012 | 2012-10-22 | peristiwa | siap | ptkp | 16 | 16 |
| PMK 206 Tahun 2012 | 2012-12-17 | peristiwa | siap | ter_harian | 16 | 16 |
| PER-31/PJ/2012 | 2012-12-27 | tanpa_perubahan | siap | - | 16 | 16 |
| PMK 122 Tahun 2015 | 2015-06-29 | peristiwa | siap | ptkp | 16 | 16 |
| PMK 152 Tahun 2015 | 2015-08-06 | peristiwa | siap | ter_harian | 16 | 16 |
| PER-32/PJ/2015 | 2015-08-07 | tanpa_perubahan | siap | - | 16 | 16 |
| PMK 101 Tahun 2016 | 2016-06-22 | peristiwa | siap | ptkp | 16 | 17 |
| PMK 102 Tahun 2016 | 2016-06-22 | peristiwa | siap | ter_harian | 19 | 16 |
| PER-16/PJ/2016 | 2016-09-29 | tanpa_perubahan | siap | - | 16 | 16 |
| PP 41 Tahun 2016 | 2016-10-17 | kontrol_negatif | siap | - | 16 | 16 |
| PMK 40 Tahun 2017 | 2017-03-10 | kontrol_negatif | siap | - | 16 | 16 |
| PMK 167 Tahun 2018 | 2018-12-19 | kontrol_negatif | siap | - | 16 | 16 |
| PMK 68 Tahun 2020 | 2020-06-15 | kontrol_negatif | tidak_terdeteksi | - | 16 | 16 |
| UU 7 Tahun 2021 | 2021-10-29 | peristiwa | siap | tarif_pasal_17 | 16 | 8 |
| PP 55 Tahun 2022 | 2022-12-20 | kontrol_negatif | siap | - | 8 | 8 |
| PMK 66 Tahun 2023 | 2023-06-27 | kontrol_negatif | tidak_ada_perubahan | - | 8 | 8 |
| PP 58 Tahun 2023 | 2023-12-27 | peristiwa | siap | ter_bulanan, ter_harian | 8 | 8 |
| PMK 168 Tahun 2023 | 2023-12-29 | peristiwa | siap | bukan_pegawai, ter_harian | 8 | 7 |
| PMK 114 Tahun 2025 | 2025-12-30 | kontrol_negatif | siap | - | 7 | 7 |

- Salah lolos: **0**
- Selisih akhir terhadap riwayat berlabel: **7** daun (pph_final_pesangon[0].batas_atas, pph_final_pesangon[0].persen, pph_final_pesangon[1].batas_atas, pph_final_pesangon[1].persen, pph_final_pesangon[2].batas_atas, pph_final_pesangon[2].persen, pph_final_pesangon[3].persen)
