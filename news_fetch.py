#!/usr/bin/env python3
"""
TIOS news layer — runs on a GitHub Actions runner (open internet). Pulls FREE, KEYLESS RSS/Atom
feeds + Google-News queries for the drivers that move THIS book, keeps only holding-relevant items,
and writes data/news-digest.json (machine) + data/news-latest.md (human).

News is CONTEXT ONLY — never a buy/sell/timing signal. No paid sources, no API keys.
The Cowork weekly task reads data/news-digest.json (raw same-origin) into market-intelligence.md.
See ANALYST-SPEC.md. Source map verified by the design audit (Worker 3, 27 Jun 2026).

Run:  python news_fetch.py
"""
import json, os, sys, datetime, hashlib, urllib.parse
import requests, feedparser

HERE = os.path.dirname(os.path.abspath(__file__))
OUTJSON = os.path.join(HERE, "data", "news-digest.json")
OUTMD = os.path.join(HERE, "data", "news-latest.md")
UA = "Mozilla/5.0 (TIOS news digest; thomas.noonan001@gmail.com)"
DAYS = 14          # rolling window
PER_SRC = 5        # cap items per source
PER_DRIVER = 6     # cap items shown per driver in the human digest

# driver -> the holdings it transmits to
HOLDINGS = {
 "US rates / Fed": ["IVV", "VGS", "NDQ", "GGUS"],
 "US mega-cap / AI capex": ["IVV", "VGS", "NDQ", "GGUS"],
 "Semis / Taiwan": ["ASIA", "EMKT", "NDQ"],
 "China + iron ore": ["VAS", "VHY"],
 "Energy / oil": ["VHY", "VAS"],
 "Gold": ["QAU"],
 "Crypto": ["CRYP"],
 "AU rates (RBA)": ["VAS", "VHY"],
 "AU tax / reg": ["ALL (disposal gate)"],
 "UK tax / reg": ["ALL (disposal gate)"],
 "Europe": ["HEUR"],
 "Cross-market": ["whole book"],
}

def gn(q):  # Google News RSS query (free, keyless)
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=en-AU&gl=AU&ceid=AU:en"

# (driver, source name, url-or-__GN__query, trust A/B/C)
SOURCES = [
 ("US rates / Fed", "Fed monetary", "https://www.federalreserve.gov/feeds/press_monetary.xml", "A"),
 ("US rates / Fed", "Fed speeches", "https://www.federalreserve.gov/feeds/speeches.xml", "A"),
 ("US rates / Fed", "BLS", "https://www.bls.gov/feed/bls_latest.rss", "A"),
 ("US mega-cap / AI capex", "Google News", '__GN__"AI capex" OR hyperscaler OR "data center" (Nvidia OR Microsoft OR Meta OR Amazon OR Alphabet OR Apple)', "C"),
 ("Semis / Taiwan", "Google News", '__GN__TSMC OR "Taiwan Semiconductor" OR "chip capex" OR "Taiwan Strait" OR semiconductor', "C"),
 ("China + iron ore", "Google News", '__GN__"iron ore" OR "China stimulus" OR "China property" OR PBoC OR "Caixin PMI"', "C"),
 ("Energy / oil", "EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml", "A"),
 ("Energy / oil", "Google News", '__GN__"oil price" OR OPEC OR Brent OR Hormuz', "C"),
 ("Gold", "Google News", '__GN__"gold price" OR "safe haven" OR "central bank gold"', "C"),
 ("Crypto", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "B"),
 ("AU rates (RBA)", "RBA", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "A"),
 ("AU tax / reg", "AU Treasury", "https://treasury.gov.au/rss.xml", "A"),
 ("AU tax / reg", "Google News", '__GN__"Division 296" OR "super tax" OR "capital gains tax" Australia', "C"),
 ("UK tax / reg", "gov.uk HMRC", "https://www.gov.uk/government/organisations/hm-revenue-customs.atom", "A"),
 ("Europe", "ECB press", "https://www.ecb.europa.eu/rss/press.html", "A"),
 ("Cross-market", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "B"),
]

def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        if r.status_code != 200:
            return None
        return feedparser.parse(r.content)   # requests auto-decompresses gzip; feedparser parses bytes
    except Exception as e:
        sys.stderr.write(f"  fetch fail {url[:55]}: {e}\n")
        return None

def pub_dt(e):
    for k in ("published_parsed", "updated_parsed"):
        v = e.get(k)
        if v:
            try:
                return datetime.datetime(*v[:6], tzinfo=datetime.timezone.utc)
            except Exception:
                pass
    return None

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=DAYS)
    items, seen = [], set()
    for driver, name, url, trust in SOURCES:
        is_gn = url.startswith("__GN__")
        feed = fetch(gn(url[5:]) if is_gn else url)
        src = "Google News" if is_gn else name
        n = 0
        for e in (feed.entries if feed else []):
            if n >= PER_SRC:
                break
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title:
                continue
            key = hashlib.md5(title.lower()[:80].encode()).hexdigest()
            if key in seen:
                continue
            dt = pub_dt(e)
            if dt and dt < cutoff:
                continue
            publisher = src
            if is_gn and " - " in title:        # Google News titles end "Headline - Publisher"
                publisher = title.rsplit(" - ", 1)[1].strip()
            seen.add(key)
            items.append({"driver": driver, "holdings": HOLDINGS.get(driver, ["whole book"]),
                          "title": title, "source": publisher, "url": link,
                          "published": (dt.strftime("%Y-%m-%d") if dt else ""),
                          "trust": trust, "flag": "context-only"})
            n += 1
        print(f"  {driver:24} {src:14} +{n}")
    items.sort(key=lambda x: x["published"], reverse=True)

    os.makedirs(os.path.dirname(OUTJSON), exist_ok=True)
    json.dump({"generated": now.strftime("%Y-%m-%dT%H:%MZ"),
               "note": "CONTEXT ONLY — never a buy/sell/timing signal. Free keyless feeds. See ANALYST-SPEC.md.",
               "count": len(items), "items": items}, open(OUTJSON, "w"), indent=1)

    md = [f"# News that moves the book — {now.strftime('%Y-%m-%d')}",
          "*CONTEXT ONLY — not a buy/sell/timing signal. Default: HOLD + keep contributing; any sale adviser-gated. Trust: A=official/primary · B=major wire · C=aggregator.*", ""]
    for driver in dict.fromkeys(d for d, *_ in SOURCES):     # unique drivers, in order
        ds = [i for i in items if i["driver"] == driver][:PER_DRIVER]
        if not ds:
            continue
        md.append(f"## {driver}  → {', '.join(HOLDINGS.get(driver, ['whole book']))}")
        for i in ds:
            md.append(f"- [{i['trust']}] {i['title']} *({i['source']}, {i['published']})* — {i['url']}")
        md.append("")
    open(OUTMD, "w").write("\n".join(md))
    print(f"\nWrote {len(items)} items -> {OUTJSON} + {OUTMD}")

if __name__ == "__main__":
    main()
