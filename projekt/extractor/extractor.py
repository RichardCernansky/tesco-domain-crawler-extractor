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
        price_m = re.search(rx["price_regex"], html)
        cur, price = (None, None)
        unit_bundle = None
        if price_m:
            gcurr, gprice, gunit_price, gper_quantity, gper_unit = 1,2,4,5,6
            cur = price_m.group(gcurr).strip()
            price = float(price_m.group(gprice))
            unit_price = float(price_m.group(gunit_price))
            unit_quant = float(price_m.group(gper_quantity))
            unit = price_m.group(gper_unit)
            unit_bundle = {"price": unit_price, "quantity": unit_quant, "unit": unit}
        return (cur, price, unit_bundle)

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

        for i, html_path in enumerate(storage):
            if i % 100 == 0:
                print(f"[{i}/{total}] processed so far | added={len(products)} | last={html_path.name}", flush=True)

            try:
                html = html_path.read_text(encoding="utf-8", errors="ignore")
                m = body_re.search(html)
                body = m.group(1) if m else html  # fallback if no <body> match
                # parse using the same regexes under the "product" key
                parsed = self.parse_product_html(body, rx)
                required = ("name",  "price")
                if all(parsed.get(k) is not None for k in required):
                    parsed["source_file"] = str(html_path)
                    products.append(parsed)
            except Exception:
                print(f"ERROR in processing file {html_path.name}", flush=True)
                continue

        # optional final summary
        print(f"Done. Files: {total}, products added: {len(products)}")

        return products

    def save_products(self, products):
        out_path = self.app_cfg["products_out_path"]
        p = Path(out_path)
        mode = "w"
        with p.open(mode, encoding="utf-8") as f:
            for rec in products:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"path": str(p), "count": len(products)}