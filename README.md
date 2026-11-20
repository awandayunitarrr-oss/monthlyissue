# Motorcycle Issue Dashboard

Dashboard rekap issue motor dari **Iwan Banaran**, **Pertamax7**, dan **TMC Blog**,
di-update otomatis setiap hari (23:17 WIB); rekap tetap per periode 1–15 dan 16–akhir bulan.

## Cara kerja

| Bagian | File | Fungsi |
| --- | --- | --- |
| Scraper | `scraper/fetch_issues.py` | Ambil artikel per periode (RSS → sitemap → halaman depan), beri tag merek & kategori |
| Konfigurasi | `scraper/config.json` | Daftar sumber, kata kunci merek & kategori |
| Data | `docs/data/periods/YYYY-MM-H1.json` / `H2.json` | Satu file per periode (H1 = tgl 1–15, H2 = tgl 16–akhir) |
| Dashboard | `docs/index.html` | Halaman statis, membaca `docs/data/` |
| Jadwal | `.github/workflows/update-issues.yml` | Menjalankan scraper, commit data, deploy ke GitHub Pages |

## Aktivasi (sekali saja)

1. Merge branch ini ke `main` (jadwal GitHub Actions hanya jalan dari default branch).
2. **Settings → Pages → Source: GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions: Read and write**.
4. **Actions → Update Motorcycle Issue → Run workflow** untuk percobaan pertama
   (isi periode, mis. `2026-11-H1`, atau kosongkan).

## Menjalankan manual

```bash
pip install -r scraper/requirements.txt
python scraper/fetch_issues.py --period 2026-11-H1
python -m http.server -d docs 8000   # buka http://localhost:8000
```

## Kurasi manual

Di file periode, tiap artikel boleh diberi:

- `"highlight": true` — tandai ★ sebagai issue pilihan untuk deck
- `"locked": true` — judul/ringkasan/tag yang sudah diedit tidak ditimpa saat update berikutnya
- `"note": "..."` — catatan bebas

Tambah merek/kategori baru cukup lewat `scraper/config.json`.

## Ringkasan artikel ("Poin penting")

Setiap artikel diringkas menjadi 3–5 poin (`scraper/summarize.py`):

- **Tanpa pengaturan apa pun**: ringkasan otomatis — memilih kalimat terpenting dari artikel
  (kalimat asli, bukan ditulis ulang).
- **Dengan AI (opsional)**: tambahkan secret `ANTHROPIC_API_KEY` di
  **Settings → Secrets and variables → Actions → New repository secret**. Ringkasan lalu ditulis
  ulang oleh Claude dalam bahasa baku, dan artikel yang sudah diringkas AI tidak diringkas ulang.

## Deploy di Vercel (opsional)

`vercel.json` menyalin `docs/` ke `public/` dan menayangkannya sebagai situs statis.
Di pengaturan proyek Vercel, **Root Directory harus kosong** (bukan `scraper`), kalau tidak
folder `docs/` tidak terlihat saat build.

## Rilis Motor Indonesia & pembanding

Menu **Rilis Motor Indonesia** mengumpulkan berita peluncuran motor di Indonesia dan membuat slide
perbandingan "sebelumnya vs sekarang" per tipe (harga, warna, gambar). Sumber pembanding, urut prioritas:

1. **Isian manual** — `manual/pembanding.csv` (lihat `manual/README.md`). Dipakai untuk Honda dan merek lain.
2. **Situs resmi Yamaha** — halaman produk publik dicatat setiap update ke `docs/data/official/yamaha/`;
   untuk rilis sebelum pencatatan dimulai dipakai arsip Internet Archive dari halaman resmi tersebut.
3. **Artikel blog** — artikel rilis versi sebelumnya yang ditemukan otomatis.

Situs resmi merek lain tidak diambil otomatis karena datanya hanya tersedia lewat API internal mereka.

## Special Case: Motor Listrik (EV)

Tab **⚡ Special Case: Motor Listrik** memisahkan rilis EV (baterai, jarak tempuh, daya motor, waktu cas, swap/subsidi)
dari motor bensin, plus isu EV lain per periode.

**Sorotan produk EV** (bagian atas tab) diisi manual di `docs/data/ev_spotlight.json` — tidak bergantung periode:
foto di `docs/ev/<produk>/`, deck presentasi di `docs/files/`. Fitur bertanda `"verifikasi"` tampil kuning
(belum ada di brosur resmi). Saat ini berisi Yamaha NMAX E (brosur Yamaha Scooters 2027 + foto resmi).

## Mode presentasi 16:9

Tombol **▶ Presentasi** di header menampilkan periode terpilih sebagai 5 slide 16:9 (sampul, ringkasan, highlight,
rilis Indonesia, special case EV) dengan animasi. Navigasi: ← → / spasi / klik, `F` layar penuh, `Esc` keluar.
**Export PDF** di mode ini mencetak 5 halaman 16:9 (pilih "Simpan sebagai PDF" di dialog cetak).
Deck NMAX E versi ringkas (9 slide) bisa diputar dari tab EV lewat tombol "Presentasikan deck".
