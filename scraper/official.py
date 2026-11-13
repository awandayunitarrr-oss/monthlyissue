"""
Data pembanding dari sumber resmi.

1) Situs resmi Yamaha Indonesia (halaman produk publik): tipe, harga OTR Jakarta, warna (nama + kode warna)
   dan gambar per warna. Disimpan sebagai riwayat di docs/data/official/yamaha/<slug>.json setiap kali
   scraper berjalan, sehingga versi sebelum sebuah rilis tetap tercatat.
2) Internet Archive (web.archive.org): tampilan halaman resmi Yamaha pada tanggal tertentu, untuk rilis yang
   terjadi sebelum riwayat sendiri mulai dicatat.
3) Isian manual tim (manual/pembanding.csv): untuk merek lain (mis. Honda), atau untuk mengoreksi data otomatis.

Merek lain sengaja tidak diambil dari situs resminya: datanya hanya tersedia lewat API internal
yang tidak disediakan untuk umum.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

YAMAHA = "https://www.yamaha-motor.co.id"
ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "docs" / "data" / "official"
MANUAL_CSV = ROOT / "manual" / "pembanding.csv"
MANUAL_SPEC_CSV = ROOT / "manual" / "spesifikasi.csv"


def _price(text: str) -> float | None:
    m = re.search(r"rp\.?\s?(\d{1,3}(?:\.\d{3})+)", text or "", re.I)
    return float(m.group(1).replace(".", "")) if m else None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# --------------------------------------------------------------------------- #
# Yamaha
# --------------------------------------------------------------------------- #
def parse_yamaha(html: bytes | str, url: str) -> dict | None:
    """Halaman produk Yamaha → {name, url, variants:[{name, price, colors:[{name, hex, image}]}]}."""
    soup = BeautifulSoup(html, "lxml")
    og = soup.find("meta", attrs={"property": "og:title"})
    name = og["content"].strip() if og and og.get("content") else ""
    variants = []
    for div in soup.select("div.sec2-div"):
        imgs = [urljoin(url, i.get("src") or i.get("data-src") or "") for i in div.select("img.sec2-swiper-img")]
        colors = []
        for k, c in enumerate(div.select("div.sec2-color-div")):
            hexm = re.search(r"#[0-9a-fA-F]{3,8}", c.get("style", ""))
            colors.append({"name": (c.get("data-src") or "").strip(), "hex": hexm.group(0) if hexm else None,
                           "image": imgs[k] if k < len(imgs) else None, "new": None})
        tags = [p.get_text(" ", strip=True) for p in div.select("p.sec2-color-tag3")]
        vname = next((t for t in tags if not _price(t)), "") or next(
            (p.get_text(" ", strip=True) for p in div.select("p.sec2-color-tag2")), "")
        price = next((_price(t) for t in tags if _price(t)), None)
        if vname or colors:
            variants.append({"name": vname.replace('"', "").strip() or "Standar", "price": price,
                             "colors": [c for c in colors if c["name"]], "notes": []})
    if not variants:  # tata letak lain (mis. arsip lama): ambil harga per varian dari data terstruktur
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
            except (ValueError, TypeError):
                continue
            for item in data if isinstance(data, list) else [data]:
                for v in item.get("hasVariant", []) if isinstance(item, dict) else []:
                    off = v.get("offers") or {}
                    try:
                        price = float(off.get("price")) if off.get("price") else None
                    except (TypeError, ValueError):
                        price = None
                    variants.append({"name": v.get("name", ""), "price": price, "colors": [], "notes": []})
                if isinstance(item, dict) and item.get("@type") == "ProductGroup" and not name:
                    name = item.get("name", "")
    spec_lines = []
    for tr in soup.select("table.sec4-table tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) >= 2:
            spec_lines.append(f"{tds[0]} : {tds[-1]}")
    from launches import spec_table_from_lines  # noqa: PLC0415
    spec_table = spec_table_from_lines(spec_lines)
    if not variants and not spec_table:
        return None
    # gabungkan blok dengan nama tipe sama (satu blok per warna di beberapa halaman)
    merged: dict[str, dict] = {}
    for v in variants:
        k = v["name"].upper()
        if k in merged:
            merged[k]["colors"] += [c for c in v["colors"] if c["name"] not in {x["name"] for x in merged[k]["colors"]}]
            merged[k]["price"] = merged[k]["price"] or v["price"]
        else:
            merged[k] = v
    return {"name": name, "url": url, "variants": list(merged.values()), "spec_table": spec_table}


def yamaha_product_urls(get) -> list[str]:
    urls: set[str] = set()
    pages = [YAMAHA + "/"] + [f"{YAMAHA}/products/category/{c}/" for c in
                               ("matic", "maxi-yamaha", "classy", "sport", "moped", "off-road")]
    for page in pages:
        r = get(page)
        if r is None:
            continue
        for m in re.finditer(r'href="((?:https?://www\.yamaha-motor\.co\.id)?/product/([a-z0-9-]+)/?)', r.text):
            urls.add(f"{YAMAHA}/product/{m.group(2)}/")
    return sorted(urls)


def _same(a: dict, b: dict) -> bool:
    sig = lambda d: [(v["name"], v["price"], tuple(c["name"] for c in v["colors"])) for v in d["variants"]]  # noqa: E731
    return sig(a) == sig(b) and (a.get("spec_table") or {}) == (b.get("spec_table") or {})


def _store_path(slug: str) -> Path:
    return STORE / "yamaha" / f"{slug}.json"


def record(slug: str, entry: dict) -> bool:
    """Tambahkan entri ke riwayat produk bila isinya berubah. True bila ada perubahan."""
    p = _store_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"slug": slug, "history": []}
    hist = data["history"]
    same_day = next((h for h in hist if h["date"][:10] == entry["date"][:10] and h["source"] == entry["source"]), None)
    if same_day is not None:
        if _same(same_day, entry):
            return False
        hist.remove(same_day)  # catatan hari yang sama diperbarui (mis. setelah pembaca diperluas)
    same_before = [h for h in hist if h["date"] <= entry["date"]]
    if same_before and _same(same_before[-1], entry) and entry["source"] == "official":
        return False
    hist.append(entry)
    hist.sort(key=lambda h: h["date"])
    data.update({"name": entry.get("name") or data.get("name"), "url": entry["url"]})
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def snapshot_yamaha(get) -> int:
    """Simpan kondisi terkini semua halaman produk Yamaha (dipanggil di setiap update)."""
    n = 0
    today = datetime.now().strftime("%Y-%m-%d")
    for url in yamaha_product_urls(get):
        r = get(url)
        if r is None:
            continue
        d = parse_yamaha(r.content, url)
        if d:
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            n += record(slug, {**d, "date": today, "source": "official"})
    return n


def wayback(get, url: str, when: datetime, before: bool = True) -> dict | None:
    """Halaman resmi sebagaimana diarsipkan Internet Archive sekitar tanggal `when`."""
    ts = (when - timedelta(days=2) if before else when + timedelta(days=21)).strftime("%Y%m%d")
    r = get(f"https://archive.org/wayback/available?url={url}&timestamp={ts}")
    if r is None:
        return None
    try:
        snap = r.json()["archived_snapshots"]["closest"]
    except (ValueError, KeyError, TypeError):
        return None
    snap_dt = datetime.strptime(snap["timestamp"][:8], "%Y%m%d")
    w = when.replace(tzinfo=None)
    if before and not (w - timedelta(days=400) <= snap_dt < w - timedelta(days=1)):
        return None
    if not before and not (w <= snap_dt <= w + timedelta(days=120)):
        return None
    raw = f"https://web.archive.org/web/{snap['timestamp']}id_/{url}"
    rr = get(raw)
    if rr is None:
        return None
    d = parse_yamaha(rr.content, url)
    if not d:
        return None
    return {**d, "date": snap_dt.strftime("%Y-%m-%d"), "source": "wayback", "archive_url": snap["url"]}


def match_yamaha(model: str) -> str | None:
    """Cocokkan nama model rilis ke slug produk resmi yang sudah tercatat (atau dikenal dari daftar produk)."""
    key = _norm(re.sub(r"(?i)^yamaha\s+", "", model))
    if len(key) < 3:
        return None
    best = None
    for p in (STORE / "yamaha").glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        cands = {_norm(d["slug"]), _norm(re.sub(r"(?i)^yamaha\s+", "", d.get("name") or ""))}
        for c in cands:
            if c and (c == key or c.startswith(key) or key.startswith(c)):
                score = len(c) if key.startswith(c) or c == key else len(key)
                if best is None or score > best[0]:
                    best = (score, d["slug"])
    return best[1] if best else None


def yamaha_compare(get, model: str, launch_date: str) -> tuple[dict | None, dict | None]:
    """(sebelum, sesudah) rilis untuk model Yamaha: dari riwayat sendiri, atau Internet Archive."""
    slug = match_yamaha(model)
    if not slug:
        return None, None
    data = json.loads(_store_path(slug).read_text(encoding="utf-8"))
    when = datetime.fromisoformat(launch_date)
    day = when.strftime("%Y-%m-%d")
    hist = data["history"]
    prev = next((h for h in reversed(hist) if h["date"] < day), None)
    now = next((h for h in hist if h["date"] >= day), None)
    url = data["url"]
    if prev is None:
        prev = wayback(get, url, when, before=True)
        if prev:
            record(slug, prev)
    if now is None or now["date"] > (when + timedelta(days=120)).strftime("%Y-%m-%d"):
        snap = wayback(get, url, when, before=False)
        if snap:
            record(slug, snap)
        now = snap
    return prev, now


# --------------------------------------------------------------------------- #
# Isian manual
# --------------------------------------------------------------------------- #
def load_manual() -> list[dict]:
    """manual/pembanding.csv → daftar {brand, model, key, year, variants}."""
    if not MANUAL_CSV.exists():
        return []
    groups: dict[tuple, dict] = {}
    with MANUAL_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("model") or not row.get("tahun") or row.get("merek", "").startswith("#"):
                continue
            try:
                year = int(row["tahun"])
            except ValueError:
                continue
            k = (row.get("merek", "").lower(), _norm(row["model"]), year)
            g = groups.setdefault(k, {"brand": row.get("merek", ""), "model": row["model"], "key": k[1], "year": year,
                                      "variants": [], "source": "manual", "date": f"{year}-01-01", "url": None})
            colors = [c.strip() for c in row.get("warna", "").split(";") if c.strip()]
            images = [c.strip() for c in row.get("gambar", "").split(";")]
            price = row.get("harga", "").replace(".", "").replace(",", "").replace("Rp", "").strip()
            g["variants"].append({
                "name": row.get("tipe") or "Standar",
                "price": float(price) if price.isdigit() else None,
                "colors": [{"name": c, "hex": None, "new": None, "image": images[i] if i < len(images) and images[i] else None}
                           for i, c in enumerate(colors)],
                "notes": [row["catatan"]] if row.get("catatan") else []})
    if MANUAL_SPEC_CSV.exists():
        from launches import spec_from_line  # noqa: PLC0415
        with MANUAL_SPEC_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                if not row.get("model") or not row.get("tahun") or not row.get("spesifikasi") or row.get("merek", "").startswith("#"):
                    continue
                try:
                    year = int(row["tahun"])
                except ValueError:
                    continue
                k = (row.get("merek", "").lower(), _norm(row["model"]), year)
                g = groups.setdefault(k, {"brand": row.get("merek", ""), "model": row["model"], "key": k[1], "year": year,
                                          "variants": [], "source": "manual", "date": f"{year}-01-01", "url": None})
                hit = spec_from_line(f"{row['spesifikasi']} : {row.get('nilai', '')}")
                g.setdefault("spec_table", {})[hit[0] if hit else row["spesifikasi"]] = row.get("nilai", "")
    return list(groups.values())


def manual_for(manual: list[dict], brand: str, model: str, year: int) -> tuple[dict | None, dict | None]:
    """(pembanding tahun sebelumnya, data tahun rilis) dari isian manual untuk model ini."""
    key = _norm(re.sub(r"(?i)^(" + re.escape(brand.split(" / ")[0]) + r")\s+", "", model))
    b = brand.split(" / ")[0].lower()

    def hit(m: dict) -> bool:
        if m["brand"] and not b.startswith(m["brand"].lower()) and not m["brand"].lower().startswith(b):
            return False
        return len(m["key"]) >= 3 and (m["key"] == key or key.startswith(m["key"]) or m["key"].startswith(key))

    mine = [m for m in manual if hit(m)]
    prev = max((m for m in mine if m["year"] < year), key=lambda m: m["year"], default=None)
    now = next((m for m in mine if m["year"] == year), None)
    return prev, now
