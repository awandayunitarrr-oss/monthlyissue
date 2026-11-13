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
    r"dibanderol|diperkenalkan|perkenalkan|memperkenalkan|mengaspal|unjuk gigi|gebrak|menggebrak|warna baru|kelir baru)(?![a-z])", re.I)
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
                 "compare": [], "articles": [], "image": a.get("image"), "highlight": False,
                 "detail": None, "prev_detail": None, "title": a["title"]}
            groups.append(g)
        g["articles"].append({"title": a["title"], "url": a["url"], "source": a["source"], "published": a["published"]})
        g["highlight"] = g["highlight"] or bool(a.get("highlight"))
        if detail_score(L.get("detail")) > detail_score(g["detail"]):
            g["detail"], g["title"] = {**L["detail"], "source": a["source"]}, a["title"]
        if detail_score(L.get("prev_detail")) > detail_score(g["prev_detail"]):
            g["prev_detail"] = L["prev_detail"]
        for k in ("prev_official", "now_official"):
            if L.get(k) and not g.get(k):
                g[k] = L[k]
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
    import official  # noqa: PLC0415 - hindari import melingkar saat modul dimuat
    manual = official.load_manual()
    for g in groups:
        if g["detail"]:
            g["detail"].setdefault("source", "artikel")
        if g["prev_detail"]:
            g["prev_detail"]["source"] = "artikel"
        align_previous(g["detail"], g["prev_detail"])
        # prioritas pembanding: isian manual > situs resmi (riwayat / Internet Archive) > artikel blog
        year = int(g["date"][:4])
        m_prev, m_now = official.manual_for(manual, g["brand"], g["model"], year)
        o_prev, o_now = g.pop("prev_official", None), g.pop("now_official", None)
        now_specs = {**((g["detail"] or {}).get("spec_table") or {}), **((o_now or {}).get("spec_table") or {}),
                     **((m_now or {}).get("spec_table") or {})}
        prev_specs = {**((g["prev_detail"] or {}).get("spec_table") or {}), **((o_prev or {}).get("spec_table") or {}),
                      **((m_prev or {}).get("spec_table") or {})}
        if o_now:
            g["detail"] = {**o_now, "intro": (g["detail"] or {}).get("intro", ""), "source": o_now["source"]}
        if m_now:
            g["detail"] = {**m_now, "intro": (g["detail"] or {}).get("intro", ""), "url": (g["detail"] or {}).get("url")}
        if o_prev:
            g["prev_detail"] = o_prev
        if m_prev:
            g["prev_detail"] = m_prev
        if m_now and not m_now.get("variants") and o_now:   # isian manual hanya spesifikasi → tetap pakai tipe/warna resmi
            g["detail"] = {**o_now, "intro": g["detail"].get("intro", ""), "source": o_now["source"]}
        if g["detail"] is not None or now_specs:
            g["detail"] = {**(g["detail"] or {"variants": [], "source": "artikel"}), "spec_table": now_specs}
        if g["prev_detail"] is not None or prev_specs:
            g["prev_detail"] = {**(g["prev_detail"] or {"variants": [], "source": "artikel"}), "spec_table": prev_specs}

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


# --------------------------------------------------------------------------- #
# Detail ala slide: tipe → harga → warna (+ gambar), untuk produk baru & sebelumnya
# --------------------------------------------------------------------------- #
from urllib.parse import quote, urljoin  # noqa: E402

from bs4 import BeautifulSoup  # noqa: E402

_CW = ("Matte|Metallic|Red|Black|White|Blue|Green|Grey|Gray|Silver|Brown|Burgundy|Yellow|Orange|Purple|Violet|Gold|"
       "Pink|Cyan|Navy|Maroon|Beige|Cream|Titanium|Bronze|Magenta|Teal|Turquoise|Merah|Hitam|Putih|Biru|Hijau|Coklat|"
       "Cokelat|Kuning|Ungu|Emas|Perak|Oranye")
COLOR_RX = re.compile(rf"(?<![\w])((?:[A-Z][a-zA-Z]+ ){{0,3}}(?:{_CW})(?: (?:{_CW}|Metallic|Matte|Pearl|Gloss|Doff|Glossy))*)(?![\w])")
COLOR_LEAD_STOP = {"Warna", "Tipe", "Type", "Dan", "Yaitu", "Pilihan", "Baru", "New", "Plus", "Ada", "Varian", "Velg",
                   "Honda", "Yamaha", "Suzuki", "Kawasaki", "Kelir", "Opsi", "Dengan", "Seperti", "Serta", "Hadir", "The",
                   "Logo", "Emblem", "Jok", "Rangka", "Bodi", "Body", "Nuansa", "Balutan", "Sentuhan", "Livery", "Edisi",
                   "Dibalut", "Berwarna", "Kini", "Untuk", "Di", "Ini", "Itu", "Yang", "Atau", "Juga", "Tersedia"}
COLOR_PREV_STOP = re.compile(r"(velg|pelek|rims?|rangka|emblem|logo|jok|knalpot|shock|suspensi|grafis|striping|aksen|"
                             r"lis|garnish|cover|dek|footstep|spion|panel)(?:\W+\w+){0,3}\W*$", re.I)
KNOWN_VARIANTS = ["RoadSync", "Smart Key", "Keyless", "CBS", "ABS", "Standard", "Standar", "Deluxe", "Premium",
                  "Special Edition", "SE", "Connected", "Turbo", "Ultimate", "Tech Max", "TechMAX", "Cyber City",
                  "Sporty", "Active", "Prestige", "Exclusive", "Limited Edition"]
VAR_RX = re.compile(r"(?<![\w])(" + "|".join(re.escape(v) for v in sorted(KNOWN_VARIANTS, key=len, reverse=True)) + r")(?![\w])"
                    r"|(?:[Tt]ipe|[Tt]ype|[Vv]arian)\s+([A-Z][\w-]*(?:\s[A-Z][\w-]*)?)")
VAR_NORM = {"standar": "Standard", "techmax": "Tech Max"}
NEW_RX = re.compile(r"(?<![a-z])(baru|anyar|new|terbaru|perdana|tambahan)(?![a-z])", re.I)
OLD_RX = re.compile(r"(?<![a-z])(sudah ada|sebelumnya|dipertahankan|warna lama|melengkapi|tetap tersedia|masih tersedia)(?![a-z])", re.I)


def _var_name(m: re.Match) -> str | None:
    v = (m.group(1) or m.group(2) or "").strip()
    if not v or v.lower() in ("baru", "new", "terbaru", "ini", "tertinggi", "terendah", "standar") and not m.group(1):
        return None
    return VAR_NORM.get(v.lower().replace(" ", ""), v)


def _colors_in(text: str) -> list[tuple[str, int]]:
    out = []
    for m in COLOR_RX.finditer(text):
        words = m.group(1).split()
        while words and words[0] in COLOR_LEAD_STOP:
            words.pop(0)
        if not words or (len(words) == 1 and words[0] in ("Matte", "Metallic")):
            continue
        if COLOR_PREV_STOP.search(re.split(r"[.!?;:,]", text[:m.start()][-40:])[-1]):
            continue
        name = " ".join(words)
        if name not in [c for c, _ in out]:
            out.append((name, m.start()))
    return out


def _img_src(img, base: str) -> str | None:
    for k in ("data-src", "data-lazy-src", "data-original", "src"):
        v = img.get(k)
        if v and not v.startswith("data:"):
            return urljoin(base, v)
    ss = img.get("srcset") or img.get("data-srcset")
    if ss:
        return urljoin(base, ss.split(",")[-1].strip().split(" ")[0])
    return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def extract_detail(html: bytes | str, url: str) -> dict:
    """Ambil tipe, harga per tipe, warna per tipe (+ gambar) dan catatan dari HTML artikel."""
    soup = BeautifulSoup(html, "lxml")
    body = (soup.find("article") or soup.find(class_=re.compile(r"entry-content|post-content|article-content|content-detail"))
            or soup.body or soup)
    for bad in body.find_all(["script", "style", "nav", "aside", "footer", "form"]):
        bad.decompose()
    for bad in body.find_all(class_=re.compile(r"related|share|comment|sidebar|baca-juga|tags?\b", re.I)):
        bad.decompose()

    images = []

    def take_img(img, variant):
        src = _img_src(img, url)
        if not src or re.search(r"logo|avatar|icon|emoji|gravatar|ads?[-_/]|banner|\.gif", src, re.I):
            return
        if any(i["src"] == src for i in images):
            return
        fig = img.find_parent("figure")
        cap = fig.find("figcaption").get_text(" ", strip=True) if fig and fig.find("figcaption") else ""
        key = _norm(" ".join([img.get("alt", ""), img.get("title", ""), cap, src.rsplit("/", 1)[-1]]))
        images.append({"src": src, "key": key, "variant": variant})

    variants: dict[str, dict] = {}
    spec_lines: list[str] = []
    order: list[str] = []
    loose: list[dict] = []
    intro = ""
    current = None

    def V(name: str) -> dict:
        k = name.upper()
        if k not in variants:
            variants[k] = {"name": name, "price": None, "colors": [], "notes": []}
            order.append(k)
        return variants[k]

    def add_colors(target: list, text: str) -> None:
        cut = OLD_RX.search(text)
        for name, pos in _colors_in(text):
            if any(c["name"].lower() == name.lower() for c in target):
                continue
            is_new = False if (cut and pos > cut.start()) else (True if NEW_RX.search(text[:pos + 1]) else None)
            target.append({"name": name, "new": is_new, "image": None})

    for el in body.find_all(["h2", "h3", "h4", "p", "li", "tr", "img"]):
        if el.name == "img":
            take_img(el, current)
            continue
        if el.name == "li" and el.find("p"):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" | " if el.name == "tr" else " ", strip=True)).strip()
        if len(text) < 3:
            continue
        spec_lines.extend(re.split(r"\s*(?:<br>|\n)\s*", el.get_text("\n", strip=True)) if el.name != "tr" else [text])
        if not intro and el.name == "p" and len(text) > 80:
            first = [s for s in _sentences(text)][:2]
            intro = _clean_sentence(" ".join(first)) if first else ""
        vars_here = [v for v in (_var_name(m) for m in VAR_RX.finditer(text)) if v]
        vars_here = list(dict.fromkeys(vars_here))
        prices = [v for v in (_price_value(m) for m in PRICE.finditer(text)) if v]
        heading = el.name in ("h2", "h3", "h4") or (len(text) < 60 and not prices)
        if heading:
            current = vars_here[0] if len(vars_here) == 1 else (None if el.name.startswith("h") else current)
        # harga
        if prices:
            if len(vars_here) >= 2 and len(prices) >= 2:
                for vn, pv in zip(vars_here, prices):
                    V(vn)["price"] = V(vn)["price"] or pv
            elif len(vars_here) == 1:
                V(vars_here[0])["price"] = V(vars_here[0])["price"] or prices[0]
            elif current:
                V(current)["price"] = V(current)["price"] or prices[0]
        # warna
        target_name = vars_here[0] if len(vars_here) == 1 else (current if not vars_here else None)
        if target_name:
            add_colors(V(target_name)["colors"], text)
            if not heading and len(text) > 40 and len(V(target_name)["notes"]) < 3:
                V(target_name)["notes"].append(_clean_sentence(text[:300]))
        else:
            add_colors(loose, text)

    out_vars = [variants[k] for k in order if variants[k]["price"] or variants[k]["colors"]]
    if not out_vars and (loose or intro):
        allp = [v for v in (_price_value(m) for m in PRICE.finditer(body.get_text(" "))) if v]
        out_vars = [{"name": "Semua tipe", "price": allp[0] if allp else None, "colors": loose, "notes": []}]
        loose = []
    # gambar per warna: 1) cocok nama warna di alt/caption/nama file, 2) urutan gambar di bawah tipe yang sama
    used = set()
    for v in out_vars:
        for c in v["colors"]:
            toks = _norm(c["name"]).split()
            best = None
            for i, im in enumerate(images):
                if i in used:
                    continue
                hit = sum(1 for t in toks if t in im["key"].split())
                if hit == len(toks) or (len(toks) >= 2 and hit >= len(toks) - 1 and hit >= 2):
                    best = i
                    if hit == len(toks):
                        break
            if best is not None:
                c["image"] = images[best]["src"]
                used.add(best)
    for v in out_vars:
        missing = [c for c in v["colors"] if not c["image"]]
        pool = [i for i, im in enumerate(images) if i not in used and im["variant"] == v["name"]]
        if missing and len(pool) >= len(missing) and len(pool) <= len(v["colors"]) + 1:
            for c, i in zip(missing, pool):
                c["image"] = images[i]["src"]
                used.add(i)
    _place_loose(out_vars, loose)
    return {"url": url, "intro": intro, "variants": out_vars, "spec_table": spec_table_from_lines(spec_lines), "loose_colors": [c["name"] for c in loose][:12],
            "n_images": len(images), "image_keys": [im["key"][-80:] for im in images[:20]]}


def _place_loose(variants: list[dict], loose: list[dict]) -> None:
    """Warna yang tak jelas tipenya: masukkan ke tipe yang namanya disebut di warna (RoadSync Matte Black)
    atau yang warna lainnya berawalan sama (Exceptional …, Phenomenal …)."""
    for c in list(loose):
        first = c["name"].split()[0].lower()
        target = next((v for v in variants if v["name"].lower() in c["name"].lower()), None) or \
            next((v for v in variants if any(x["name"].split()[0].lower() == first for x in v["colors"])), None)
        if target and not any(x["name"].lower() == c["name"].lower() for x in target["colors"]):
            target["colors"].append(c)
            loose.remove(c)


def align_previous(now: dict | None, prev: dict | None) -> None:
    """Lengkapi tipe produk sebelumnya memakai pola penamaan warna produk baru
    (mis. warna 'Exceptional …' = tipe CBS), lalu buang warna yang bukan warna bodi."""
    if not now or not prev:
        return
    loose = [{"name": n, "new": None, "image": None} for n in prev.get("loose_colors", [])]
    pv = prev["variants"]
    for c in list(loose):
        first = c["name"].split()[0].lower()
        nv = next((v for v in now["variants"] if v["name"].lower() in c["name"].lower()), None) or \
            next((v for v in now["variants"] if any(x["name"].split()[0].lower() == first for x in v["colors"])), None)
        if not nv:
            continue
        tv = next((v for v in pv if v["name"].upper() == nv["name"].upper()), None)
        if tv is None:
            tv = {"name": nv["name"], "price": None, "colors": [], "notes": []}
            pv.append(tv)
        if not any(x["name"].lower() == c["name"].lower() for x in tv["colors"]):
            tv["colors"].append(c)
    order = [v["name"].upper() for v in now["variants"]]
    pv.sort(key=lambda v: order.index(v["name"].upper()) if v["name"].upper() in order else 99)
    prev["loose_colors"] = []


PREV_TITLE = re.compile(r"(rilis|resmi|launching|meluncur|luncur|warna baru|warna-baru|harga|hadir|new|terbaru|facelift|penyegaran)", re.I)


def find_previous(model: str, brand: str, date_iso: str, get, sources: list[dict]) -> list[dict]:
    """Cari artikel rilis model yang sama 2 bulan – 4 tahun sebelum tanggal rilis ini (TMC: pencarian feed,
    Iwan Banaran: slug di sitemap). Hasil: kandidat {title,url,date,source} terbaru dulu."""
    name = re.sub(r"(?i)^(" + "|".join(re.escape(b) for b in _brand_tokens(brand)) + r")\s+", "", model).strip()
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if w.lower() not in ("new", "all")][:3]
    if not words:
        return []
    want = "".join(w.lower() for w in words[:2])
    now = datetime.fromisoformat(date_iso)
    lo, hi = now.timestamp() - 4 * 365 * 86400, now.timestamp() - 60 * 86400
    found = []
    for src in sources:
        base = src["base"].rstrip("/")
        if "tmcblog" in base:
            r = get(f"{base}/?s={quote(' '.join(words[:2]))}&feed=rss2")
            if r is not None and "<item" in r.text:
                for it in BeautifulSoup(r.content, "xml").find_all("item"):
                    t, link = it.title.text if it.title else "", it.link.text if it.link else ""
                    try:
                        from email.utils import parsedate_to_datetime
                        d = parsedate_to_datetime(it.pubDate.text)
                    except Exception:  # noqa: BLE001
                        continue
                    if lo <= d.timestamp() <= hi and want in re.sub(r"[^a-z0-9]", "", t.lower()) and PREV_TITLE.search(t):
                        found.append({"title": t, "url": link, "date": d.isoformat(), "source": src["name"]})
        if "iwanbanaran" in base:
            for sm in ("sitemap-posts-1.xml", "sitemap-posts-2.xml"):
                r = get(f"{base}/{sm}")
                if r is None:
                    continue
                for u in BeautifulSoup(r.content, "xml").find_all("url"):
                    loc, lm = u.find("loc"), u.find("lastmod")
                    if not loc or not lm:
                        continue
                    slug = loc.text.rsplit("/", 1)[-1]
                    try:
                        d = datetime.fromisoformat(lm.text.strip()[:10])
                    except ValueError:
                        continue
                    if lo <= d.timestamp() <= hi and want in slug.replace("-", "") and PREV_TITLE.search(slug):
                        found.append({"title": slug.replace("-", " "), "url": loc.text.strip(), "date": d.isoformat(),
                                      "source": src["name"]})
    found.sort(key=lambda x: x["date"], reverse=True)
    return found[:5]


def detail_score(d: dict | None) -> int:
    if not d:
        return 0
    return sum(2 * bool(v["price"]) + len(v["colors"]) + sum(1 for c in v["colors"] if c["image"]) for v in d["variants"])


# --------------------------------------------------------------------------- #
# Head to head spesifikasi
# --------------------------------------------------------------------------- #
SPEC_GROUPS = [
    ("Mesin", [
        ("Tipe Mesin", r"(tipe|jenis) mesin|engine type"),
        ("Volume Silinder", r"volume silinder|isi silinder|kapasitas (mesin|silinder)|displacement|kubikasi"),
        ("Diameter x Langkah", r"diameter x langkah|diameter ?x ?langkah|bore x stroke"),
        ("Perbandingan Kompresi", r"(perbandingan|rasio) kompresi|compression ratio"),
        ("Daya Maksimum", r"(daya|tenaga|power) (maksimum|maksimal|max)|max(imum)? power"),
        ("Torsi Maksimum", r"torsi (maksimum|maksimal|max)|max(imum)? torque"),
        ("Sistem Starter", r"(sistem )?(starter|stater)"),
        ("Sistem Bahan Bakar", r"sistem (bahan bakar|suplai bahan bakar)|fuel system"),
        ("Tipe Transmisi", r"(tipe |sistem |jenis )?transmisi"),
        ("Tipe Kopling", r"(tipe |jenis )?kopling"),
        ("Kapasitas Oli Mesin", r"kapasitas (oli|minyak pelumas)"),
    ]),
    ("Rangka & Kaki-kaki", [
        ("Tipe Rangka", r"(tipe |jenis )?rangka"),
        ("Suspensi Depan", r"suspensi depan"),
        ("Suspensi Belakang", r"suspensi belakang"),
        ("Ban Depan", r"(ukuran )?ban depan"),
        ("Ban Belakang", r"(ukuran )?ban belakang"),
        ("Rem Depan", r"rem depan"),
        ("Rem Belakang", r"rem belakang"),
    ]),
    ("Dimensi & Kapasitas", [
        ("P x L x T", r"p ?x ?l ?x ?t|dimensi( \(p ?x ?l ?x ?t\))?|panjang x lebar x tinggi"),
        ("Jarak Sumbu Roda", r"jarak sumbu roda|wheelbase"),
        ("Jarak Terendah ke Tanah", r"jarak (terendah )?(ke|dengan) tanah|ground clearance"),
        ("Tinggi Tempat Duduk", r"tinggi (tempat duduk|jok)|seat height"),
        ("Berat Isi", r"berat( isi| kosong| kering)?|bobot( isi)?|curb weight"),
        ("Kapasitas Tangki Bensin", r"(kapasitas )?tangki( bensin| bahan bakar)?|kapasitas bahan bakar|fuel tank"),
    ]),
    ("Kelistrikan", [
        ("Sistem Pengapian", r"(sistem )?pengapian"),
        ("Tipe Battery", r"(tipe )?(battery|baterai|aki)"),
        ("Tipe Busi", r"(tipe )?busi"),
    ]),
]
_SPEC_RX = [(label, re.compile(r"^\s*(?:" + rx + r")\b\s*(?:\([^)]*\))?\s*(?:[:：|=]|\s{2,}|\t)\s*(?P<val>.+)$", re.I))
            for _, items in SPEC_GROUPS for label, rx in items]


def spec_from_line(line: str) -> tuple[str, str] | None:
    """'Daya Maksimum : 11,3 kW / 8.500 rpm' → ('Daya Maksimum', '11,3 kW / 8.500 rpm')."""
    line = re.sub(r"\s*\|\s*[:：]?\s*\|?\s*", " : ", line.strip().strip("|•-– ")) if "|" in line else line.strip().strip("•-– ")
    if len(line) > 160:
        return None
    for label, rx in _SPEC_RX:
        m = rx.match(line)
        if m:
            val = re.sub(r"^[\s:：|=]+", "", m.group("val")).strip(" .;|")
            if val and len(val) <= 100 and not re.match(r"(?i)^(yang|ini|itu|juga|dan|masih|kini|tetap)\b", val):
                return label, val
    return None


def spec_table_from_lines(lines) -> dict:
    out: dict[str, str] = {}
    for line in lines:
        hit = spec_from_line(line)
        if hit and hit[0] not in out:
            out[hit[0]] = hit[1]
    return out
