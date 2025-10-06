# crawler/crawler.py  (no multiprocessing)

import time, random
from pathlib import Path
from urllib.parse import  urljoin
from crawler.fetcher import Fetcher
from my_utils import *
from html import unescape

class Crawler:

    def __init__(self):
        self.profile = str(Path.home() / ".uc" / "tesco-profile-3")
        self.fetcher = Fetcher()

        return

    def parse_listing_page(self, html: str, base_url: str, cat_cfg: dict):
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
        self,
        start_url: str,
        cat_cfg: dict,
        max_pages: int | None = None,
        headless: bool = False,
        respect_robots: bool = True,
    ):
        seen, out = set(), set()
        driver = create_driver(profile_dir=self.profile, headless=headless)
        url = start_url
        try:
            while url and url not in seen:
                seen.add(url)
                fetcher = self.fetcher
                html = fetcher.fetch_html_dynamic(url, driver=driver, headless=headless, respect_robots=respect_robots)
                print(f"Fetched url:{url}.")
                res = self.parse_listing_page(html, url, cat_cfg)

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

    def parse_product_html(self, html: str, cfg: dict):
        pcfg = cfg["product"]
        fl = flags(pcfg.get("flags"))

        #name
        name_m = re.search(pcfg["name_regex"], html, flags=fl)
        name = unescape(name_m.group(1).strip()) if name_m else None

        #currency, price
        price_m = re.search(pcfg["price_regex"], html, flags=fl)
        cur, val = (None, None)
        if price_m:
            gi, gv = pcfg.get("price_capture_groups", [1, 2])
            cur = price_m.group(gi).strip()
            val = float(price_m.group(gv))

        #brand
        brand = None
        b1 = re.search(pcfg["brand_regex_aria"], html, flags=fl)
        if b1:
            brand = unescape(b1.group(1).strip())
        else:
            b2 = re.search(pcfg["brand_regex_facet"], html, flags=fl)
            if b2:
                brand = unescape(b2.group(1).replace("%20", " ").replace("%2D", "-"))

        #ingredients
        ingredients = None
        m = re.search(pcfg["ingredients_regex"], html, flags=fl)
        if m:
            inner = m.group(1)
            inner_stripped = strip_html_plain(inner)
            ingredients = get_ingredients(inner_stripped)

        #category
        cm = re.search(pcfg["category_regex"], html, flags=fl)
        category = unescape(cm.group(1).strip()) if cm else None

        # description
        dm = re.search(pcfg["description_regex"], html, flags=fl)
        description = None
        description_lines = None
        if dm:
            block = dm.group(1)
            raw_lines = re.findall(pcfg["description_lines_regex"], block, flags=fl)
            lines = []
            for s in raw_lines:
                t = unescape(strip_html_plain(s).strip())
                if t:
                    lines.append(t)
            description_lines = lines or None
            description = " ".join(description_lines) if description_lines else None

        return {
            "name": name,
            "brand": brand,
            "price_currency": cur,
            "price": val,
            "ingredients": ingredients,
            "category": category,
            "description": description,
        }

    def process_product_pages_sequential(
        self,
        product_urls: list[str],
        cfg: dict,
        headless: bool = False,
        respect_robots: bool = True,
    ):
        """Visit every product URL sequentially using ONE driver."""
        driver = create_driver(profile_dir=self.profile, headless=headless)
        out = []
        try:
            for u in product_urls:
                try:
                    print("started fetching")
                    html = self.fetcher.fetch_html_dynamic(
                        u,
                        driver=driver,                 # reuse same driver
                        headless=headless,
                        wait_selector=None,            # SSR-first: no heavy waits
                        respect_robots=respect_robots,
                        retries=1,
                    )
                    print(f"Fetched url:{u}.")
                    data = self.parse_product_html(html, cfg)
                    print(data)
                    data.update({"site": cfg.get("site", "unknown"), "url": u})
                    out.append(data)
                    time.sleep(0.08 + random.random() * 0.15)  # tiny jitter; be polite
                except Exception as e:
                    out.append({"site": cfg.get("site", "unknown"), "url": u, "error": str(e)})
        finally:
            driver.quit()
        return out


    def crawl(self, cfg: dict, max_pages: int):
        """workers kept for API compatibility; ignored (no multiprocessing)."""
        start_url = cfg["start_url"]
        cat = cfg["category"]

        product_pages = self.list_product_urls_from_listings(
            start_url, cat, max_pages=max_pages, headless=False, respect_robots=True
        )

        parsed_products = self.process_product_pages_sequential(
            product_pages, cfg, headless=False, respect_robots=True
        )
        return parsed_products
