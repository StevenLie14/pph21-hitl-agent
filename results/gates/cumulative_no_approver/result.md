# Replay kumulatif tanpa manusia

Dibuat oleh `pph21 draft-backtest --kumulatif`. Model LLM: azure:gpt-6-luna. Tabel pembanding tiap langkah adalah keluaran sistem sendiri di langkah sebelumnya (draf `siap` diterapkan, draf `tahan` tidak); selisih = daun nilai yang berbeda dari riwayat berlabel.

| dokumen | tanggal | peran | keputusan | key diterapkan | selisih sebelum | selisih sesudah |
|---|---|---|---|---|---|---|
| KMK 564 Tahun 2004 | 2004-11-29 | peristiwa | tahan | - | 0 | 3 |
| PMK 10 Tahun 2005 | 2005-01-31 | peristiwa | tahan | - | 3 | 4 |
| PMK 137 Tahun 2005 | 2005-12-30 | peristiwa | tahan | - | 4 | 4 |
| PMK 138 Tahun 2005 | 2005-12-30 | peristiwa | tahan | - | 4 | 4 |
| UU 36 Tahun 2008 | 2008-09-23 | peristiwa | tahan | - | 4 | 12 |
| PMK 250 Tahun 2008 | 2008-12-31 | peristiwa | tahan | - | 12 | 18 |
| PMK 254 Tahun 2008 | 2008-12-31 | peristiwa | tahan | - | 12 | 18 |
| PER-31/PJ/2009 | 2009-05-25 | tanpa_perubahan | tahan | - | 18 | 19 |
| PP 68 Tahun 2009 | 2009-11-16 | peristiwa | tahan | - | 19 | 29 |
| PMK 16 Tahun 2010 | 2010-01-25 | tanpa_perubahan | tahan | - | 29 | 29 |
| PP 80 Tahun 2010 | 2010-12-20 | peristiwa | tahan | - | 29 | 33 |
| PMK 262 Tahun 2010 | 2010-12-31 | tanpa_perubahan | tahan | - | 33 | 33 |
| PMK 162 Tahun 2012 | 2012-10-22 | peristiwa | tahan | - | 33 | 33 |
| PMK 206 Tahun 2012 | 2012-12-17 | peristiwa | tahan | - | 33 | 33 |
| PER-31/PJ/2012 | 2012-12-27 | tanpa_perubahan | tahan | - | 33 | 33 |
| PMK 122 Tahun 2015 | 2015-06-29 | peristiwa | tahan | - | 33 | 33 |
| PMK 152 Tahun 2015 | 2015-08-06 | peristiwa | tahan | - | 33 | 33 |
| PER-32/PJ/2015 | 2015-08-07 | tanpa_perubahan | tahan | - | 33 | 33 |
| PMK 101 Tahun 2016 | 2016-06-22 | peristiwa | tahan | - | 33 | 33 |
| PMK 102 Tahun 2016 | 2016-06-22 | peristiwa | tahan | - | 33 | 33 |
| PER-16/PJ/2016 | 2016-09-29 | tanpa_perubahan | tahan | - | 33 | 33 |
| PP 41 Tahun 2016 | 2016-10-17 | kontrol_negatif | tahan | - | 33 | 33 |
| PMK 40 Tahun 2017 | 2017-03-10 | kontrol_negatif | tahan | - | 33 | 33 |
| PMK 167 Tahun 2018 | 2018-12-19 | kontrol_negatif | tahan | - | 33 | 33 |
| PMK 68 Tahun 2020 | 2020-06-15 | kontrol_negatif | tidak_ada_perubahan | - | 33 | 33 |
| UU 7 Tahun 2021 | 2021-10-29 | peristiwa | tahan | - | 33 | 32 |
| PP 55 Tahun 2022 | 2022-12-20 | kontrol_negatif | tahan | - | 32 | 32 |
| PMK 66 Tahun 2023 | 2023-06-27 | kontrol_negatif | tahan | - | 32 | 32 |
| PP 58 Tahun 2023 | 2023-12-27 | peristiwa | tahan | - | 32 | 283 |
| PMK 168 Tahun 2023 | 2023-12-29 | peristiwa | tahan | - | 283 | 285 |
| PMK 114 Tahun 2025 | 2025-12-30 | kontrol_negatif | tahan | - | 285 | 285 |

- Salah lolos: **0**
- Selisih akhir terhadap riwayat berlabel: **285** daun (ptkp.tambahan_kawin, ptkp.tambahan_tanggungan, ptkp.wajib_pajak_sendiri, biaya_jabatan.maksimal_sebulan, biaya_jabatan.maksimal_setahun, biaya_jabatan.persen, biaya_pensiun.maksimal_sebulan, biaya_pensiun.maksimal_setahun, biaya_pensiun.persen, tarif_pasal_17[0].batas_atas, tarif_pasal_17[1].batas_atas, tarif_pasal_17[1].persen ...)
