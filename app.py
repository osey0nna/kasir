import io
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_VERCEL = bool(os.environ.get("VERCEL"))

# Vercel: filesystem read-only kecuali /tmp -> SQLite wajib di /tmp (sifatnya sementara).
DB_PATH = os.environ.get("DATABASE_PATH") or (
    "/tmp/kasir.db" if IS_VERCEL else os.path.join(BASE_DIR, "instance", "kasir.db")
)

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),      # path absolut -> aman di Vercel
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_url_path="/static",
)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ganti-secret-key-ini")

WIB = timezone(timedelta(hours=7))

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total INTEGER NOT NULL,
    paid INTEGER NOT NULL,
    change INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transaction_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name TEXT NOT NULL,
    price INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    subtotal INTEGER NOT NULL
);
"""

SEED = [
    ("Matcha Latte", 22000, 40),
    ("Strawberry Milk", 20000, 35),
    ("Iced Americano", 18000, 50),
    ("Matcha Cookies", 15000, 25),
    ("Strawberry Cheesecake", 28000, 12),
    ("Mochi", 12000, 30),
]


def now():
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    fresh = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    if fresh:
        conn.executemany(
            "INSERT INTO products (name, price, stock, created_at) VALUES (?,?,?,?)",
            [(n, p, s, now()) for n, p, s in SEED],
        )
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        if not os.path.exists(DB_PATH):  # first run / cold start di Vercel
            init_db()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.template_filter("rupiah")
def rupiah(value):
    return "Rp " + f"{int(value or 0):,}".replace(",", ".")


# ---------------------------------------------------------------- Kasir (POS)
@app.get("/")
def kasir():
    products = get_db().execute(
        "SELECT * FROM products WHERE stock > 0 ORDER BY name"
    ).fetchall()
    return render_template("kasir.html", products=products)


@app.post("/api/checkout")
def checkout():
    data = request.get_json(silent=True) or {}
    try:
        paid = int(data.get("paid") or 0)
        wanted = {}
        for it in data.get("items") or []:
            pid, qty = int(it["id"]), int(it["qty"])
            if qty <= 0:
                raise ValueError
            wanted[pid] = wanted.get(pid, 0) + qty
    except (KeyError, TypeError, ValueError):
        return jsonify(ok=False, error="Data keranjang tidak valid."), 400
    if not wanted:
        return jsonify(ok=False, error="Keranjang masih kosong."), 400

    db = get_db()
    lines, total = [], 0
    for pid, qty in wanted.items():
        p = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if p is None:
            return jsonify(ok=False, error="Ada produk yang sudah tidak tersedia."), 400
        if p["stock"] < qty:
            return jsonify(ok=False, error=f"Stok {p['name']} tidak cukup (sisa {p['stock']})."), 400
        sub = p["price"] * qty  # harga selalu dari database, bukan dari klien
        total += sub
        lines.append((p, qty, sub))
    if paid < total:
        return jsonify(ok=False, error="Uang bayar kurang dari total."), 400

    try:
        cur = db.execute(
            "INSERT INTO transactions (total, paid, change, created_at) VALUES (?,?,?,?)",
            (total, paid, paid - total, now()),
        )
        tid = cur.lastrowid
        for p, qty, sub in lines:
            db.execute(
                "INSERT INTO transaction_items (transaction_id, product_id, product_name, price, qty, subtotal)"
                " VALUES (?,?,?,?,?,?)",
                (tid, p["id"], p["name"], p["price"], qty, sub),
            )
            db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, p["id"]))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        return jsonify(ok=False, error="Gagal menyimpan transaksi."), 500
    return jsonify(ok=True, redirect=url_for("struk", tid=tid))


# ---------------------------------------------------------------- Produk CRUD
def parse_product_form():
    name = (request.form.get("name") or "").strip()
    errors = []
    if not name:
        errors.append("Nama produk wajib diisi.")
    try:
        price = int(request.form.get("price", ""))
        stock = int(request.form.get("stock", ""))
        if price < 0 or stock < 0:
            raise ValueError
    except ValueError:
        errors.append("Harga dan stok harus berupa angka 0 atau lebih.")
        price = stock = 0
    return {"name": name[:80], "price": price, "stock": stock}, errors


@app.get("/produk")
def produk():
    q = (request.args.get("q") or "").strip()
    db = get_db()
    if q:
        rows = db.execute(
            "SELECT * FROM products WHERE name LIKE ? ORDER BY id DESC",
            (f"%{q}%",),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("produk.html", products=rows, q=q)


@app.route("/produk/tambah", methods=["GET", "POST"])
def produk_tambah():
    if request.method == "POST":
        data, errors = parse_product_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("produk_form.html", product=data, mode="tambah")
        db = get_db()
        db.execute(
            "INSERT INTO products (name, price, stock, created_at) VALUES (?,?,?,?)",
            (data["name"], data["price"], data["stock"], now()),
        )
        db.commit()
        flash("Produk berhasil ditambahkan.", "success")
        return redirect(url_for("produk"))
    return render_template("produk_form.html", product={}, mode="tambah")


@app.route("/produk/<int:pid>/edit", methods=["GET", "POST"])
def produk_edit(pid):
    db = get_db()
    p = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if p is None:
        abort(404)
    if request.method == "POST":
        data, errors = parse_product_form()
        if errors:
            for e in errors:
                flash(e, "error")
            data["id"] = pid
            return render_template("produk_form.html", product=data, mode="edit")
        db.execute(
            "UPDATE products SET name=?, price=?, stock=? WHERE id=?",
            (data["name"], data["price"], data["stock"], pid),
        )
        db.commit()
        flash("Produk berhasil diperbarui.", "success")
        return redirect(url_for("produk"))
    return render_template("produk_form.html", product=p, mode="edit")


@app.post("/produk/<int:pid>/hapus")
def produk_hapus(pid):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (pid,))
    db.commit()
    flash("Produk dihapus.", "success")
    return redirect(url_for("produk"))


# ---------------------------------------------------------------- Riwayat
@app.get("/transaksi")
def transaksi():
    rows = get_db().execute(
        "SELECT t.*, (SELECT COALESCE(SUM(qty),0) FROM transaction_items WHERE transaction_id = t.id) AS items"
        " FROM transactions t ORDER BY t.id DESC LIMIT 200"
    ).fetchall()
    total = sum(r["total"] for r in rows)
    return render_template("transaksi.html", rows=rows, total=total)


@app.get("/transaksi/<int:tid>")
def struk(tid):
    db = get_db()
    t = db.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
    if t is None:
        abort(404)
    items = db.execute("SELECT * FROM transaction_items WHERE transaction_id = ?", (tid,)).fetchall()
    return render_template("struk.html", t=t, items=items)


@app.post("/transaksi/<int:tid>/hapus")
def transaksi_hapus(tid):
    """Hapus transaksi + kembalikan stok produk."""
    db = get_db()
    items = db.execute("SELECT * FROM transaction_items WHERE transaction_id = ?", (tid,)).fetchall()
    for it in items:
        if it["product_id"]:
            db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (it["qty"], it["product_id"]))
    db.execute("DELETE FROM transactions WHERE id = ?", (tid,))
    db.commit()
    flash("Transaksi dihapus & stok dikembalikan.", "success")
    return redirect(url_for("transaksi"))


# ---------------------------------------------------------------- Download website (zip)
ZIP_ROOT = "kasir"
EXCLUDE_DIRS = {".git", ".vercel", "__pycache__", "instance", "venv", ".venv", "node_modules", ".idea", ".vscode"}
EXCLUDE_EXT = (".pyc", ".db", ".sqlite", ".sqlite3", ".zip")
EXCLUDE_FILES = {".env"}


@app.get("/download")
def download_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for f in sorted(files):
                if f.endswith(EXCLUDE_EXT) or f in EXCLUDE_FILES:
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, BASE_DIR).replace(os.sep, "/")
                z.write(full, f"{ZIP_ROOT}/{rel}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="kasir.zip")


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)