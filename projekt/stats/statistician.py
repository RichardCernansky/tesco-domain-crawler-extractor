import os
import json
import re

class Statistician:
    def __init__(self, app_config):
        self.app_config = app_config
        self.metadata_path = app_config["metadata_path"]
        self.products_path = app_config.get("products_path")

    # flatten any JSON value (dict/list/scalars) into one string
    def _flatten_to_text(self, obj):
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return " ".join(self._flatten_to_text(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return " ".join(self._flatten_to_text(v) for v in obj)
        return str(obj)

    # count tokens in products.ndjson (concat all fields, split by " ")
    def count_product_tokens(self):
        if not self.products_path or not os.path.exists(self.products_path):
            return 0
        total_tokens = 0
        with open(self.products_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    prod = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = self._flatten_to_text(prod).strip()
                # normalize any whitespace to a single space so split(" ") is clean
                text_norm = re.sub(r"\s+", " ", text)
                if text_norm:
                    total_tokens += len(text_norm.split(" "))
        return total_tokens

    def get_stats(self):
        total_files = 0
        total_size = 0
        product_files = 0
        product_size = 0
        bad_product_files = 0  # contains "something is not right"
        bad_product_size = 0

        pattern = re.compile(r"browser\shas\sfailed\ssome\ssecurity\schecks", re.IGNORECASE)
        pattern = re.compile(r"You\sdon't\shave\spermission\sto\saccess", re.IGNORECASE)
        pattern = re.compile(r"window\.XMLHttpRequest\.prototype\.send", re.IGNORECASE)

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    path = entry.get("content_path")
                    url = entry.get("url", "")

                    if not path or not os.path.exists(path):
                        continue

                    size = os.path.getsize(path)
                    total_files += 1
                    total_size += size

                    if "/products/" in url:
                        product_files += 1
                        product_size += size

                        BAD_TARGETS = [
                            "browser has failed some security checks",
                            "You don't have permission to access",
                            "window.XMLHttpRequest.prototype.send",
                            # full HTML snippet target:
                            """<html><head></head><body>
                              <script src="/j3K7pd/P/c/t5S2UpFdcA/Qfup2pJaVO/NWB0Q0Z-JAw/VmkXPVdK/ZDJp?v=062000b0-b448-f78a-7295-7d0d39da6853&amp;t=919040508"></script>
                              <script>
                                 (function() {
                                     var chlgeId = '';
                                     var scripts = document.getElementsByTagName('script');
                                     for (var i = 0; i < scripts.length; i++) {
                                         if (scripts[i].src && scripts[i].src.match(/t=([^&#]*)/)) {
                                             chlgeId = scripts[i].src.match(/t=([^&#]*)/)[1];
                                         }
                                     }
                                     var proxied = window.XMLHttpRequest.prototype.send;
                                     window.XMLHttpRequest.prototype.send = function() {
                                         var pointer = this
                                         var intervalId = window.setInterval(function() {
                                             if (pointer.readyState === 4 && pointer.responseURL && pointer.responseURL.indexOf('t=' + chlgeId) > -1) {
                                                 location.reload(true);
                                                 clearInterval(intervalId);
                                             }
                                         }, 1);
                                         return proxied.apply(this, [].slice.call(arguments));
                                     };
                                 })();
                              </script>
                            </body></html>""",
                        ]

                        # open the file and check for the phrase
                        try:
                            with open(path, "r", encoding="utf-8", errors="ignore") as html_file:

                                content = html_file.read(200000)  # only peek first 20KB
                                if any(t.lower() in content.lower() for t in BAD_TARGETS):
                                    bad_product_files += 1
                                    bad_product_size += size  # NEW
                        except Exception:
                            pass

                except json.JSONDecodeError:
                    continue

        non_product_files = total_files - product_files
        non_product_size = total_size - product_size

        # bad/ok among product files
        ok_product_files = max(product_files - bad_product_files, 0)
        ok_product_size = max(product_size - bad_product_size, 0)

        def fmt_mb(b):
            return f"{b / (1024 ** 2):.2f} MB"

        pct_total = lambda n: (n / total_files * 100) if total_files else 0
        pct_product = lambda n: (n / product_files * 100) if product_files else 0

        tokens_in_products = self.count_product_tokens()

        dash_size = 100
        print("\nStorage Statistics\n" + "=" * dash_size)
        print(f"{'Category':<28} {'Count':>10} {'Size':>15} {'% of Total':>12} {'% of Product':>14}")
        print("-" * dash_size)
        # 1) All files
        print(f"{'All HTML files':<28} {total_files:>10} {fmt_mb(total_size):>15} {100.00:>12.2f} {'—':>14}")
        # 2) Non-product files
        print(
            f"{'Non-product files':<28} {non_product_files:>10} {fmt_mb(non_product_size):>15} {pct_total(non_product_files):>12.2f} {'—':>14}")
        # 3) Product files
        print(
            f"{'Product files':<28} {product_files:>10} {fmt_mb(product_size):>15} {pct_total(product_files):>12.2f} {'100.00%' if product_files else '—':>14}")
        print("-" * dash_size)
        # 4) Bad files (subset of product)
        print(
            f"{'!Error! product files':<28} {bad_product_files:>10} {fmt_mb(bad_product_size):>15} {pct_total(bad_product_files):>12.2f} {pct_product(bad_product_files):>14.2f}")
        # 5) OK files (product - bad)
        print(
            f"{'!OK! product files':<28} {ok_product_files:>10} {fmt_mb(ok_product_size):>15} {pct_total(ok_product_files):>12.2f} {pct_product(ok_product_files):>14.2f}")
        print("=" * dash_size)

        print(f"Number of tokens in {self.products_path}: {tokens_in_products:,}\n")