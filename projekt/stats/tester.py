import json
import re
from pathlib import Path
from html import unescape
from my_utils import strip_html_plain, flags  # already in your project


class Tester:
    def __init__(self, extractor, app_cfg: dict):
        self.extractor = extractor
        self.unit_tests_path = app_cfg["unit_tests_path"]
        self.rx = extractor.site_cfg["regexes"]
        self._body_re = re.compile(self.rx["body_regex"], flags(self.rx.get("flags")))
        self.fields = set()  # will be populated from extracted entities only

    # -------- basics --------
    def _norm(self, v):
        if v is None:
            return None
        s = unescape(str(v))
        s = strip_html_plain(s)
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _eq_scalar(self, a, b):
        return self._norm(a) == self._norm(b)

    def _eq_list(self, a, b):
        if a is None and b is None:
            return True
        if not isinstance(a, list) or not isinstance(b, list):
            return False
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if self._norm(x) != self._norm(y):
                return False
        return True

    def _eq_unit_bundle(self, a, b):
        if a is None and b is None:
            return True
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        return self._eq_scalar(a.get("price"), b.get("price")) and self._eq_scalar(a.get("unit"), b.get("unit"))

    def _eq_nutrition(self, a, b):
        if a is None and b is None:
            return True
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        keys = set(a.keys()) | set(b.keys())
        for k in keys:
            if not self._eq_scalar(a.get(k), b.get(k)):
                return False
        return True

    def _eq_field(self, field, expected, got):
        if field == "ingredients":
            return self._eq_list(expected, got)
        if field == "unit_bundle":
            return self._eq_unit_bundle(expected, got)
        if field == "nutrition_table":
            return self._eq_nutrition(expected, got)
        return self._eq_scalar(expected, got)

    # -------- IO --------
    def _load_tests(self):
        with open(self.unit_tests_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    # -------- single loop test (no try/except, no static fields) --------
    def test(self):
        tests = self._load_tests()
        total = len(tests)
        passed = {}  # field -> count

        for rec in tests:  # ONE LOOP
            src = rec["source_file"]
            html = Path(src).read_text(encoding="utf-8", errors="ignore")
            m = self._body_re.search(html)
            body = m.group(1) if m else html
            extracted = self.extractor.parse_product_html(body, self.rx, Path(src).name)

            # only compare fields present on THIS extracted entity
            for f in extracted.keys():
                self.fields.add(f)
                if self._eq_field(f, rec.get(f), extracted.get(f)):
                    passed[f] = passed.get(f, 0) + 1

        # print stats for every field discovered from extracted entities
        print(f"Unit tests: {total} (alphabetical order)")
        for f in sorted(self.fields):
            print(f"{f}: {passed.get(f, 0)}/{total}")

        return passed, total
