import json
import re
from pathlib import Path
from html import unescape
from my_utils import strip_html_plain, flags  # project helpers: strip HTML to text; translate flag strings to re flags


class Tester:
    def __init__(self, extractor, app_cfg: dict):
        self.extractor = extractor                          # extractor must expose .parse_product_html(...) + .site_cfg
        self.unit_tests_path = app_cfg["unit_tests_path"]            # line-delimited JSON (NDJSON) with expected fields
        self.rx = extractor.site_cfg["regexes"]              # regex config taken from site configuration
        self._body_re = re.compile(self.rx["body_regex"],         # compile main body-cropping regex once
                                   flags(self.rx.get("flags")))
        self.fields = set()  # will be populated from extracted entities only  # dynamic field set discovered during tests

    # -------- basics --------
    def _norm(self, v):
        if v is None:
            return None                                     # keep None distinct
        s = unescape(str(v))                      # decode HTML entities (&amp; -> &)
        s = strip_html_plain(s)                   # remove tags/markup -> plain text
        s = re.sub(r"\s+", " ", s).strip().lower()     # normalize whitespace + case-fold
        return s

    def _eq_scalar(self, a, b):
        return self._norm(a) == self._norm(b)                    # normalized string equality for scalars

    def _eq_list(self, a, b):
        if a is None and b is None:
            return True                                       # treat both missing as equal
        if not isinstance(a, list) or not isinstance(b, list):
            return False                               # type mismatch
        if len(a) != len(b):
            return False                                 # length mismatch
        for x, y in zip(a, b):                      # order-sensitive element-wise compare
            if self._norm(x) != self._norm(y):
                return False
        return True

    def _eq_unit_bundle(self, a, b):
        if a is None and b is None:
            return True
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        return (self._eq_scalar(a.get("price"), b.get("price"))     # compare structured price/unit pair
                and self._eq_scalar(a.get("unit"), b.get("unit")))

    def _eq_nutrition(self, a, b):
        if a is None and b is None:
            return True
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        keys = set(a.keys()) | set(b.keys())                        # union ensures missing keys are checked as None
        for k in keys:
            if not self._eq_scalar(a.get(k), b.get(k)):
                return False
        return True

    def _eq_field(self, field, expected, got):
        if field == "ingredients":
            return self._eq_list(expected, got)       # list equality (order-sensitive)
        if field == "unit_bundle":
            return self._eq_unit_bundle(expected, got)        # dict with price/unit
        if field == "nutrition_table":
            return self._eq_nutrition(expected, got)      # dict of nutrients
        return self._eq_scalar(expected, got)       # default: scalar compare

    # -------- IO --------
    def _load_tests(self):
        with open(self.unit_tests_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()] # load NDJSON: one JSON object per non-empty line

    # -------- single loop test (no try/except, no static fields) --------
    def test(self):
        tests = self._load_tests()
        total = len(tests)            # number of records to test (used as denominator)
        passed = {}  # field -> count

        for rec in tests:
            src = rec["source_file"]                    # path to the saved HTML file for this test case
            html = Path(src).read_text(encoding="utf-8", errors="ignore")
            m = self._body_re.search(html)                     # crop to body region
            body = m.group(1) if m else html                        # fallback: use whole HTML if no match
            extracted = self.extractor.parse_product_html(          # run extractor on the (possibly cropped) HTML
                body, self.rx, Path(src).name
            )

            # only compare fields present on THIS extracted entity    # avoids penalizing fields the extractor didn't emit
            for f in extracted.keys():
                self.fields.add(f)                                  # collect dynamic set of seen fields
                if self._eq_field(f, rec.get(f), extracted.get(f)): # compare expected vs got using field-aware equality
                    passed[f] = passed.get(f, 0) + 1                # increment per-field pass counter

        # print stats for every field discovered from extracted entities
        print(f"Unit tests for REGEXES: {total} (in alphabetical order)")  # headline with total test count
        for f in sorted(self.fields):                               # stable alphabetical listing of fields
            print(f"{f} REGEX accuracy: {passed.get(f, 0)}/{total}")# per-field accuracy against total cases

        return passed, total          # allow callers to use raw counts programmatically
