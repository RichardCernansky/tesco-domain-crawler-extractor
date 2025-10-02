# eval/evaluate.py
from collections import Counter

def evaluate_products(products_iter):
    """
    products_iter: iterable of dicts with keys {site, url, name, brand, price}
    Returns small dict + prints a short summary.
    """
    n = 0
    missing = Counter()
    by_site = Counter()
    for p in products_iter:
        n += 1
        by_site[p.get("site","?")] += 1
        if not p.get("name"):  missing["name"]  += 1
        if p.get("price") is None: missing["price"] += 1
        if not p.get("brand"): missing["brand"] += 1

    report = {
        "total_products": n,
        "by_site": dict(by_site),
        "missing_fields": dict(missing),
    }
    return report
