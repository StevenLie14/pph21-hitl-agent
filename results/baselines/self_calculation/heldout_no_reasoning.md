# LLM menghitung PPh 21 sendiri (azure:gpt-6-luna, 28 kasus, 3 run per kondisi)

| kondisi | benar (selisih <= Rp1) | dalam 1% | tanpa angka | median selisih yang salah | kasus benar di semua run | kasus tidak stabil | token rata-rata | jalan kode rata-rata |
|---|---|---|---|---|---|---|---|---|
| tanpa_data | 18/84 | 18/84 | 1 | Rp735,000 | 6/28 | 0 | 300 | 0.0 |
| dengan_tabel | 29/84 | 29/84 | 0 | Rp1,174,225 | 6/28 | 6 | 3,844 | 0.0 |
| dengan_kode | 44/84 | 44/84 | 0 | Rp619,065 | 10/28 | 9 | 7,316 | 0.83 |

Acuan: mesin hitung deterministik pada argumen yang diharapkan; kebenaran mesin sendiri dari uji emas contoh lampiran resmi, jadi angka di sini mengukur selisih LLM terhadap mesin.
