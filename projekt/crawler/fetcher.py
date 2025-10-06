import time, re, requests
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser
from my_utils import *


UA = "Mozilla/5.0 (compatible; ProductCrawler/1.0)"
ROBOTS_CACHE, ROBOTS_TIME = {}, {}
ROBOTS_TTL = 60 * 60
BODY_INNER_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body\s*>")

class Fetcher:
    def __init__(self):
        return

    def _get_rp(self, url: str) -> robotparser.RobotFileParser:
        parsed = urlparse(url)
        netloc = parsed.netloc
        now = time.time()
        rp = ROBOTS_CACHE.get(netloc)
        if rp and (now - ROBOTS_TIME.get(netloc, 0) < ROBOTS_TTL):
            return rp
        robots_url = f"{parsed.scheme}://{netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            r = requests.get(robots_url, headers={"User-Agent": UA}, timeout=5)
            rp.parse([] if r.status_code >= 400 else r.text.splitlines())
        except Exception:
            rp.parse([])
        ROBOTS_CACHE[netloc] = rp
        ROBOTS_TIME[netloc] = now
        return rp


    def _accept_cookies(self, driver, timeout_per_try=2):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            WebDriverWait(driver, timeout_per_try).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')]"))
            ).click()
            return True
        except Exception:
            return False


    def fetch_html_dynamic(
        self,
        url: str,
        profile_dir: str | None = None,
        headless: bool = True,
        wait_selector: str | None = None,
        timeout: int = 2,
        respect_robots: bool = True,
        return_body_only: bool = False,
        driver=None,
        retries: int = 0
    ) -> str:
        if respect_robots:
            rp = self._get_rp(url)
            if not rp.can_fetch(UA, url):
                raise PermissionError(f"Blocked by robots.txt: {url}")
        _own = False
        if driver is None:
            driver = create_driver(profile_dir=profile_dir, headless=headless)
            _own = True
        try:
            driver.get(url)
            self._accept_cookies(driver, timeout_per_try=timeout)
            html = driver.page_source
            if return_body_only:
                m = BODY_INNER_RE.search(html)
                return m.group(1) if m else ""
            return html
        finally:
            if _own:
                driver.quit()

    def fetch_tesco_list_html(self, url: str, driver=None, headless=False, respect_robots=True) -> str:
        profile = str(Path.home() / ".uc" / "tesco-profile-3")
        return self.fetch_html_dynamic(
            url=url,
            profile_dir=profile,
            respect_robots=respect_robots,
            return_body_only=True,
            driver=driver,
            timeout=2,
            retries=0,
        )
