import re
from html import unescape
import json
from typing import Dict, List, Tuple, Any

def flags(flag_list):
    f = 0
    if not flag_list:
        return f
    for x in flag_list:
        u = x.upper()
        if u == "I": f |= re.IGNORECASE
        if u == "S": f |= re.DOTALL
        if u == "M": f |= re.MULTILINE
    return f

def get_ingredients(inner: str):
    def split_ingredients(s: str, sep: str):
        parts, buf, depth = [], [], 0
        for ch in s:
            if ch == '(':
                depth += 1
            elif ch == ')' and depth > 0:
                depth -= 1
            if ch == sep and depth == 0:
                part = ''.join(buf).strip()
                if part: parts.append(part)
                buf = []
            else:
                buf.append(ch)
        tail = ''.join(buf).strip()
        if tail: parts.append(tail)
        return parts

    first_level_parts = split_ingredients(inner, ",")
    second_level_parts = []
    for p in first_level_parts:
        ingredient_split = split_ingredients(p, " ")
        for s in ingredient_split:
            has_number = any(ch.isdigit() for ch in s)
            if has_number:
                continue  # skip this s
            t = (s or "").strip(" ()[]")
            if t:
                second_level_parts.append(t)


    all_ingredients = []
    for p in second_level_parts:
        if ',' in p:
            all_ingredients.extend(split_ingredients(p, ","))
        else:
            all_ingredients.append(p)
    return all_ingredients

def strip_html_plain(s: str) -> str:
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?is)<!--.*?-->', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>', ' ', s)
    s = re.sub(r'(?i)</(p|div|li|tr|th|td|h[1-6])\s*>', ' ', s)
    s = re.sub(r'(?s)<[^>]*>', ' ', s)
    s = unescape(s).replace('\xa0', ' ')
    s = s.replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r'^\s*ingredients?\s*[:\-\u2013\u2014]\s*', '', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' .;,[]')

def load_jsonl(path: str) -> List[dict]:
    docs=[]
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            docs.append(json.loads(line))
    return docs

def build_products_by_id(products: List[dict]) -> Dict[int, dict]:
    out = {}
    for p in products:
        pid = p.get("product_id")
        if pid is None:
            continue
        out[int(pid)] = p
    return out

def join_hits(hits: List[Tuple[int, float]], products_by_id: Dict[int, dict], fields=("name","brand","category")) -> List[dict]:
    out = []
    for did, score in hits:
        meta = products_by_id.get(int(did))
        if not meta:
            continue
        row = {"id": int(did), "score": float(score)}
        for f in fields:
            row[f] = meta.get(f)
        out.append(row)
    return out

