import argparse, json
from services.get_products import get_products


def build_arg_parser():
    ap = argparse.ArgumentParser(prog="crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    gp = sub.add_parser("get-products", help="Crawl products from ndjson configs (one per line).")
    gp.add_argument("--max-pages", type=int, default=0, help="Max listing pages per site (0 = all).")
    gp.add_argument("--workers", type=int, default=8, help="Thread workers.")

    return ap

def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    if args.cmd == "get-products":
        report = get_products(
            configs_json="data/site_configs/configs.json",
            workers=args.workers
        )
        print("[OK] products written to", "data/products.ndjson")
        print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
