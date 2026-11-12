#!/usr/bin/env python3
"""
Motorcycle Issue scraper.

Mengambil artikel dari iwanbanaran.com, pertamax7.com dan tmcblog.com untuk
satu periode (H1 = tanggal 1-15, H2 = tanggal 16-akhir bulan), memberi tag
merek & kategori, lalu menyimpannya ke docs/data/periods/<YYYY-MM-Hn>.json
dan memperbarui docs/data/index.json yang dibaca oleh dashboard.

Pemakaian:
    python scraper/fetch_issues.py                 # periode otomatis (hari ini, WIB)
    python scraper/fetch_issues.py --period 2026-05-H1
    python scraper/fetch_issues.py --period 2026-05-H2 --no-article-fetch
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import summarize

WIB = timezone(timedelta(hours=7))
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
PERIOD_DIR = DATA_DIR / "periods"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

MONTHS_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]


# --------------------------------------------------------------------------- #
# Periode
# --------------------------------------------------------------------------- #
@dataclass
class Period:
    year: int
    month: int
    half: int  # 1 or 2

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-H{self.half}"

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1 if self.half == 1 else 16)

    @property
    def end(self) -> date:
        last = calendar.monthrange(self.year, self.month)[1]
        return date(self.year, self.month, 15 if self.half == 1 else last)

    @property
    def label(self) -> str:
        return f"{self.start.day} – {self.end.day} {MONTHS_ID[self.month]} {self.year}"

    @classmethod
    def parse(cls, s: str) -> "Period":
        m = re.fullmatch(r"(\d{4})-(\d{2})-H([12])", s.strip().upper())
        if not m:
            raise ValueError(f"Format periode salah: {s!r} (contoh: 2026-05-H1)")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    @classmethod
    def for_day(cls, d: date) -> "Period":
        return cls(d.year, d.month, 1 if d.day <= 15 else 2)


# --------------------------------------------------------------------------- #
# Model artikel
# --------------------------------------------------------------------------- #
@dataclass
class Article:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    image: str | None = None
    brands: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    text: str = ""  # isi lengkap artikel, hanya dipakai untuk meringkas (tidak disimpan)
    points: list[str] = field(default_factory=list)
    summary_by: str = ""  # "ai" | "auto"

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published": self.published.astimezone(WIB).isoformat(),
            "summary": self.summary,
            "points": self.points,
            "summary_by": self.summary_by,
            "image": self.image,
            "brands": self.brands,
            "categories": self.categories,
        }


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, retries: int = 3, timeout: int = 25) -> requests.Response | None:
    for i in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            print(f"  ! {url}: HTTP {r.status_code}", file=sys.stderr)
            if r.status_code in (404, 410):
                return None
        except requests.RequestException as e:
            print(f"  ! {url}: {e}", file=sys.stderr)
        time.sleep(2 ** i)
    return None


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
        if d:
            return d if d.tzinfo else d.replace(tzinfo=WIB)
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=WIB)
    except ValueError:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=WIB)
    return None


def clean_text(html_or_text: str) -> str:
    text = BeautifulSoup(html_or_text or "", "lxml").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    # buang ekor khas WordPress: "The post X appeared first on Y."
    text = re.sub(r"The post .* appeared first on .*$", "", text).strip()
    text = re.sub(r"\[(…|\.\.\.)\]$", "…", text).strip()
    return text


def shorten(text: str, limit: int = 600) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…").strip()


# --------------------------------------------------------------------------- #
# Collectors
# --------------------------------------------------------------------------- #
def collect_from_feed(src: dict, period: Period) -> list[Article]:
    """WordPress-style RSS, menelusuri ?paged=N sampai melewati awal periode."""
    out: list[Article] = []
    start_dt = datetime.combine(period.start, datetime.min.time(), WIB)
    for feed_url in src.get("feeds", []):
        for page in range(1, src.get("max_feed_pages", 15) + 1):
            url = feed_url if page == 1 else f"{feed_url}{'&' if '?' in feed_url else '?'}paged={page}"
            r = get(url)
            if not r or "<item" not in r.text:
                break
            soup = BeautifulSoup(r.content, "xml")
            items = soup.find_all("item")
            if not items:
                break
            oldest = None
            for it in items:
                pub = parse_date(it.pubDate.text if it.pubDate else None)
                link = (it.link.text if it.link else "").strip()
                title = clean_text(it.title.text if it.title else "")
                if not (pub and link and title):
                    continue
                oldest = pub if oldest is None or pub < oldest else oldest
                content = it.find("encoded") or it.find("content:encoded")
                desc = it.description.text if it.description else ""
                body_html = content.text if content else desc
                image = None
                media = it.find("media:content") or it.find("content", attrs={"url": True}) or it.find("enclosure")
                if media and media.get("url"):
                    image = media["url"]
                if not image and body_html:
                    img = BeautifulSoup(body_html, "lxml").find("img")
                    if img and img.get("src"):
                        image = img["src"]
                text = clean_text(body_html)
                out.append(Article(title=title, url=link, source=src["name"], published=pub,
                                   summary=shorten(text), image=image, text=text))
            if oldest and oldest < start_dt:
                break
        if out:
            break  # feed pertama yang berhasil sudah cukup
    return out


def collect_from_sitemap(src: dict, period: Period) -> list[Article]:
    """Fallback: baca sitemap, ambil URL dengan lastmod di sekitar periode."""
    urls: list[tuple[str, datetime | None]] = []
    lo = datetime.combine(period.start, datetime.min.time(), WIB) - timedelta(days=1)
    seen_maps: set[str] = set()
    queue = list(src.get("sitemaps", []))
    while queue and len(seen_maps) < 30:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        r = get(sm)
        if not r:
            continue
        soup = BeautifulSoup(r.content, "xml")
        for s in soup.find_all("sitemap"):
            loc = s.find("loc")
            lm = parse_date(s.lastmod.text if s.find("lastmod") else None)
            if loc and (lm is None or lm >= lo) and re.search(r"post|news|article|sitemap\d|\d{4}", loc.text):
                queue.append(loc.text.strip())
        for u in soup.find_all("url"):
            loc = u.find("loc")
            lm = parse_date(u.lastmod.text if u.find("lastmod") else None)
            if loc and (lm is None or lm >= lo):
                urls.append((loc.text.strip(), lm))
    arts = []
    for url, _ in urls[: src.get("max_sitemap_urls", 150)]:
        a = fetch_article(url, src["name"])
        if a:
            arts.append(a)
    return arts


def collect_from_homepage(src: dict, period: Period) -> list[Article]:
    """Fallback terakhir: link artikel di halaman depan / kategori."""
    pattern = re.compile(src.get("article_url_regex", r"/\d{4}/\d{2}/|/news/|/berita/"))
    links: list[str] = []
    for page in src.get("listing_pages", [src["base"]]):
        r = get(page)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = urljoin(page, a["href"]).split("#")[0]
            if urlparse(href).netloc.endswith(urlparse(src["base"]).netloc.replace("www.", "")) \
                    and pattern.search(href) and href not in links:
                links.append(href)
    arts = []
    for url in links[: src.get("max_listing_urls", 80)]:
        a = fetch_article(url, src["name"])
        if a:
            arts.append(a)
    return arts


def fetch_article(url: str, source: str) -> Article | None:
    r = get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")

    def meta(*names):
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    title = meta("og:title") or (soup.title.text.strip() if soup.title else "")
    pub = parse_date(meta("article:published_time", "datePublished", "pubdate", "date"))
    if not pub:
        t = soup.find("time", attrs={"datetime": True})
        pub = parse_date(t["datetime"]) if t else None
    if not pub:
        for s in soup.find_all("script", type="application/ld+json"):
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', s.text or "")
            if m:
                pub = parse_date(m.group(1))
                break
    if not (title and pub):
        return None
    body = soup.find("article") or soup.find(class_=re.compile(r"entry-content|post-content|article-content|content-detail"))
    paras = [p.get_text(" ", strip=True) for p in (body or soup).find_all("p")]
    paras = [p for p in paras if len(p) > 60]
    summary = shorten(" ".join(paras[:4])) or (meta("og:description", "description") or "")
    return Article(title=clean_text(title), url=url, source=source, published=pub,
                   summary=summary, image=meta("og:image"), text=" ".join(paras))


def enrich(article: Article) -> None:
    """Lengkapi gambar / ringkasan dari halaman artikel bila feed terlalu tipis."""
    if article.image and len(article.text) > 1200:
        return
    full = fetch_article(article.url, article.source)
    if not full:
        return
    article.image = article.image or full.image
    if len(full.text) > len(article.text):
        article.text = full.text
    if len(full.summary) > len(article.summary):
        article.summary = full.summary


# --------------------------------------------------------------------------- #
# Tagging
# --------------------------------------------------------------------------- #
def tag(article: Article, cfg: dict) -> None:
    text = f"{article.title} {article.summary}".lower()
    title = article.title.lower()

    def hits(keywords: list[str], hay: str) -> int:
        return sum(1 for k in keywords if re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", hay))

    brands = [(b, hits(kws, title) * 3 + hits(kws, text)) for b, kws in cfg["brands"].items()]
    article.brands = [b for b, s in sorted(brands, key=lambda x: -x[1]) if s > 0][:3]
    cats = [(c, hits(kws, title) * 2 + hits(kws, text)) for c, kws in cfg["categories"].items()]
    article.categories = [c for c, s in sorted(cats, key=lambda x: -x[1]) if s > 0][:3] or ["Lainnya"]


def is_relevant(article: Article, cfg: dict) -> bool:
    text = f"{article.title} {article.summary}".lower()
    for kw in cfg.get("exclude_title_keywords", []):
        if kw.lower() in article.title.lower():
            return False
    car_only = cfg.get("car_keywords", [])
    moto = cfg.get("motorcycle_keywords", [])
    if any(k in text for k in car_only) and not any(k in text for k in moto) and not article.brands:
        return False
    return True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def run(period: Period, article_fetch: bool = True) -> dict:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    start_dt = datetime.combine(period.start, datetime.min.time(), WIB)
    end_dt = datetime.combine(period.end, datetime.max.time(), WIB)

    collected: dict[str, Article] = {}
    report = {}
    for src in cfg["sources"]:
        print(f"→ {src['name']}")
        arts: list[Article] = []
        method = None
        for method in ("feed", "sitemap", "homepage"):
            fn = {"feed": collect_from_feed, "sitemap": collect_from_sitemap, "homepage": collect_from_homepage}[method]
            try:
                arts = fn(src, period)
            except Exception as e:  # noqa: BLE001 - lanjut ke metode berikutnya
                print(f"  ! {method} gagal: {e}", file=sys.stderr)
                arts = []
            arts = [a for a in arts if start_dt <= a.published <= end_dt]
            if arts:
                break
        print(f"  {len(arts)} artikel via {method if arts else '-'}")
        report[src["name"]] = {"count": len(arts), "method": method if arts else None}
        for a in arts:
            collected.setdefault(a.url, a)

    articles = list(collected.values())
    for a in articles:
        if article_fetch:
            enrich(a)
        tag(a, cfg)
    articles = [a for a in articles if is_relevant(a, cfg)]
    articles.sort(key=lambda a: a.published, reverse=True)

    out_path = PERIOD_DIR / f"{period.key}.json"
    existing = {}
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        existing = {x["url"]: x for x in old.get("articles", [])}

    # Ringkas: artikel yang sudah punya ringkasan AI (atau dikunci) tidak diringkas ulang.
    todo = [a for a in articles
            if not (existing.get(a.url, {}).get("locked")
                    or (existing.get(a.url, {}).get("summary_by") == "ai" and existing[a.url].get("points")))]
    summarize.summarize_all(todo)

    merged = []
    for a in articles:
        d = a.to_dict()
        prev = existing.pop(a.url, None)
        if prev:
            if not d["points"] and prev.get("points"):
                d["points"], d["summary_by"] = prev["points"], prev.get("summary_by", "")
            # pertahankan suntingan manual (highlight, summary, tags yang dikunci)
            for k in ("highlight", "note"):
                if k in prev:
                    d[k] = prev[k]
            if prev.get("locked"):
                d.update({k: prev[k] for k in ("summary", "points", "summary_by", "brands", "categories", "title") if k in prev})
                d["locked"] = True
        merged.append(d)
    merged.extend(existing.values())  # artikel lama yang tak muncul lagi tetap disimpan
    merged.sort(key=lambda x: x["published"], reverse=True)

    payload = {
        "period": period.key,
        "label": period.label,
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "generated_at": datetime.now(WIB).isoformat(timespec="seconds"),
        "sources": report,
        "articles": merged,
    }
    PERIOD_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_index()
    print(f"✓ {len(merged)} artikel → {out_path.relative_to(ROOT)}")
    return payload


def rebuild_index() -> None:
    periods = []
    for p in sorted(PERIOD_DIR.glob("*.json"), reverse=True):
        d = json.loads(p.read_text(encoding="utf-8"))
        periods.append({
            "period": d["period"], "label": d["label"], "start": d["start"], "end": d["end"],
            "count": len(d["articles"]), "generated_at": d.get("generated_at"),
            "file": f"data/periods/{p.name}",
        })
    (DATA_DIR / "index.json").write_text(
        json.dumps({"updated_at": datetime.now(WIB).isoformat(timespec="seconds"), "periods": periods},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", help="YYYY-MM-H1 atau YYYY-MM-H2 (default: periode hari ini, WIB)")
    ap.add_argument("--no-article-fetch", action="store_true", help="jangan buka halaman artikel satu per satu")
    ap.add_argument("--no-ai", action="store_true", help="jangan pakai ringkasan AI walau ANTHROPIC_API_KEY tersedia")
    ap.add_argument("--reindex", action="store_true", help="hanya bangun ulang docs/data/index.json")
    args = ap.parse_args()
    if args.reindex:
        rebuild_index()
        return
    period = Period.parse(args.period) if args.period else Period.for_day(datetime.now(WIB).date())
    if args.no_ai:
        summarize.USE_AI = False
    print(f"Periode {period.key} ({period.label})")
    run(period, article_fetch=not args.no_article_fetch)


if __name__ == "__main__":
    main()
