"""Boss-mode randomisation data pools and RSS headline fetching."""

import logging
import random
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# -- Boss-mode randomisation pools (mirror src/ts/boss-lock/edition.ts) ------

BRANDS = [
    'Nikkei-ish Times', 'Keizai Observer', 'Shachiku Standard',
    'Kabushiki Chronicle', 'Ledger Shinpo', 'Toushi Weekly',
    'The Wall Treat Journal', 'Bloomsburg Review', 'Fishing Tyres',
    'The Econonomist', 'Barrons Weekday', 'Dow Janes Newswire',
    'Markit Watch', 'Investors Dairy', 'The Motley Fuel',
    'CNBN World', 'Forex Factory Outlet', 'The Guardiun Business',
    'FAX NEWS', 'BVC WORLD NEWS', 'MPR Breakable NEWS',
    'CBG NEWS', 'Ski News', 'ABG NEWS and Headlines',
    'PB$ Public Broadband for $',
]

HEADLINES = [
    ('Bond Yields Ease as Investors Reprice Policy Path',
     'Major indices traded in narrow ranges, while sector rotation remained active beneath the surface.'),
    ('AI Capex Wave Lifts Outlook for Chipmakers and Software Groups',
     'Investors balanced growth concerns with stronger enterprise spending signals, keeping tech leadership intact.'),
    ('Commodities Retreat as Traders Lock in Gains from Recent Rally',
     'Energy-linked equities softened while defensive sectors outperformed in late-session trading.'),
    ('Dollar Strengthens on Diverging Rate Expectations Across G7',
     'Currency markets responded to widening policy differentials, with exporters rallying.'),
    ('Trade Tensions Resurface as Tariff Fears Rattle Asian Markets',
     'Uncertainty over trade policy rippled through global supply chains, lifting demand for hedging.'),
    ('Real Estate Recovery Takes Shape as REIT Index Hits Year-High',
     'Expectations of peak interest rates are drawing capital back into property trusts.'),
    ('Emerging Markets Draw Fresh Inflows as Rate Cuts Begin',
     'Narrowing interest-rate differentials spur a rotation into EM debt and equities.'),
    ('IPO Pipeline Swells as Tech and Healthcare Deals Multiply',
     'Improved risk appetite is accelerating the pace of listings.'),
    ('Global Inflation Cools, Markets Price In Policy Pivot',
     'Slowing consumer-price gains have fueled expectations of coordinated monetary easing.'),
    ('ESG Scrutiny Intensifies as Regulators Push for Disclosure Standards',
     'Investors recalibrate sustainability strategies as greenwashing concerns grow.'),
]

STORIES = [
    'Central banks signal a data-dependent pause at upcoming meetings',
    'Freight rates ease as shipping lanes continue to normalize',
    'Housing indicators show tentative signs of stabilization',
    'Emerging-market currencies trade mixed versus the dollar',
    'AI capex plans lift guidance across enterprise software names',
    'Semiconductor inventory metrics improve, boosting order outlook',
    'Cloud providers reiterate infrastructure investment targets',
    'Large-cap tech earnings surpass consensus on revenue growth',
    'Energy stocks pull back as commodities retreat from recent highs',
    'Consumer staples attract inflows on valuation appeal',
    'Strong payrolls data reinforces higher-for-longer rate outlook',
    'Gold extends rally as investors seek safe-haven assets',
    'Office vacancy rates drop for the first time in four quarters',
    'Data center REITs surge on AI-driven infrastructure demand',
    'Brazil central bank delivers third consecutive rate cut',
    'Indian equity market climbs to fourth-largest by capitalization',
    'AI startups filing for IPOs at fastest pace on record',
    'Green bond issuance surges 40% year over year',
    'US CPI undershoots consensus, boosting rate-cut bets',
    'Carbon credit trading volumes reach record highs globally',
]

SECTIONS = ['World', 'Markets', 'Economy', 'Companies', 'Tech', 'Policy',
            'Opinion', 'Commodities', 'Currencies', 'Fixed Income',
            'Regulation', 'IPO Watch', 'Real Estate', 'Climate & Energy']

BYLINES = ['By Lionel Beige', 'By Markets Desk', 'By A. Ledger',
           'By C. Margin, London Bureau', 'By R. Dividend & S. Yield',
           'By Capital Markets Team', 'By D. Leverage, New York',
           'By Desk Tokyo', 'By K. Sato', 'By Y. Suzuki, Kabutocho Bureau']

BREAKING = [
    'Breaking: Equity futures swing sharply higher',
    'Breaking: Major central banks signal joint statement',
    'Breaking: FX moves ahead of key macro release',
    'Breaking: Crude oil drops 5% on supply concerns',
    'Breaking: US payrolls smash expectations, yields spike',
    'Breaking: ECB delivers surprise rate cut',
    'Breaking: Chipmaker raises full-year guidance sharply',
    'Breaking: Gold hits record high amid safe-haven demand',
]

DESK_LABELS = ['Analysis', 'Briefing', 'Markets Live', 'Morning Note',
               'Desk View', 'Deep Dive', 'The Big Read', 'Macro Pulse']


# -- Real news headline cache --------------------------------------------------

_RSS_FEEDS = [
    'https://feeds.bbci.co.uk/news/business/rss.xml',
    'https://feeds.bbci.co.uk/news/technology/rss.xml',
]
_news_cache_lock = threading.Lock()
_news_cache_headlines: list = []
_news_cache_ts: float = 0.0
_NEWS_CACHE_TTL = 600  # 10 minutes


def _fetch_real_headlines() -> list:
    """Fetch real business/tech headlines from RSS feeds (cached 10 min)."""
    global _news_cache_headlines, _news_cache_ts

    now = time.time()
    with _news_cache_lock:
        if _news_cache_headlines and (now - _news_cache_ts) < _NEWS_CACHE_TTL:
            return list(_news_cache_headlines)

    headlines = []
    for feed_url in _RSS_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; YU-AI-Manager/2.8)',
            })
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                root = ET.fromstring(resp.read())
            for item in root.findall('.//item/title'):
                if item.text:
                    headlines.append(item.text.strip())
        except Exception:
            logger.warning("web startup step failed", exc_info=True)

    with _news_cache_lock:
        _news_cache_headlines = headlines
        _news_cache_ts = now

    return headlines


def pick_boss_edition() -> dict:
    """Return a fully randomised edition for boss-mode pages."""
    brand = random.choice(BRANDS)
    headline, subhead = random.choice(HEADLINES)

    # Mix 2-3 real headlines into the fake stories
    fake_stories = random.sample(STORIES, min(3, len(STORIES)))
    real_headlines = _fetch_real_headlines()
    real_picks = random.sample(real_headlines, min(2, len(real_headlines))) if real_headlines else []
    stories = fake_stories + real_picks
    random.shuffle(stories)

    sections = random.sample(SECTIONS, min(5, len(SECTIONS)))
    byline = random.choice(BYLINES)
    show_breaking = random.random() < 0.38
    breaking_text = random.choice(BREAKING) if show_breaking else ''
    desk_label = random.choice(DESK_LABELS)
    return {
        'brand': brand, 'headline': headline, 'subhead': subhead,
        'stories': stories, 'sections': sections, 'byline': byline,
        'show_breaking': show_breaking, 'breaking_text': breaking_text,
        'desk_label': desk_label,
    }


def get_quotes_html() -> tuple:
    """Fetch live market quotes and return (quotes_html, source_label)."""
    try:
        from core.services_core.market_quotes import get_market_quotes_payload
        data = get_market_quotes_payload()
        quotes = data.get('quotes', [])
        source = data.get('source', 'fallback')
    except Exception:
        quotes = []
        source = 'fallback'

    if not quotes:
        return '', 'sample'

    rows = []
    for q in quotes:
        label = str(q.get('label', ''))[:8]
        value = str(q.get('value', ''))
        color = '#7b1e1e' if value.startswith('-') else '#1f3f1f'
        rows.append(
            f'<div style="display:flex;justify-content:space-between;gap:12px;">'
            f'<span>{label}</span>'
            f'<span style="font-weight:700;color:{color};">{value}</span></div>'
        )
    src_label = 'LIVE' if source == 'yahoo' else 'FALLBACK'
    return '\n'.join(rows), src_label
