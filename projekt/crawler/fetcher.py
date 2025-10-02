import os, time, re, requests
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser


UA = "Mozilla/5.0 (compatible; ProductCrawler/1.0)"
ROBOTS_CACHE, ROBOTS_TIME = {}, {}
ROBOTS_TTL = 60 * 60
BODY_INNER_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body\s*>")

def _get_rp(url: str) -> robotparser.RobotFileParser:
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

# fetcher.py
def create_driver(profile_dir: str | None = None, headless: bool = True, driver_path: str | None = None):
    import undetected_chromedriver as uc
    opts = uc.ChromeOptions()
    opts.add_argument("--lang=en-GB")
    opts.add_argument("--window-size=1280,2000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-first-run"); opts.add_argument("--no-default-browser-check")
    if profile_dir:
        opts.add_argument(f"--user-data-dir={profile_dir}")
    if headless:
        opts.add_argument("--headless=new")

    # IMPORTANT: point UC at the preinstalled driver to avoid concurrent downloads
    if driver_path:
        driver = uc.Chrome(options=opts, driver_executable_path=driver_path)
    else:
        driver = uc.Chrome(options=opts)

    # (optional speed) block heavy assets
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": [
        "*.jpg","*.jpeg","*.png","*.gif","*.webp","*.svg",
        "*.woff","*.woff2","*.ttf","*.mp4","*.avi","*.m4v","*.mp3"
    ]})
    return driver

def _accept_cookies_fast(driver, timeout_per_try=2, xpaths=None, check_cookie_names: tuple[str, ...] = ("OptanonConsent", "OptanonAlertBoxClosed")):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    if xpaths is None:
        xpaths = [
            "//button[contains(., 'Accept all cookies')]",
            "//button[contains(., 'Accept all')]",
            "//button[@data-testid='accept-all']",
            "//button[contains(., 'Allow all')]",
            "//button[contains(., 'I agree')]",
        ]
    def click_here():
        for xp in xpaths:
            try:
                WebDriverWait(driver, timeout_per_try).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                ).click()
                print(xp)
                return True
            except Exception:
                pass
        return False
    driver.switch_to.default_content()
    if click_here():
        return True
    try:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        return False
    for fr in frames[:5]:
        try:
            driver.switch_to.frame(fr)
            if click_here():
                driver.switch_to.default_content()
                return True
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()
    return False

def fetch_html_dynamic(
    url: str,
    profile_dir: str | None = None,
    headless: bool = True,
    wait_selector: str | None = None,
    cookie_xpaths: list[str] | None = None,
    timeout: int = 2,
    respect_robots: bool = True,
    return_body_only: bool = False,
    driver=None,
    retries: int = 0
) -> str:
    if respect_robots:
        rp = _get_rp(url)
        if not rp.can_fetch(UA, url):
            raise PermissionError(f"Blocked by robots.txt: {url}")
    _own = False
    if driver is None:
        driver = create_driver(profile_dir=profile_dir, headless=headless)
        _own = True
    try:
        driver.get(url)
        # _accept_cookies_fast(driver, timeout_per_try=timeout, xpaths=cookie_xpaths)
        html = driver.page_source
        if return_body_only:
            m = BODY_INNER_RE.search(html)
            return m.group(1) if m else ""
        return html
    finally:
        if _own:
            driver.quit()

def fetch_tesco_list_html(url: str, driver=None, headless=True, respect_robots=True) -> str:
    profile = str(Path.home() / ".uc" / "tesco-profile")
    return fetch_html_dynamic(
        url=url,
        profile_dir=profile,
        headless=headless,
        cookie_xpaths=[
            "//button[contains(., 'Accept all cookies')]",
            "//button[contains(., 'Accept all')]",
            "//button[@data-testid='accept-all']",
            "//button[contains(., 'Allow all')]",
            "//button[contains(., 'I agree')]",
        ],
        respect_robots=respect_robots,
        return_body_only=True,
        driver=driver,
        timeout=2,
        retries=0,
    )
