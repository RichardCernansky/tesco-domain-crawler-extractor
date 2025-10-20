import json
from pathlib import Path
from my_utils import *
from html import unescape

class Extractor:

    def __init__(self, site_cfg, app_cfg):
        self.site_cfg = site_cfg
        self.app_cfg = app_cfg

        #add body regex
        return

    def get_name(self, html, rx, fl):
        name_m = re.search(rx["name_regex"], html)
        name = unescape(name_m.group(1).strip()) if name_m else None
        return name

    def get_ingredients(self, html, rx, fl):
        ingredients = None
        m = re.search(rx["ingredients_regex"], html)
        if m:
            inner = m.group(1)
            inner_stripped = strip_html_plain(inner)
            ingredients = get_ingredients(inner_stripped)

        return ingredients

    def get_price_and_currency(self, html, rx, fl):
        # Try each regex pattern in order
        for key, price_regex in rx["price_regexes"].items():
            price_m = re.search(price_regex, html)
            if price_m:
                # Capture the currency symbol, main price, and unit price
                cur = '£'  # Assuming the currency is always GBP, as per the example
                price = price_m.group(1)  # The main price, e.g., 1.99
                # unit_price =price_m.group(2).split('/')[0]  # The unit price (e.g., 7.96 from 7.96/kg)
                # unit_quant = None  # You may not need to capture this unless it's given
                # unit = price_m.group(2).split('/')[1]  # The unit, e.g., kg from 7.96/kg
                # unit_bundle = {"price": unit_price, "unit": unit}

                return cur, price, None

        return None, None, None  # Return None if no match is found

    def get_brand(self, html, rx, fl):
        #brand
        brand = None
        b1 = re.search(rx["brand_regex"], html)
        if b1:
            brand = unescape(b1.group(1).strip())
        return brand

    def get_category(self, html, rx, fl):
        cm = re.search(rx["category_regex"], html)
        category = unescape(cm.group(1).strip()) if cm else None
        return category

    def get_description(self, html, rx, fl):
        # description
        dm = re.search(rx["description_regex"], html)
        description = None
        if dm:
            block = dm.group(1)
            raw_lines = re.findall(rx["description_lines_regex"], block)
            lines = []
            for s in raw_lines:
                t = unescape(strip_html_plain(s).strip())
                if t:
                    lines.append(t)
            description_lines = lines or None
            description = " ".join(description_lines) if description_lines else None
        return description

    def get_nutrition_table(self, html, rx, fl):
        nut_rx = rx.get("nutrition_regexes")
        out = {}
        for key, pattern in nut_rx.items():
            m = re.search(pattern, html)
            if m:
                val = unescape(strip_html_plain(m.group(1)).strip())
                out[key] = val
            else:
                out[key] = None

        return out

    def parse_product_html(self, html: str, rx: dict):
        fl = flags(rx.get("flags"))
        #name
        name = self.get_name(html, rx, fl)
        ingredients = self.get_ingredients(html, rx, fl)
        currency, price, unit_bundle = self.get_price_and_currency(html, rx, fl)
        brand = self.get_brand(html, rx, fl)
        category = self.get_category(html, rx, fl)
        description = self.get_description(html, rx, fl)
        nutrition_table = self.get_nutrition_table(html, rx, fl)

        return {
            "name": name,
            "brand": brand,
            "price_currency": currency,
            "price": price,
            "ingredients": ingredients,
            "category": category,
            "description": description,
            "nutrition_table": nutrition_table,
            "unit_bundle": unit_bundle
        }

    def extract_products(self):
        products = []

        # site-level regex bundle
        rx = self.site_cfg["regexes"]
        fl = flags(rx.get("flags"))  # uses your my_utils.flags -> e.g., I|S
        body_re = re.compile(rx["body_regex"], fl)

        storage_dir = Path("data/storage")
        storage = sorted(storage_dir.glob("*.html"))
        total = len(storage)

        import traceback
        product_id = 1
        for i, html_path in enumerate(storage):
            if i % 100 == 0:
                print(f"[{i}/{total}] processed so far | added={len(products)} | last={html_path.name}", flush=True)

            try:
                html = html_path.read_text(encoding="utf-8", errors="ignore")
                m = body_re.search(html)
                body = m.group(1) if m else html  # fallback if no <body> match
                # parse using the same regexes under the "product" key
                parsed = self.parse_product_html(body, rx)
                required = ("name", "price")
                if all(parsed.get(k) is not None for k in required):
                    parsed["source_file"] = str(html_path)
                    parsed["product_id"] = product_id
                    product_id += 1
                    products.append(parsed)
            except Exception:
                print(f"ERROR in processing file {html_path.name}", flush=True)
                traceback.print_exc()
                continue

        # optional final summary
        print(f"Done. Files: {total}, products added: {len(products)}")

        return products

    def save_products(self, products):
        out_path = self.app_cfg["products_path"]
        p = Path(out_path)
        mode = "w"
        with p.open(mode, encoding="utf-8") as f:
            for rec in products:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"path": str(p), "count": len(products)}