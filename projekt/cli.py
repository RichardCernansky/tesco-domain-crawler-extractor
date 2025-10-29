import argparse, json
from services import fetch_pages, extract_products, build_index, query, stats, test


def build_arg_parser():
    ap = argparse.ArgumentParser(prog="crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c_fetch_pages = sub.add_parser("fetch-pages", help="Crawl products from ndjson configs (one per line).")
    c_extract_products = sub.add_parser("extract-products", help="Parse saved HTML files and emit NDJSON.")
    c_build_index = sub.add_parser("build-index", help="Build index.")
    c_stats = sub.add_parser("stats", help="Build index.")
    c_test = sub.add_parser("test", help="Build index.")

    p_query = sub.add_parser("query")
    p_query.add_argument("--mode", choices=["idf", "idf_l2"], required=True)
    p_query.add_argument("--topk", type=int, required=True)
    p_query.add_argument("terms", nargs="+", metavar="terms", help="Use at least one query token.")

    return ap

def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    site_config = "data/configs/site_config.json"
    app_config = "data/configs/app_config.json"

    with open(site_config, "r", encoding="utf-8") as f:
        site_cfg = json.load(f)
    with open(app_config, "r", encoding="utf-8") as f:
        app_cfg = json.load(f)

    if args.cmd == "fetch-pages":
        fetch_pages(site_cfg, app_cfg)
    elif args.cmd == "extract-products":
        extract_products(site_cfg, app_cfg)
        print("[OK] products written to", "data/products.ndjson")
    elif args.cmd == "build-index":
        build_index(app_cfg)
    elif args.cmd == "query":
        mode = args.mode
        q = " ".join(args.terms)
        top_k = int(args.topk)
        query(app_cfg, mode, q, top_k)
    elif args.cmd == "stats":
        stats(app_cfg)
    elif args.cmd == "test":
        test(site_cfg,app_cfg)


if __name__ == "__main__":
    main()
