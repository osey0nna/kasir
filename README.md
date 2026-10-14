# Kasir Soft 🌸🍵

Aplikasi kasir sederhana (Flask + SQLite) bertema soft pink & matcha.

## Fitur
- **Kasir**: pilih produk, keranjang, bayar, kembalian otomatis, stok berkurang.
- **Produk (CRUD)**: tambah, lihat, cari, edit, hapus.
- **Riwayat**: daftar transaksi, struk, hapus transaksi (stok dikembalikan).
- **Download website**: tombol "Download ZIP" di navbar (`/download`) membuat zip source code web ini sendiri.

## Jalankan lokal
```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python kasir_app.py
```
Buka http://127.0.0.1:5000 — database dibuat otomatis di `instance/kasir.db`.

## Deploy ke Vercel
```bash
npm i -g vercel
vercel          # preview
vercel --prod   # production
```
Atau push ke GitHub lalu import repo di dashboard Vercel (tanpa setting tambahan).
Opsional: set Environment Variable `SECRET_KEY`.

### Catatan penting: SQLite di Vercel
Filesystem Vercel read-only, jadi database otomatis dibuat di `/tmp/kasir.db`
dan di-seed dengan data contoh saat cold start. **Data bersifat sementara**:
bisa hilang saat instance di-recycle/redeploy dan tidak dibagi antar instance.
Cocok untuk demo/tugas. Untuk data permanen, ganti ke database eksternal
(Vercel Postgres/Neon, Turso, Supabase) — logika SQL ada di `kasir_app.py`.

### Static file (CSS/JS)
Flask melayani `/static/*` dengan path absolut dan `vercel.json` memastikan folder
`static/` & `templates/` ikut ter-bundle, jadi tidak ada masalah 404 di production.
