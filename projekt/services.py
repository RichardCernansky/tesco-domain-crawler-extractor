from crawler.crawler import Crawler
from extractor.extractor import Extractor
from indexer.builder import IndexBuilder
from indexer.index import Index
from my_utils import load_jsonl, build_products_by_id, join_hits


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
    for r in results:
        print(f"Product ID: {r['id']}| ", f"Score: {r['score']:.3f}| ", r.get("name", ""), r.get("brand", ""), r.get("category", ""))

    return