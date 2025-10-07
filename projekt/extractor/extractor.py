
import time, random
from pathlib import Path
from urllib.parse import  urljoin
from crawler.fetcher import Fetcher
from my_utils import *
from html import unescape

class Extractor:

    def __init__(self, site_cfg, app_cfg):
        self.site_cfg = site_cfg
        self.app_cfg = app_cfg

        #add body regex
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

    def extract_products(self):
        return
