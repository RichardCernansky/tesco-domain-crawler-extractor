import argparse, json
from services.services import fetch_pages


def build_arg_parser():
    ap = argparse.ArgumentParser(prog="crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    gp = sub.add_parser("fetch-pages", help="Crawl products from ndjson configs (one per line).")
    gp.add_argument("--max-pages", type=int, default=0, help="Max listing pages per site (0 = all).")
    gp.add_argument("--workers", type=int, default=8, help="Thread workers.")

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

    elif args.cmd == "get-product":
        print("[OK] products written to", "data/products.ndjson")


if __name__ == "__main__":
    main()
