import os
import json
import re
import tiktoken

class Statistician:
    def __init__(self, app_config):
        self.app_config = app_config
        self.metadata_path = app_config["metadata_path"]  # path to NDJSON with file metadata
        self.products_path = app_config.get("products_path")  # path to products NDJSON (one JSON per line)
        enc_name = app_config.get("tiktoken_encoding")  # default, override via config for parity
        self.encoder = tiktoken.get_encoding(enc_name)  # instantiate encoder once for reuse

    def _flatten_to_text(self, obj):
        # Converts arbitrarily nested JSON (dict/list/str/number/None) into a single whitespace-separated string
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return " ".join(self._flatten_to_text(v) for v in obj.values())  # depth-first over values
        if isinstance(obj, (list, tuple)):
            return " ".join(self._flatten_to_text(v) for v in obj)  # concatenate list items
        return str(obj)  # fallback for numbers, bools, etc.

    def count_product_tokens(self):
        # Streams products.ndjson to avoid loading entire file into memory
        if not self.products_path or not os.path.exists(self.products_path):
            return 0
        total_tokens = 0
        with open(self.products_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    prod = json.loads(line)  # parse one product per line
                except json.JSONDecodeError:
                    continue  # skip malformed lines
                text = self._flatten_to_text(prod).strip()  # flatten the whole product record
                if text:
                    text_norm = re.sub(r"\s+", " ", text)  # normalize whitespace for stable counts
                    total_tokens += len(self.encoder.encode(text_norm))  # model-consistent token count
        return total_tokens

    def get_stats(self):
        # Aggregates file and size stats and classifies product pages as OK vs Error by HTML fingerprint
        total_files = 0
        total_size = 0
        product_files = 0
        product_size = 0
        bad_product_files = 0
        bad_product_size = 0

        # HTML substrings that flag blocked/guard pages (kept as lowercase-insensitive checks)
        BAD_TARGETS = [
            "browser has failed some security checks",
            "you don't have permission to access",
            "window.xmlhttprequest.prototype.send",
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

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)  # read one metadata record
                    path = entry.get("content_path")
                    url = entry.get("url", "")
                    if not path or not os.path.exists(path):
                        continue  # skip missing files

                    size = os.path.getsize(path)  # file size in bytes
                    total_files += 1
                    total_size += size

                    if "/products/" in url:  # classify as product based on URL pattern
                        product_files += 1
                        product_size += size

                        try:
                            with open(path, "r", encoding="utf-8", errors="ignore") as html_file:
                                content = html_file.read(200000)  # cap read to 200 KB for speed
                                # case-insensitive fingerprint match
                                if any(t.lower() in content.lower() for t in BAD_TARGETS):
                                    bad_product_files += 1
                                    bad_product_size += size
                        except Exception:
                            pass  # tolerate transient read errors
                except json.JSONDecodeError:
                    continue  # ignore malformed metadata lines

        non_product_files = total_files - product_files  # complement counts
        non_product_size = total_size - product_size
        ok_product_files = max(product_files - bad_product_files, 0)  # guard against negative on inconsistencies
        ok_product_size = max(product_size - bad_product_size, 0)

        def fmt_mb(b):
            return f"{b / (1024 ** 2):.2f} MB"  # human-readable MiB

        pct_total = lambda n: (n / total_files * 100) if total_files else 0  # % relative to all files
        pct_product = lambda n: (n / product_files * 100) if product_files else 0  # % relative to product subset

        tokens_in_products = self.count_product_tokens()  # tokenized size of products dataset

        dash_size = 100
        print("\nStorage Statistics\n" + "=" * dash_size)
        print(f"{'Category':<28} {'Count':>10} {'Size':>15} {'% of Total':>12} {'% of Product':>14}")
        print("-" * dash_size)
        print(f"{'All HTML files':<28} {total_files:>10} {fmt_mb(total_size):>15} {100.00:>12.2f} {'—':>14}")  # overall
        print(f"{'Non-product files':<28} {non_product_files:>10} {fmt_mb(non_product_size):>15} {pct_total(non_product_files):>12.2f} {'—':>14}")  # non-product
        print(f"{'Product files':<28} {product_files:>10} {fmt_mb(product_size):>15} {pct_total(product_files):>12.2f} {'100.00%' if product_files else '—':>14}")  # product
        print("-" * dash_size)
        print(f"{'!Error! product files':<28} {bad_product_files:>10} {fmt_mb(bad_product_size):>15} {pct_total(bad_product_files):>12.2f} {pct_product(bad_product_files):>14.2f}")  # error subset
        print(f"{'!OK! product files':<28} {ok_product_files:>10} {fmt_mb(ok_product_size):>15} {pct_total(ok_product_files):>12.2f} {pct_product(ok_product_files):>14.2f}")  # OK subset
        print("=" * dash_size)
        print(f"Number of tokens in {self.products_path}: {tokens_in_products:,}\n")  # final token count summary
