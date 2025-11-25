from crawler.crawler import Crawler
from extractor.extractor import Extractor
from indexer.builder import IndexBuilder
from indexer.index import Index
from stats.statistician import Statistician
from my_utils import load_jsonl, build_products_by_id, join_hits
from stats.tester import Tester
from pylucene.searcher import search_products

def fetch_pages(site_cfg: dict, app_cfg: dict):
    crawler = Crawler(site_cfg, app_cfg)
    crawler.crawl()
    crawler.fetcher.close()
    return

def extract_products(site_cfg: dict, app_cfg: dict):
    extractor = Extractor(site_cfg, app_cfg)
    products = extractor.extract_products()
    stats = extractor.save_products(products)
    print(stats)
    return


def build_index( app_cfg: dict):
    builder = IndexBuilder(app_cfg)
    docs = load_jsonl(app_cfg['products_path'])
    built = builder.build(docs)
    builder.save(built, app_cfg['index_path'])
    return

def query(app_cfg: dict, mode, q, top_k):
    index = Index(app_cfg)
    products = load_jsonl(app_cfg["products_path"])  # or however you load them
    products_by_id = build_products_by_id(products)
    hits = index.search(mode, q, top_k)
    results = join_hits(hits, products_by_id)
    for i,r in enumerate(results):
        print(f"{i+1}. Product ID: {r['id']}| Score: {r['score']:.3f}| {r.get('name', '')} | {r.get('brand', '')} | {r.get('category', '')}")

    return

def stats(app_config: dict):
    sr = Statistician(app_config)
    sr.get_stats()
    return

def test(site_config:dict, app_config:dict):
    extractor = Extractor(site_config, app_config)
    tester = Tester(extractor, app_config)
    tester.test()
    return

def search_lucene(app_config: dict, args):
    q = " ".join(args.terms)
    fuzzy = not args.no_fuzzy
    results = search_products(q, top_k=args.topk, field=args.field, fuzzy=fuzzy)
    for i, r in enumerate(results, 1):
        name = r.get("name") or ""
        brand = r.get("brand") or ""
        category = r.get("category") or ""
        price = r.get("price_num") or ""
        score = r.get("score") or 0.0
        print(f"{i}. [{score:.2f}] {name}")
        print(f"   Brand: {brand} | Category: {category} | Price: {price}")

