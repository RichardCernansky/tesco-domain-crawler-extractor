import json
from crawler.crawler import _crawl
from eval.evaluate import evaluate_products
import itertools


def get_products(configs_json: str,  workers: int = 8):
    all_products = []
    #go through all the configs

    with open(configs_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    out_path = cfg["products_output_path"]
    max_pages = cfg["max_pages"]
    with open(out_path, "w", encoding="utf-8") as out:
        # get products from one site and write into jsonl
        parsed_products = _crawl(cfg,  max_pages=max_pages, workers=workers)
        for p in parsed_products:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
        all_products.append(parsed_products)
    report = evaluate_products(itertools.chain.from_iterable(all_products))
    return report
