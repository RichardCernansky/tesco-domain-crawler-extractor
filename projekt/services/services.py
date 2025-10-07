from crawler.crawler import Crawler
from extractor.extractor import Extractor

def fetch_pages(site_cfg: dict, app_cfg: dict):
    crawler = Crawler(site_cfg, app_cfg)
    crawler.crawl()
    crawler.fetcher.close()
    return

def extract_products(site_cfg: dict, app_cfg: dict):
    extractor = Extractor(site_cfg, app_cfg)
    extractor.extract_products()
    return
