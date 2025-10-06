


def fetch_products(site_config: str, app_config: str,  workers: int = 8):
    all_products = []
    #go through all the configs

    with open(site_config, "r", encoding="utf-8") as f:
        site_cfg = json.load(f)
    with open(app_config, "r", encoding="utf-8") as f:
        app_cfg = json.load(f)

    out_path = app_cfg["products_output_path"]
    max_pages = site_cfg["max_pages"]

    with open(out_path, "w", encoding="utf-8") as out:
        # get products from one site and write into jsonl
        parsed_products = _crawl(site_cfg,  max_pages=max_pages, workers=workers)
        for p in parsed_products:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
        all_products.append(parsed_products)
    report = evaluate_products(itertools.chain.from_iterable(all_products))
    return report
