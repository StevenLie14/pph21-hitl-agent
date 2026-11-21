# Evaluasi Fase 2: draf tarif dan gerbang

Dibuat oleh `pph21 draft-evaluate`. Pasangan G4: pola+llm. Model LLM: azure:gpt-6-luna, prompt draf-llm-v3-2026-11-16-teks-utuh. Label: `taxagent/taxes/pph21/data/draf_label.yaml` (belum ada penilai kedua).

## 1. Replay ekstraksi (per angka)

| set | ekstraktor | benar | salah | terlewat | presisi | recall |
|---|---|---|---|---|---|---|
| dev | det | 38 | 5 | 2 | 88.4% | 95.0% |
| dev | llm | 39 | 5 | 1 | 88.6% | 97.5% |
| dev | sepakat | 37 | 2 | 3 | 94.9% | 92.5% |
| dev | tabel_ocr | 254 | 0 | 0 | 100.0% | 100.0% |
| dev | tabel_visi | 254 | 0 | 0 | 100.0% | 100.0% |
| uji | det | 62 | 0 | 48 | 100.0% | 56.4% |
| uji | llm | 108 | 3 | 2 | 97.3% | 98.2% |
| uji | sepakat | 62 | 0 | 48 | 100.0% | 56.4% |

`det` = pola regex; `llm` = LLM jendela teks; `graf` = LLM lewat bukti graf; `llm2` = LLM kedua; `sepakat` = angka yang dibaca SAMA oleh kedua ekstraktor pasangan G4 (yang bisa lolos gerbang); `tabel_ocr` / `tabel_visi` = tabel TER lampiran dibaca dari PDF JDIH (OCR kotak / LLM vision), dinilai terpisah; ekstraktor teks dinilai tanpa daun tabel.

Sumber teks (urutan sistem terpasang: JDIH andal, pajak.go.id, JDIH perlu_dicek): jdih 20, pajak.go.id 11.
Tabel lampiran: PDF JDIH lokal: OCR kotak + LLM vision.

Salah (dev, det):

- PMK 66 Tahun 2023: natura.kupon_batas_sebulan=2000000 (label tidak ada)
- PMK 66 Tahun 2023: natura.bingkisan_batas_setahun=3000000 (label tidak ada)
- PMK 66 Tahun 2023: natura.olahraga_batas_setahun=1500000 (label tidak ada)
- PMK 66 Tahun 2023: natura.tempat_tinggal_batas_sebulan=2000000 (label tidak ada)
- PMK 66 Tahun 2023: natura.kendaraan_batas_rata_bruto_sebulan=100000000 (label tidak ada)

Salah (dev, llm):

- PMK 168 Tahun 2023: ter_harian.batas_bebas_harian=2500000 (label tidak ada)
- PER-16/PJ/2016: ter_harian.batas_atas_ter_harian=450000 (label tidak ada)
- PP 58 Tahun 2023: ter_harian.dpp_persen_di_atas_batas=0.5 (label tidak ada)
- PMK 66 Tahun 2023: natura.kupon_batas_sebulan=2000000 (label tidak ada)
- PMK 66 Tahun 2023: natura.kendaraan_batas_rata_bruto_sebulan=100000000 (label tidak ada)

Salah (dev, sepakat):

- PMK 66 Tahun 2023: natura.kupon_batas_sebulan=2000000 (label tidak ada)
- PMK 66 Tahun 2023: natura.kendaraan_batas_rata_bruto_sebulan=100000000 (label tidak ada)

Salah (uji, llm):

- PER-31/PJ/2009: ter_harian.batas_atas_ter_harian=150000 (label tidak ada)
- PER-31/PJ/2012: ter_harian.batas_atas_ter_harian=200000 (label tidak ada)
- PER-32/PJ/2015: ter_harian.batas_atas_ter_harian=300000 (label tidak ada)

## 2. Tanggal berlaku (G6)

| set | benar | salah |
|---|---|---|
| dev | 13 | 0 |
| uji | 17 | 1 |

- PMK 162 Tahun 2012: terbaca None (mulai berlaku 2012-10-22 (tengah tahun)), label 2013

## 3. Mutasi

| set | jenis | n | siap | tahan | tidak ada perubahan | ditolak | dilewati | **salah lolos** | gerbang yang menahan |
|---|---|---|---|---|---|---|---|---|---|
| dev | asli | 13 | 4 | 0 | 9 | 0 | 0 | **0** | G1 1, G3 1, G4 3 |
| dev | ubah | 33 | 33 | 0 | 0 | 0 | 0 | **0** | G1 2, G3 1, G4 19, G5 8 |
| dev | digit | 33 | 33 | 0 | 0 | 0 | 0 | **3** | G1 31, G2 2, G3 33, G4 31, G5 3 |
| dev | kata | 33 | 33 | 0 | 0 | 0 | 0 | **3** | G1 31, G2 2, G3 33, G4 15, G5 3 |
| dev | kali10 | 33 | 30 | 0 | 0 | 3 | 0 | **0** | G1 2, G3 1, G4 18, G5 28 |
| dev | tengah | 33 | 33 | 0 | 0 | 0 | 0 | **0** | G1 2, G3 1, G4 19, G5 8, G6 31 |
| uji | asli | 18 | 10 | 0 | 8 | 0 | 0 | **0** | G1 10, G4 3 |
| uji | ubah | 84 | 84 | 0 | 0 | 0 | 0 | **0** | G1 42, G4 64, G5 21 |
| uji | digit | 84 | 84 | 0 | 0 | 0 | 0 | **6** | G1 78, G2 3, G3 84, G4 81, G5 6 |
| uji | kata | 84 | 84 | 0 | 0 | 0 | 0 | **6** | G1 78, G2 3, G3 84, G4 28, G5 6 |
| uji | kali10 | 84 | 80 | 0 | 0 | 0 | 4 | **0** | G1 39, G4 61, G5 46 |
| uji | tengah | 84 | 84 | 0 | 0 | 0 | 0 | **0** | G1 42, G4 64, G5 21, G6 49 |

### Pembanding (dari run yang sama, tanpa panggilan LLM tambahan)

Nilai salah yang masuk tabel bila draf diterima tanpa gerbang (pola saja), bila bacaan LLM diterima langsung (LLM saja), dan bila hanya kesepakatan dua ekstraktor (G4) yang dipakai. Penahan tunggal: draf salah yang hanya ditahan satu gerbang; mematikan gerbang itu meloloskannya.

| set | jenis | n | salah lolos (G1-G8) | pola saja | LLM saja | G4 saja | penahan tunggal |
|---|---|---|---|---|---|---|---|
| dev | asli | 13 | 0 | 0 | 3 | 0 | - |
| dev | ubah | 33 | 0 | 0 | 15 | 0 | - |
| dev | digit | 33 | 3 | 3 | 31 | 0 | - |
| dev | kata | 33 | 3 | 3 | 14 | 0 | - |
| dev | kali10 | 33 | 0 | 0 | 15 | 0 | - |
| dev | tengah | 33 | 0 | 0 | 15 | 0 | - |
| uji | asli | 18 | 0 | 0 | 3 | 0 | - |
| uji | ubah | 84 | 0 | 0 | 29 | 0 | - |
| uji | digit | 84 | 6 | 6 | 81 | 0 | - |
| uji | kata | 84 | 6 | 6 | 28 | 0 | - |
| uji | kali10 | 84 | 0 | 0 | 29 | 0 | - |
| uji | tengah | 84 | 0 | 0 | 29 | 0 | - |

Salah lolos:

- UU 7 Tahun 2021 digit tarif_pasal_17[0].batas_atas: 60000000 -> 72000000: tarif_pasal_17: draf [{'batas_atas': 250000000, 'persen': 15}, {'batas_atas': 500000000, 'persen': 25}, {'batas_atas': 5000000000, 'persen': 30}, {'batas_atas': None, 'persen': 35}], seharusnya [{'batas_atas': 60000000, 'persen': 5}, {'batas_atas': 250000000, 'persen': 15}, {'batas_atas': 500000000, 'persen': 25}, {'batas_atas': 5000000000, 'persen': 30}, {'batas_atas': None, 'persen': 35}]
- UU 7 Tahun 2021 kata tarif_pasal_17[0].batas_atas: 60000000 -> 72000000: tarif_pasal_17: draf [{'batas_atas': 250000000, 'persen': 15}, {'batas_atas': 500000000, 'persen': 25}, {'batas_atas': 5000000000, 'persen': 30}, {'batas_atas': None, 'persen': 35}], seharusnya [{'batas_atas': 60000000, 'persen': 5}, {'batas_atas': 250000000, 'persen': 15}, {'batas_atas': 500000000, 'persen': 25}, {'batas_atas': 5000000000, 'persen': 30}, {'batas_atas': None, 'persen': 35}]
- PER-16/PJ/2016 digit ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 4500000 -> 5400000: ptkp: draf {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 375000, 'tambahan_tanggungan': 375000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}
- PER-16/PJ/2016 kata ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 4500000 -> 5400000: ptkp: draf {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 375000, 'tambahan_tanggungan': 375000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}
- PER-16/PJ/2016 digit ptkp.wajib_pajak_sendiri: 54000000 -> 64800000: ptkp: draf {'wajib_pajak_sendiri': 4500000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}
- PER-16/PJ/2016 kata ptkp.wajib_pajak_sendiri: 54000000 -> 64800000: ptkp: draf {'wajib_pajak_sendiri': 4500000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 54000000, 'tambahan_kawin': 4500000, 'tambahan_tanggungan': 4500000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2009 digit ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 1320000 -> 1584000: ptkp: draf {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 110000, 'tambahan_tanggungan': 110000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2009 kata ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 1320000 -> 1584000: ptkp: draf {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 110000, 'tambahan_tanggungan': 110000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2009 digit ptkp.wajib_pajak_sendiri: 15840000 -> 19008000: ptkp: draf {'wajib_pajak_sendiri': 1320000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2009 kata ptkp.wajib_pajak_sendiri: 15840000 -> 19008000: ptkp: draf {'wajib_pajak_sendiri': 1320000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 15840000, 'tambahan_kawin': 1320000, 'tambahan_tanggungan': 1320000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2012 digit ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 2025000 -> 2430000: ptkp: draf {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 168750, 'tambahan_tanggungan': 168750, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2012 kata ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 2025000 -> 2430000: ptkp: draf {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 168750, 'tambahan_tanggungan': 168750, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2012 digit ptkp.wajib_pajak_sendiri: 24300000 -> 29160000: ptkp: draf {'wajib_pajak_sendiri': 2025000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}
- PER-31/PJ/2012 kata ptkp.wajib_pajak_sendiri: 24300000 -> 29160000: ptkp: draf {'wajib_pajak_sendiri': 2025000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 24300000, 'tambahan_kawin': 2025000, 'tambahan_tanggungan': 2025000, 'maksimal_tanggungan': 3}
- PER-32/PJ/2015 digit ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 3000000 -> 3600000: ptkp: draf {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 250000, 'tambahan_tanggungan': 250000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}
- PER-32/PJ/2015 kata ptkp.tambahan_kawin,ptkp.tambahan_tanggungan: 3000000 -> 3600000: ptkp: draf {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 250000, 'tambahan_tanggungan': 250000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}
- PER-32/PJ/2015 digit ptkp.wajib_pajak_sendiri: 36000000 -> 43200000: ptkp: draf {'wajib_pajak_sendiri': 3000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}
- PER-32/PJ/2015 kata ptkp.wajib_pajak_sendiri: 36000000 -> 43200000: ptkp: draf {'wajib_pajak_sendiri': 3000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}, seharusnya {'wajib_pajak_sendiri': 36000000, 'tambahan_kawin': 3000000, 'tambahan_tanggungan': 3000000, 'maksimal_tanggungan': 3}
