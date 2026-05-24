"""
Screener.in scraper for deep fundamentals, financial results, and shareholding data.
"""

import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
from urllib.parse import quote

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Reusable session for connection pooling
_session = requests.Session()
_session.headers.update(HEADERS)

# Rate limiting
_last_request_time = 0
MIN_REQUEST_INTERVAL = 2.0  # seconds between requests


def _rate_limited_get(url: str, max_retries: int = 3) -> Optional[requests.Response]:
    """Make a rate-limited GET request with retries and exponential backoff."""
    global _last_request_time

    for attempt in range(max_retries):
        # Enforce minimum delay between requests
        elapsed = time.time() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed + random.uniform(0, 0.5))

        try:
            _last_request_time = time.time()
            response = _session.get(url, timeout=20)

            if response.status_code == 200:
                return response
            elif response.status_code in (429, 503):
                backoff = (2**attempt) * 5 + random.uniform(0, 2)
                logger.warning(
                    f"Rate limited ({response.status_code}), waiting {backoff:.1f}s"
                )
                time.sleep(backoff)
            else:
                logger.warning(
                    f"Unexpected status {response.status_code} for {url}"
                )
                return None
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2**attempt)

    return None


def _parse_table(table_element) -> List[Dict[str, str]]:
    """Parse an HTML table into a list of row dicts."""
    if not table_element:
        return []

    headers = []
    header_row = table_element.find("thead")
    if header_row:
        headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    rows = []
    tbody = table_element.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if headers and len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            elif cells:
                rows.append({"data": cells})

    return rows


def resolve_screener_slug(symbol: str) -> Optional[str]:
    """Resolve NSE symbol to screener.in URL slug using search API."""
    url = f"https://www.screener.in/api/company/search/?q={quote(symbol)}&v=3&fts=1"
    response = _rate_limited_get(url)
    if not response:
        return None

    try:
        results = response.json()
        if results and len(results) > 0:
            # Extract slug from URL field
            first_result = results[0]
            if "url" in first_result:
                return first_result["url"].strip("/").split("/")[-1]
    except (ValueError, KeyError, IndexError):
        pass

    return symbol


def get_company_page(symbol: str) -> Optional[BeautifulSoup]:
    """Fetch and parse screener.in company page."""
    # Try consolidated first, then standalone
    urls = [
        f"https://www.screener.in/company/{quote(symbol, safe='')}/consolidated/",
        f"https://www.screener.in/company/{quote(symbol, safe='')}/",
    ]

    for url in urls:
        response = _rate_limited_get(url)
        if response and response.status_code == 200:
            return BeautifulSoup(response.text, "html.parser")

    # Try resolving the slug if direct access fails
    slug = resolve_screener_slug(symbol)
    if slug and slug != symbol:
        for suffix in ["/consolidated/", "/"]:
            url = f"https://www.screener.in/company/{quote(slug, safe='')}{suffix}"
            response = _rate_limited_get(url)
            if response and response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")

    return None


def get_top_ratios(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract top ratios (P/E, Market Cap, ROCE, etc.) from company page."""
    ratios = {}
    ratios_section = soup.find("ul", {"id": "top-ratios"})

    if not ratios_section:
        # Alternative: look for the ratios in the company-ratios section
        ratios_section = soup.find("div", {"id": "top"})

    if ratios_section:
        for li in ratios_section.find_all("li"):
            name_el = li.find("span", class_="name")
            value_el = li.find("span", class_="number") or li.find(
                "span", class_="value"
            )
            if name_el and value_el:
                ratios[name_el.get_text(strip=True)] = value_el.get_text(strip=True)

    return ratios


def get_quarterly_results(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract quarterly financial results."""
    section = soup.find("section", {"id": "quarters"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def get_profit_loss(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract annual profit & loss statement."""
    section = soup.find("section", {"id": "profit-loss"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def get_balance_sheet(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract balance sheet data."""
    section = soup.find("section", {"id": "balance-sheet"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def get_cash_flow(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract cash flow statement."""
    section = soup.find("section", {"id": "cash-flow"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def get_shareholding(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract shareholding pattern."""
    section = soup.find("section", {"id": "shareholding"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def get_ratios(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract financial ratios over years."""
    section = soup.find("section", {"id": "ratios"})
    if not section:
        return []

    table = section.find("table")
    return _parse_table(table)


def scrape_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Scrape comprehensive fundamental data from screener.in for a given NSE symbol.

    Returns dict with: ratios, quarterly_results, profit_loss, balance_sheet,
    cash_flow, shareholding, financial_ratios
    """
    logger.info(f"Scraping screener.in fundamentals for {symbol}")

    soup = get_company_page(symbol)
    if not soup:
        return {"error": f"Could not fetch data for {symbol} from screener.in"}

    # Extract company name
    company_name = ""
    h1 = soup.find("h1")
    if h1:
        company_name = h1.get_text(strip=True)

    result = {
        "symbol": symbol,
        "company_name": company_name,
        "source": "screener.in",
        "top_ratios": get_top_ratios(soup),
        "quarterly_results": get_quarterly_results(soup),
        "profit_loss": get_profit_loss(soup),
        "balance_sheet": get_balance_sheet(soup),
        "cash_flow": get_cash_flow(soup),
        "shareholding": get_shareholding(soup),
        "financial_ratios": get_ratios(soup),
    }

    logger.info(f"Successfully scraped fundamentals for {symbol}")
    return result
