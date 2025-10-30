import json
import re
from pathlib import Path
from my_utils import *  # expects: flags, strip_html_plain, get_ingredients
from html import unescape

class Extractor:

    def __init__(self, site_cfg, app_cfg):
        self.site_cfg = site_cfg  # site-specific settings, including regex bundle
        self.app_cfg = app_cfg    # app-level settings, output paths

        return

    def get_name(self, html, rx):
        name_m = re.search(rx["name_regex"], html)  # extract product name via configured regex
        name = unescape(name_m.group(1).strip()) if name_m else None  # HTML-decode + trim capture group
        return name  # may be None if no match

    def get_ingredients(self, html, rx):
        ingredients = None  # default if no ingredients found
        m = re.search(rx["ingredients_regex"], html)  # locate ingredients block
        if m:
            inner = m.group(1)  # capture inner HTML of the ingredients section
            inner_stripped = strip_html_plain(inner)  # remove tags to plain text
            ingredients = get_ingredients(inner_stripped)  # delegate to util that tokenizes/normalizes
        return ingredients  # list or None

    def get_price_and_currency(self, html, rx):
        for key, price_regex in rx["price_regexes"].items():
            price_m = re.search(price_regex, html)  # attempt one pattern
            if price_m:
                # Capture the currency symbol, main price, and unit price
                cur = '£'  # Assuming the currency is always GBP
                price = price_m.group(1)
                unit_price = price_m.group(2).split('/')[0]
                unit = price_m.group(2).split('/')[1]
                unit_bundle = {"price": unit_price, "unit": unit}
                return cur, price, unit_bundle  # early return on first successful match
        return None, None, None  # Return None if no match is found  # signals missing price

    def get_brand(self, html, rx):
        brand = None
        b1 = re.search(rx["brand_regex"], html)  # attempt brand capture
        if b1:
            brand = unescape(b1.group(1).strip())  # HTML-decode + trim
        return brand  # may be None

    def get_category(self, html, rx):
        cm = re.search(rx["category_regex"], html)  # match category breadcrumb/label
        category = unescape(cm.group(1).strip()) if cm else None  # decode + trim or None
        return category

    def get_description(self, html, rx):
        # description  # multi-line description assembled from inner list items or paragraphs
        dm = re.search(rx["description_regex"], html)  # locate description container
        description = None
        if dm:
            block = dm.group(1)  # inner HTML block for description
            raw_lines = re.findall(rx["description_lines_regex"], block)  # collect line-level fragments
            lines = []
            for s in raw_lines:
                t = unescape(strip_html_plain(s).strip())  # HTML-to-text + trim each fragment
                if t:
                    lines.append(t)  # keep non-empty text lines
            description_lines = lines or None  # normalize empty -> None
            description = " ".join(description_lines) if description_lines else None  # join to one string
        return description  # final description or None

    def get_nutrition_table(self, html, rx):
        nut_rx = rx.get("nutrition_regexes")  # dict of nutrient -> regex pattern
        out = {}  # map nutrient keys to values
        for key, pattern in nut_rx.items():
            m = re.search(pattern, html)  # try to capture each nutrient field
            if m:
                val = unescape(strip_html_plain(m.group(1)).strip())  # decode + normalize
                out[key] = val  # store captured value
            else:
                out[key] = None  # keep key with None if missing
        return out  # complete nutrition dict with possible Nones

    def get_highlights(self, html, rx):
        block_re = rx.get("highlights_lines_regex")
        m = re.search(block_re, html)  # find the highlights container
        if not m:
            return None  # no highlights section found
        block = m.group(1)  # inner HTML of highlights area
        # Prefer site-configured line extractor; default to <li> items.  # fallback LI extraction
        line_re = r'<li[^>]*>(.*?)</li>'
        raw = re.findall(line_re, block, re.I | re.S)  # collect LI inner HTML
        items = []
        for s in raw:
            t = unescape(strip_html_plain(s).strip())  # normalize each bullet
            if t:
                items.append(t)  # keep non-empty bullet text
        return " ".join(items) if items else None  # single string of highlights or None

    def parse_product_html(self, html: str, rx: dict, html_name):
        name = self.get_name(html, rx)  # product title
        ingredients = self.get_ingredients(html, rx)  # list or None
        currency, price, unit_bundle = self.get_price_and_currency(html, rx)  # price triple
        brand = self.get_brand(html, rx)
        category = self.get_category(html, rx)
        description = self.get_description(html, rx)
        nutrition_table = self.get_nutrition_table(html, rx)
        highlights = self.get_highlights(html, rx)
        return {
            "name": name,
            "brand": brand,
            "price_currency": currency,
            "price": price,
            "ingredients": ingredients,
            "category": category,
            "description": description,
            "nutrition_table": nutrition_table,
            "unit_bundle": unit_bundle,
            "highlights": highlights
        }  # normalized product record for NDJSON

    def _dedupe_key(self, rec, field):
        """Normalize a field value into a stable, comparable key for deduping."""
        v = rec.get(field)  # access chosen field ("name")
        if v is None:
            return None  # cannot dedupe without a value
        if isinstance(v, str):
            k = unescape(strip_html_plain(v))  # HTML → text
            k = re.sub(r'\s+', ' ', k).strip().lower()  # collapse spaces + lowercase
            return k or None  # return normalized or None if empty after cleanup
        return str(v).strip().lower()  # non-string fallback normalization

    def extract_products(self):
        products = []  # accumulator for extracted product dicts

        # site-level regex bundle
        rx = self.site_cfg["regexes"]
        fl = flags(rx.get("flags"))
        body_re = re.compile(rx["body_regex"], fl)  # precompile <body> (or equivalent) extractor

        storage_dir = Path("data/storage")  # source directory with raw HTML files
        storage = sorted(storage_dir.glob("*.html"))
        total = len(storage)

        import traceback
        product_id = 1
        seen = set()  # set of normalized keys we've already accepted
        for i, html_path in enumerate(storage):
            if i % 100 == 0:
                print(f"[{i}/{total}] processed so far | added={len(products)} | last={html_path.name}", flush=True)  # periodic progress

            try:
                html = html_path.read_text(encoding="utf-8", errors="ignore")  # robust file read
                m = body_re.search(html)  # limit parsing to body block if available
                body = m.group(1) if m else html  # fallback if no <body> match

                parsed = self.parse_product_html(body, rx, html_path.name)  # extract fields from HTML body
                required = ("name", "price")  # minimal completeness gate

                if all(parsed.get(k) is not None for k in required):  # keep only valid products
                    parsed["source_file"] = str(html_path)  # provenance for traceability

                    field =  "name"  # choose field to dedupe by
                    key = self._dedupe_key(parsed, field) if field else None  # normalize to a comparable key

                    if key is not None and key in seen:
                        continue  # already accepted a record for this key

                    if key is not None:
                        seen.add(key)  # remember this key as accepted

                    parsed["product_id"] = product_id  # attach local incremental ID
                    product_id += 1  # advance counter
                    products.append(parsed)  # store result
            except Exception:
                print(f"ERROR in processing file {html_path.name}", flush=True)  # file-level error logging
                traceback.print_exc()  # debug stack trace for diagnostics
                continue  # skip to next file

        # optional final summary
        used_field =  "name"  # echo dedupe criterion
        print(f"Done. Files: {total}, products added: {len(products)}")  # run summary
        return products  # full list of parsed product records

    def save_products(self, products):
        out_path = self.app_cfg["products_path"]
        p = Path(out_path)
        mode = "w"  # overwrite output on each run
        with p.open(mode, encoding="utf-8") as f:
            for rec in products:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"path": str(p), "count": len(products)}  # simple write summary
