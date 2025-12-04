import argparse, json, time
from datetime import datetime
from services import fetch_pages, extract_products, build_index, query, stats, test, search_lucene
from pylucene.build_index import build_pylucene_index

from spark.jobs.html_to_products import parse_products_spark
from spark.jobs.postprocessing_extracted import run_postprocess
from spark.jobs.extract_unique_entities import extract_unique_entities
from spark.jobs.extract_wiki_articles import extract_wiki_articles
from spark.jobs.build_brand_lookup import build_brand_lookup
from spark.jobs.build_ingredient_lookup import build_ingredient_lookup
from spark.jobs.enrich_products import enrich_products


def build_arg_parser():
    ap = argparse.ArgumentParser(prog="client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c_fetch_pages = sub.add_parser("fetch-pages", help="Crawl products from ndjson configs (one per line).")
    c_extract_products = sub.add_parser("extract-products", help="Parse saved HTML files and emit NDJSON.")
    c_build_index = sub.add_parser("build-index", help="Build index.")
    c_stats = sub.add_parser("stats", help="Build index.")
    c_test = sub.add_parser("test", help="Build index.")

    c_spark_extract_products = sub.add_parser("spark-extract", help="Parse saved HTML files and emit NDJSON.")
    c_spark_eue = sub.add_parser("spark-eue", help="Extract distinct brands and ingredients for Wikipedia matching.")
    c_spark_ewa = sub.add_parser("spark-ewa", help="Parse Wikipedia XML dump and filter relevant articles.")
    c_spark_sbl = sub.add_parser("spark-build-lookups", help="Match entities to Wikipedia and extract structured data")
    c_spark_enrich = sub.add_parser("spark-enrich", help="Join products with Wikipedia enrichment data")

    c_search = sub.add_parser("search", help="Search in data using PyLucene index")
    c_bpi = sub.add_parser("build-pylucene-index", help="Build PyLucene index")
    c_search.add_argument("terms", nargs="+", metavar="terms")
    c_search.add_argument("--field", "-f", default=None, help="Single field to search")
    c_search.add_argument("--topk", type=int, default=10, help="Number of results")
    c_search.add_argument("--no-fuzzy", action="store_true", help="Disable fuzzy matching")

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

        started_at = datetime.now()
        print(f"[SEARCH] started at {started_at.isoformat(timespec='seconds')}")
        t0 = time.perf_counter()
        query(app_cfg, mode, q, top_k)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        print(f"[SEARCH] finished in {elapsed_ms:.2f} ms")
    elif args.cmd == "stats":
        stats(app_cfg)
    elif args.cmd == "test":
        test(site_cfg,app_cfg)

    # Spark
    elif args.cmd == "spark-extract":
        parse_products_spark(app_cfg, site_cfg)
        run_postprocess(app_cfg)
    elif args.cmd == "spark-eue":
        extract_unique_entities(app_cfg)
    elif args.cmd == "spark-ewa":
        extract_wiki_articles(app_cfg)
    elif args.cmd == "spark-build-lookups":
        build_brand_lookup(app_cfg)
        build_ingredient_lookup(app_cfg)
    elif args.cmd == "spark-enrich":
        enrich_products(app_cfg)

    # PyLucene
    elif args.cmd == "search":
        started_at = datetime.now()
        print(f"[SEARCH] started at {started_at.isoformat(timespec='seconds')}")
        t0 = time.perf_counter()
        search_lucene(app_cfg, args)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        print(f"[SEARCH] finished in {elapsed_ms:.2f} ms")
    elif args.cmd == "build-pylucene-index":
        build_pylucene_index()

    return


if __name__ == "__main__":
    main()
