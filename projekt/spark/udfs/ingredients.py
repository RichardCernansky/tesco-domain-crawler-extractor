# at top of spark/jobs/html_to_products.py
import re
from html import unescape

# --- your original helpers, just made None-safe -----------------
def strip_html_plain(s: str) -> str | None:
    if not s:
        return None
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?is)<!--.*?-->', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>', ' ', s)
    s = re.sub(r'(?i)</(p|div|li|tr|th|td|h[1-6])\s*>', ' ', s)
    s = re.sub(r'(?s)<[^>]*>', ' ', s)
    s = unescape(s).replace('\xa0', ' ')
    s = s.replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r'^\s*ingredients?\s*[:\-\u2013\u2014]\s*', '', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip(' .;,[]')
    return s or None

def get_ingredients(inner: str) -> list[str] | None:
    if not inner:
        return None

    def split_ingredients(s: str, sep: str):
        parts, buf, depth = [], [], 0
        for ch in s:
            if ch == '(':
                depth += 1
            elif ch == ')' and depth > 0:
                depth -= 1
            if ch == sep and depth == 0:
                part = ''.join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
            else:
                buf.append(ch)
        tail = ''.join(buf).strip()
        if tail:
            parts.append(tail)
        return parts

    first_level_parts = split_ingredients(inner, ",")
    second_level_parts = []
    for p in first_level_parts:
        ingredient_split = split_ingredients(p, " ")
        for s in ingredient_split:
            if any(ch.isdigit() for ch in s):
                continue
            t = (s or "").strip(" ()[]")
            if t:
                second_level_parts.append(t)

    all_ingredients = []
    for p in second_level_parts:
        if ',' in p:
            all_ingredients.extend(split_ingredients(p, ","))
        else:
            all_ingredients.append(p)

    return all_ingredients or None



