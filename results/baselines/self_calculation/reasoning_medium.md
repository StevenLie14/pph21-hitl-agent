# LLM menghitung PPh 21 sendiri (azure:gpt-6-luna, 52 kasus, 3 run per kondisi)

| kondisi | benar (selisih <= Rp1) | dalam 1% | tanpa angka | median selisih yang salah | kasus benar di semua run | kasus tidak stabil | token rata-rata | jalan kode rata-rata |
|---|---|---|---|---|---|---|---|---|
| tanpa_data | 116/156 | 117/156 | 0 | Rp450,000 | 32/52 | 14 | 944 | 0.0 |
| dengan_tabel | 133/156 | 134/156 | 0 | Rp450,000 | 40/52 | 7 | 4,308 | 0.0 |
| dengan_kode | 105/156 | 105/156 | 36 | Rp1,000,000 | 24/52 | 21 | 13,256 | 2.27 |

Acuan: mesin hitung deterministik pada argumen yang diharapkan; kebenaran mesin sendiri dari uji emas contoh lampiran resmi, jadi angka di sini mengukur selisih LLM terhadap mesin.
