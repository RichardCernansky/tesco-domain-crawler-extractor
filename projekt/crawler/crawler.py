# crawler/crawler.py  (no multiprocessing)

import time, random
from pathlib import Path
from urllib.parse import  urljoin
from crawler.fetcher import create_driver, fetch_tesco_list_html, fetch_html_dynamic
from my_utils import *

def parse_listing_page(html: str, base_url: str, cat_cfg: dict):
    flags = re.IGNORECASE | re.DOTALL
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags)
    prod_re = re.compile(cat_cfg["product_url_regex"], flags)
    product_urls = sorted({urljoin(base_url, h) for h in hrefs if prod_re.search(h)})

    next_btn_re = re.compile(cat_cfg["next_button_regex"], flags)
    m = next_btn_re.search(html)
    next_url = None
    if m:
        next_href = urljoin(base_url, m.group(1))
        next_url = next_href.replace("&amp;", "&")

    return {"product_urls": product_urls, "next_page": next_url}

def list_product_urls_from_listings(
    start_url: str,
    cat_cfg: dict,
    max_pages: int | None = None,
    headless: bool = False,
    respect_robots: bool = True,
):
    seen, out = set(), set()
    profile = str(Path.home() / ".uc" / "tesco-profile")
    driver = create_driver(profile_dir=profile, headless=headless)
    url = start_url
    try:
        while url and url not in seen:
            seen.add(url)
            html = fetch_tesco_list_html(url, driver=driver, headless=headless, respect_robots=respect_robots)
            print(f"Fetched url:{url}.")
            res = parse_listing_page(html, url, cat_cfg)

            length=  len(res["product_urls"])
            next_one = res["next_page"]
            print(f"Number of product urls fetched: {length}")
            print(f"Next page:{next_one}")

            out.update(res["product_urls"])
            url = res["next_page"]

            if max_pages and len(out) >= max_pages:
                break
            if url in seen:
                break
    finally:
        driver.quit()
    return sorted(out)

def parse_product_html(html: str, cfg: dict):
    pcfg = cfg["product"]

    #name
    name_m = re.search(pcfg["name_regex"], html, flags(pcfg.get("flags")))
    name = unescape(name_m.group(1).strip()) if name_m else None

    #currency, price
    price_m = re.search(pcfg["price_regex"], html, flags(pcfg.get("flags")))
    cur, val = (None, None)
    if price_m:
        gi, gv = pcfg.get("price_capture_groups", [1, 2])
        cur = price_m.group(gi).strip()
        val = float(price_m.group(gv))

    #brand
    brand = None
    b1 = re.search(pcfg["brand_regex_aria"], html, flags(pcfg.get("flags")))
    if b1:
        brand = unescape(b1.group(1).strip())
    else:
        b2 = re.search(pcfg["brand_regex_facet"], html, flags(pcfg.get("flags")))
        if b2:
            brand = unescape(b2.group(1).replace("%20", " ").replace("%2D", "-"))

    #ingredients
    ingredients = None
    m = re.search(pcfg["ingredients_regex"], html, flags(pcfg.get("flags")))
    if m:
        inner = m.group(1)
        inner_stripped = strip_html_plain(inner)
        ingredients = get_ingredients(inner_stripped)

    return {"name": name, "brand": brand, "price_currency": cur, "price": val, "ingredients": ingredients}


def process_product_pages_sequential(
    product_urls: list[str],
    cfg: dict,
    headless: bool = False,
    respect_robots: bool = True,
):
    """Visit every product URL sequentially using ONE driver."""
    profile = str(Path.home() / ".uc" / "tesco-profile")
    driver = create_driver(profile_dir=profile, headless=headless)
    out = []
    try:
        for u in product_urls:
            try:
                print("started fetching")
                html = fetch_html_dynamic(
                    u,
                    driver=driver,                 # reuse same driver
                    headless=headless,
                    wait_selector=None,            # SSR-first: no heavy waits
                    respect_robots=respect_robots,
                    retries=1,
                )
                print(f"Fetched url:{u}.")
                data = parse_product_html(html, cfg)
                print(data)
                data.update({"site": cfg.get("site", "unknown"), "url": u})
                out.append(data)
                time.sleep(0.08 + random.random() * 0.15)  # tiny jitter; be polite
            except Exception as e:
                out.append({"site": cfg.get("site", "unknown"), "url": u, "error": str(e)})
    finally:
        driver.quit()
    return out


def _crawl(cfg: dict, max_pages: int, workers: int):
    """workers kept for API compatibility; ignored (no multiprocessing)."""
    start_url = cfg["start_url"]
    cat = cfg["category"]

    product_pages = list_product_urls_from_listings(
        start_url, cat, max_pages=max_pages, headless=False, respect_robots=True
    )

    parsed_products = process_product_pages_sequential(
        product_pages, cfg, headless=False, respect_robots=True
    )
    return parsed_products
