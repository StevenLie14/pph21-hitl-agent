# Backtest temporal tingkat agent

Model: gpt-6-luna (azure), 2026-11-17T15:56:22, ulangan 1.

Tabel: label.

Dunia beku: tabel tarif, regulasi.yaml (tanpa ringkasan), provenans (kosong), graf (peraturan yang terbit pada/sesudah tanggal potong disembunyikan; FAQ mati). Tidak beku: kode, prompt, dan dasar_hukum bawaan mesin.

## Kasus

| Kasus | Peristiwa | Beku | Jeda ke 1 Jan (hari) | Patch | Kunci ditinjau | PPh lama | PPh baru | PPh x1,2 |
|---|---|---|---|---|---|---|---|---|
| a2009 | UU 36 Tahun 2008, PMK 250 Tahun 2008, PMK 254 Tahun 2008 | 2008-09-23 | 100 | manusia | 19 | - | 18328000 | 17499840 |
| a2013 | PMK 162 Tahun 2012, PMK 206 Tahun 2012 | 2012-10-22 | 71 | manusia | 5 | 18328000 | 16847500 | 15997000 |
| a2015 | PMK 122 Tahun 2015 | 2015-06-29 | -179 | pipeline | 4 | 16847500 | 14800000 | 13540000 |
| a2016 | PMK 101 Tahun 2016 | 2016-06-22 | -173 | pipeline | 4 | 14800000 | 11650000 | 9760000 |
| a2022 | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 11650000 | 10650000 | 9450000 |
| a2024 | PP 58 Tahun 2023, PMK 168 Tahun 2023 | 2023-12-27 | 5 | manusia | 263 | - | 900000 | 600000 |
| a2013p | PMK 162 Tahun 2012, PMK 206 Tahun 2012 | 2012-10-22 | 71 | manusia | 5 | 2490000 | 1961250 | 1657500 |
| a2022b | UU 7 Tahun 2021 | 2021-10-29 | 64 | manusia | 14 | 6250000 | 5250000 | 4050000 |
| a2010f | PP 68 Tahun 2009 | 2009-11-16 | 46 | manusia | 12 | - | 5500000 | 4200000 |
| a2011f | PP 80 Tahun 2010 | 2010-12-20 | 12 | manusia | 4 | - | 500000 | 600000 |

## Hasil per fase

| Kasus | basi_hilang | basi_lanjutan | sadar | teradaptasi_asli | teradaptasi_ubah |
|---|---|---|---|---|---|
| a2009 | melapor 1 | tanpa_angka 1 | melapor 1 | benar 1 | benar 1 |
| a2013 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2015 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2016 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2022 | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2024 | melapor 1 | tanpa_angka 1 | melapor 1 | benar 1 | benar 1 |
| a2013p | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2022b | melapor 1 | angka_lama_diam 1 | melapor_dengan_angka 1 | benar 1 | benar 1 |
| a2010f | - | - | - | benar 1 | benar 1 |
| a2011f | - | - | - | benar 1 | benar 1 |

## Ringkasan (kasus lima fase)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| basi_hilang | 8 | melapor 8 | 8 | 0 | 0 | 10.2 | 3 |
| basi_lanjutan | 8 | angka_lama_diam 6, tanpa_angka 2 | 0 | 0 | 0 | 14.6 | 3 |
| sadar | 8 | melapor 2, melapor_dengan_angka 6 | 8 | 8 | 0 | 16.0 | 3 |
| teradaptasi_asli | 8 | benar 8 | 0 | 7 | 0 | 14.5 | 3 |
| teradaptasi_ubah | 8 | benar 8 | 0 | 7 | 0 | 14.2 | 3 |

## Ringkasan kasus sebagian (hanya fase teradaptasi)

| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | Detik (median) | Putaran (median) |
|---|---|---|---|---|---|---|---|
| teradaptasi_asli | 2 | benar 2 | 0 | 2 | 0 | 8.3 | 2 |
| teradaptasi_ubah | 2 | benar 2 | 0 | 2 | 0 | 10.4 | 2 |

Token LLM masuk / keluar: 2301785 / 21946 (498.8 keluar per run).

Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, `angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), `melapor_keliru`, `salah`, `tanpa_angka`, `galat`.
