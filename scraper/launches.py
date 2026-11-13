"""
Rilis motor di Indonesia + perbandingan dengan produk sebelumnya.

Alur:
- is_launch(d)         : artikel tersimpan (dict) yang memberitakan peluncuran motor di Indonesia.
- analyze(d, text, cfg): dari isi lengkap artikel → nama model, spesifikasi (harga/mesin/tenaga/torsi),
                         harga versi sebelumnya bila disebut, dan kalimat-kalimat pembanding.
- build(period_dir, out): gabungkan artikel peluncuran dari semua periode menjadi docs/data/launches.json,
                         satukan liputan yang sama dari beberapa blog, dan cari rilis sebelumnya untuk model
                         yang sama di data yang ada.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Deteksi
# --------------------------------------------------------------------------- #
LAUNCH_VERB = re.compile(
    r"(?<![a-z])(rilis|merilis|dirilis|resmi|meluncur|meluncurkan|luncurkan|diluncurkan|launching|hadir|debut|"
    r"dibanderol|diperkenalkan|perkenalkan|memperkenalkan|mengaspal|unjuk gigi)(?![a-z])", re.I)
SPECULATIVE = re.compile(
    r"\?|(?<![a-z])(bakal|akan|apakah|kapan|mungkin|rumor|bocoran|spyshot|spy shot|paten|terawangan|prediksi|"
    r"teaser|segera|siap-siap|jelang)(?![a-z])", re.I)
NOT_PRODUCT = re.compile(
    r"(?<![a-z])(motogp|moto2|moto3|wsbk|worldsbk|arrc|tim|team|line-?up|formasi|pembalap|rider|aplikasi|app|y-on|"
    r"mudik|pendaftaran|undangan|jadwal|event|ride the hype|kontes|festival|turnamen|lomba|touring|komunitas|"
    r"dealer|diler|bengkel|servis|layanan|promo|diskon|cashback|program|kredit|helm|apparel|jaket|oli|ban|aki|"
    r"sparepart|suku cadang|aksesori|aksesoris|sepeda listrik|mobil|suv|mpv)(?![a-z])", re.I)


def is_launch(d: dict) -> bool:
    t = d.get("title", "")
    return ("Indonesia" in (d.get("countries") or [])
            and "Peluncuran Produk" in (d.get("categories") or [])
            and (d.get("categories") or [""])[0] != "Racing & Motorsport"
            and bool(d.get("brands"))
            and bool(LAUNCH_VERB.search(t))
            and not SPECULATIVE.search(t)
            and not NOT_PRODUCT.search(t))


# --------------------------------------------------------------------------- #
# Nama model
# --------------------------------------------------------------------------- #
BRAND_ALIASES = {"YIMM": "Yamaha", "YAMAHA INDONESIA": "Yamaha", "AHM": "Honda", "ASTRA HONDA": "Honda",
                 "SIM": "Suzuki", "KMI": "Kawasaki", "PIAGGIO INDONESIA": "Vespa / Piaggio"}
SKIP = set("""indonesia rilis merilis dirilis resmi resmikan luncurkan meluncurkan diluncurkan launching new all the
generasi kedua ketiga perkenalkan memperkenalkan sang hadirkan hadir kembali breaking hot motor terbaru baru versi lini
moge gebrak deretan jajaran trio duo sederet seri special spesial edisi edition limited warna kelir pilihan jual
menjual penyegaran segarkan mengaspal tantang update varian siap livery era skutik""".split())
STOP = set("""terbaru baru rilis resmi dirilis meluncur hadir dengan dan untuk di ke dari versi edisi edition warna
color colour livery special spesial varian model year tahun makin lebih jadi kini tampil mulai harga dibanderol
seharga cuma hanya jutaan juta murah mahal pakai bawa punya dapat yang ini itu bikin intip detail resmi update
indonesia generasi kedua debut tipe type series jelang saat musim gaya""".split())
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-+.']*")


def _brand_tokens(brand: str) -> list[str]:
    toks = [x.strip() for x in brand.split("/")]
    toks += [k for k, v in BRAND_ALIASES.items() if v == brand]
    if brand == "BMW Motorrad":
        toks.append("BMW")
    return sorted(set(toks), key=len, reverse=True)


def model_name(title: str, brand: str) -> tuple[str, str]:
    """('Yamaha X-MAX 250', 'yamaha|xmax250'). Kunci dipakai untuk mencocokkan rilis model yang sama."""
    t = re.sub(r"[‘’“”\"]", " ", title)
    pos = None
    main = [x.strip() for x in brand.split("/")] + (["BMW"] if brand == "BMW Motorrad" else [])
    for group in (main, [k for k, v in BRAND_ALIASES.items() if v == brand]):  # nama merek dulu, baru singkatan (AHM, YIMM)
        for b in group:
            m = re.search(r"(?<![A-Za-z])" + re.escape(b) + r"(?![A-Za-z])", t, re.I)
            if m and (pos is None or m.end() < pos):
                pos = m.end()
        if pos is not None:
            break
    own_brand = pos is not None
    words: list[str] = []
    if pos is None:  # merek induk tidak tertulis (mis. Keeway, SYM): ambil frasa sebelum kata kerja peluncuran
        for clause in re.split(r"[:;!?|…]|\.\.", t):
            m = LAUNCH_VERB.search(clause)
            if m:
                words = [w for w in TOKEN.findall(clause[:m.start()]) if w.lower() not in SKIP][-5:]
                if words:
                    name = " ".join(words)
                    return name, f"{brand.lower()}|{re.sub(r'[^a-z0-9]', '', name.lower())}"
        m = LAUNCH_VERB.search(t)
        pos = m.end() if m else None
    if pos is not None:
        rest = t[pos:]
        rest = re.split(r"\s[–—-]\s|[,:;!?|…()&]|\.\.|\s\.\s|\sdan\s", rest)[0]
        brand_words = {w.lower() for b in _brand_tokens(brand) for w in b.split()}
        started = False
        for tok in TOKEN.findall(rest):
            low = tok.lower().strip(".'")
            if not started and (low in SKIP or low in brand_words):
                continue
            if re.fullmatch(r"(20\d\d|my20\d\d|my\d\d)", low) or (started and low in STOP):
                break
            if not started and not (tok[0].isupper() or any(c.isdigit() for c in tok)):
                continue
            started = True
            words.append(tok.strip(".'"))
            if len(words) >= 4:
                break
    model = " ".join(words)
    short_brand = brand.split(" / ")[0] if brand != "Vespa / Piaggio" else ("Vespa" if "vespa" in t.lower() else "Piaggio")
    display = (f"{short_brand} {model}" if own_brand else model) if model else title
    key = re.sub(r"[^a-z0-9]", "", model.lower())
    return display, f"{brand.lower()}|{key}" if key else ""


# --------------------------------------------------------------------------- #
# Spesifikasi
# --------------------------------------------------------------------------- #
_NUM = r"(\d{1,3}(?:[.,]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
PRICE = re.compile(r"(?:\brp\.?\s?)" + _NUM + r"(?:\s?(miliar|juta(?:an)?|jt|ribu|rb))?(?![a-z0-9])"
                   r"|" + _NUM + r"\s?(miliar|juta(?:an)?|jt)(?:\s?rupiah)?(?![a-z])", re.I)
CC = re.compile(r"(?<![\d.,])(\d{2,4}(?:[.,]\d{1,2})?)\s?cc(?![a-z])", re.I)
POWER = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s?(ps|hp|dk|kw)(?![a-z])", re.I)
TORQUE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s?nm(?![a-z])", re.I)
PRICE_CTX = re.compile(r"harga|dibanderol|banderol|dijual|seharga|otr|mulai|rp", re.I)


def _to_float(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):          # 37.080.000 / 37.080.000,00
        return float(s.split(",")[0].replace(".", ""))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):                     # 37,080,000
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))                              # 27,8 / 149.9


def _price_value(m: re.Match) -> float | None:
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    try:
        v = _to_float(num)
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith("miliar"):
        v *= 1e9
    elif unit.startswith("ju") or unit == "jt":
        v *= 1e6
    elif unit in ("ribu", "rb"):
        v *= 1e3
    return v if 5e6 <= v <= 3e9 else None   # di luar rentang harga motor → abaikan (aksesori, denda, dll.)


def _first_price(text: str) -> float | None:
    for m in PRICE.finditer(text):
        v = _price_value(m)
        if v:
            return v
    return None


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "")
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+(?=[A-Z0-9“\"(])", text) if 25 <= len(s.strip()) <= 400]


def _first(rx: re.Pattern, text: str, lo: float, hi: float, unit: str | None = None) -> str | None:
    for m in rx.finditer(text):
        try:
            v = _to_float(m.group(1))
        except ValueError:
            continue
        if lo <= v <= hi:
            u = unit or m.group(2)
            return f"{m.group(1)} {u.upper() if u.lower() in ('ps', 'hp', 'dk', 'kw') else u}"
    return None


COMPARE_STRONG = re.compile(
    r"(?<![a-z])(sebelumnya|sebelum ini|pendahulu|pendahulunya|versi lama|model lama|generasi lama|generasi sebelumnya|"
    r"versi sebelumnya|model sebelumnya|tipe sebelumnya|dibanding|dibandingkan|ketimbang|daripada|selisih|"
    r"lebih murah|lebih mahal|naik rp|turun rp|naik sekitar|naik sebesar|turun sekitar|tidak berubah|tak berubah|"
    r"masih sama|tetap sama|sama seperti|masih mengandalkan|masih menggunakan|masih memakai|outgoing)(?![a-z])", re.I)
COMPARE_WEAK = re.compile(
    r"(?<![a-z])(kini|sekarang|perubahan|ubahan|berubah|diperbarui|pembaruan|tambahan|ditambah|ditambahkan|bertambah|"
    r"berkurang|lebih ringan|lebih bertenaga|lebih besar|lebih lega|lebih irit|melengkapi|menggantikan|mengganti)(?![a-z])", re.I)
LEAD = re.compile(r"^\s*(?:[\w.]+\.com\s*[–—-]\s*)?(?:(?:bro|sob|sobat|cak|cakk+|bro sekalian|sobat tmcblog)[\w ]{0,20}?[,.!]\s*)*", re.I)
INTRO = re.compile(r"(?<![a-z])(kembali (memberikan|merilis|meluncurkan|menghadirkan|hadir)|baru saja (merilis|meluncurkan|memberikan)|"
                   r"secara resmi (merilis|meluncurkan|memperkenalkan))(?![a-z])", re.I)


def _clean_sentence(s: str) -> str:
    s = LEAD.sub("", s).strip()
    return s[:1].upper() + s[1:] if s else s


def _similar(a: str, b: str) -> bool:
    wa, wb = set(re.findall(r"[a-z0-9]{3,}", a.lower())), set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) > 0.55
PREV_PRICE = re.compile(
    r"(?:sebelumnya|semula|sebelum ini|versi lama|model lama|generasi lama|generasi sebelumnya|versi sebelumnya|"
    r"model sebelumnya|pendahulu(?:nya)?)[^.]{0,45}?(?:dibanderol|dijual|seharga|harga(?:nya)?|banderol)\s*(?:di\s*)?"
    r"(?:angka\s*|kisaran\s*|sekitar\s*)?(?:rp\.?\s?)" + _NUM + r"\s?(miliar|juta(?:an)?|jt|ribu|rb)?"
    r"|(?<![a-z])dari\s+(?:rp\.?\s?)" + _NUM + r"\s?(miliar|juta(?:an)?|jt|ribu|rb)?\s+(?:menjadi|jadi|ke)\s", re.I)
DELTA_PRICE = re.compile(r"(naik|turun|lebih mahal|lebih murah|selisih)\s+(?:sekitar|sebesar|hanya|cuma)?\s*(?:rp\.?\s?)"
                         + _NUM + r"\s?(miliar|juta(?:an)?|jt|ribu|rb)?", re.I)


def _money(num: str, unit: str | None) -> float | None:
    try:
        v = _to_float(num)
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith("miliar"):
        v *= 1e9
    elif unit.startswith("ju") or unit == "jt":
        v *= 1e6
    elif unit in ("ribu", "rb"):
        v *= 1e3
    return v


def analyze(d: dict, text: str, brand_hint: str | None = None) -> dict:
    title = d.get("title", "")
    brand = brand_hint or (d.get("brands") or [""])[0]
    display, key = model_name(title, brand)
    body = f"{title}. {text or ''}"
    sents = _sentences(body)

    title_price = _first_price(title)
    text_price = None
    for s in sents[1:]:
        if PRICE_CTX.search(s):
            text_price = _first_price(s)
            if text_price:
                break
    # harga di judul sering dibulatkan ("37 jutaan"); pakai angka di isi bila masih sekitar harga judul
    if title_price and text_price and abs(text_price - title_price) / title_price <= 0.12:
        price = text_price
    else:
        price = title_price or text_price
    specs = {
        "price": price,
        "engine": _first(CC, body, 49, 2500, "cc"),
        "power": _first(POWER, body, 3, 250),
        "torque": _first(TORQUE, body, 3, 250, "Nm"),
    }

    prev_price = delta = None
    for s in sents:
        if prev_price is None:
            m = PREV_PRICE.search(s)
            if m:
                v = _money(m.group(1), m.group(2)) if m.group(1) else _money(m.group(3), m.group(4))
                if v and 5e6 <= v <= 3e9 and v != price:
                    prev_price = v
        if delta is None:
            m = DELTA_PRICE.search(s)
            if m:
                v = _money(m.group(2), m.group(3))
                if v and 5e4 <= v <= 1e8:
                    delta = -v if m.group(1).lower() in ("turun", "lebih murah") else v

    sents = [_clean_sentence(s) for s in sents[1:]]          # [0] = judul
    strong = [s for s in sents if COMPARE_STRONG.search(s)]
    weak = [s for s in sents if s not in strong and COMPARE_WEAK.search(s) and not INTRO.search(s)]
    compare: list[str] = []
    for s in strong + weak:
        if len(s) >= 30 and not any(_similar(s, c) for c in compare):
            compare.append(s)
        if len(compare) >= 4:
            break
    return {"model": display, "key": key, "specs": specs,
            "previous_from_article": {"price": prev_price, "price_delta": delta},
            "compare": compare, "analyzed_at": datetime.now().isoformat(timespec="seconds")}


# --------------------------------------------------------------------------- #
# Gabungkan & cari pembanding
# --------------------------------------------------------------------------- #
def _keys_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    ba, ka = a.split("|", 1)
    bb, kb = b.split("|", 1)
    if ba != bb or len(ka) < 3 or len(kb) < 3:
        return False
    return ka == kb or ka.startswith(kb) or kb.startswith(ka)


def _days(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()) / 86400


GROUP_DAYS = 14  # liputan model yang sama dalam 2 minggu dianggap satu rilis


def build(period_dir: Path, out_path: Path) -> list[dict]:
    arts = []
    for p in sorted(period_dir.glob("*.json")):
        for a in json.loads(p.read_text(encoding="utf-8"))["articles"]:
            if a.get("launch") and is_launch(a):
                arts.append(a)
    arts.sort(key=lambda a: a["published"])

    # 1) satukan liputan model yang sama dalam rentang GROUP_DAYS (mis. Iwan Banaran + TMC Blog)
    groups: list[dict] = []
    for a in arts:
        L = a["launch"]
        g = next((g for g in reversed(groups)
                  if _days(g["date"], a["published"]) <= GROUP_DAYS and (_keys_match(g["key"], L["key"]) or g["model"] == L["model"])), None)
        if g is None:
            g = {"id": a["id"], "date": a["published"], "brand": a["brands"][0], "model": L["model"], "key": L["key"],
                 "specs": dict(L["specs"]), "previous_from_article": dict(L["previous_from_article"]),
                 "compare": [], "articles": [], "image": a.get("image"), "highlight": False}
            groups.append(g)
        g["articles"].append({"title": a["title"], "url": a["url"], "source": a["source"], "published": a["published"]})
        g["highlight"] = g["highlight"] or bool(a.get("highlight"))
        g["image"] = g["image"] or a.get("image")
        if len(L["model"]) > len(g["model"]) and L["key"]:
            g["model"], g["key"] = L["model"], L["key"]
        for k, v in L["specs"].items():
            g["specs"][k] = g["specs"].get(k) or v
        for k, v in L["previous_from_article"].items():
            g["previous_from_article"][k] = g["previous_from_article"].get(k) or v
        for s in L["compare"]:
            if not any(_similar(s, c) for c in g["compare"]) and len(g["compare"]) < 6:
                g["compare"].append(s)

    # 2) rilis sebelumnya untuk model yang sama (di data yang ada)
    for i, g in enumerate(groups):
        prev = next((p for p in reversed(groups[:i]) if _keys_match(p["key"], g["key"]) and _days(p["date"], g["date"]) > GROUP_DAYS), None)
        g["previous_release"] = None if prev is None else {
            "id": prev["id"], "date": prev["date"], "model": prev["model"], "specs": prev["specs"],
            "url": prev["articles"][0]["url"], "title": prev["articles"][0]["title"]}
        pa = g["previous_from_article"]
        if g["specs"].get("price") and not pa.get("price") and pa.get("price_delta"):
            pa["price"] = g["specs"]["price"] - pa["price_delta"]

    groups.sort(key=lambda g: g["date"], reverse=True)
    out_path.write_text(json.dumps({"updated_at": datetime.now().isoformat(timespec="seconds"), "launches": groups},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    return groups
