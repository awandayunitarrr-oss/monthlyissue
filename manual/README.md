# Isian manual pembanding

File `pembanding.csv` dipakai slide **Rilis Motor Indonesia** sebagai data pembanding (produk sebelumnya),
terutama untuk merek yang datanya tidak bisa diambil otomatis dari situs resmi (mis. Honda).
Isian manual selalu diutamakan di atas data otomatis.

Satu baris = satu tipe/varian untuk satu tahun model.

| Kolom | Isi | Contoh |
| --- | --- | --- |
| `merek` | Nama merek | `Honda` |
| `model` | Nama model, cukup bagian yang khas | `PCX160` |
| `tahun` | Tahun model | `2025` |
| `tipe` | Nama tipe/varian | `ABS` |
| `harga` | Harga OTR Jakarta (angka saja) | `37350000` |
| `warna` | Daftar warna, pisahkan dengan `;` | `Phenomenal Matte Red; Phenomenal White` |
| `gambar` | (opsional) URL gambar per warna, urutan sama dengan `warna`, pisahkan `;` | |
| `catatan` | (opsional) catatan singkat, tampil di slide | |

- Untuk rilis tahun 2026, slide memakai baris dengan **tahun terbaru sebelum 2026** sebagai "Sebelumnya".
- Baris dengan **tahun yang sama** dengan tahun rilis menggantikan data produk baru hasil baca artikel.
- Edit langsung di GitHub (ikon pensil), lalu **Commit changes**. Dashboard ter-update otomatis dalam beberapa menit.
