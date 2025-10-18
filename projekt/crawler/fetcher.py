import time, requests, random
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# robots.txt cache (per-host)
ROBOTS_CACHE, ROBOTS_TIME = {}, {}
ROBOTS_TTL = 60 * 60  # seconds

class Fetcher:
    def __init__(self, crawler):
        self.crawler = crawler
        self.app_cfg = crawler.app_cfg
        self.current_user_agent = None

        self.profile = self._get_profile()
        self.driver = self._create_driver(self.profile)

    # ---------- setup helpers ----------

    def _get_profile(self) -> str:
        """Pick a profile dir (random from uc_profiles if provided, else uc_profile)."""
        base = Path.home() / ".uc"
        name = self.app_cfg.get("uc_profile")
        return str(base / name)

    def _pick_user_agent(self) -> str:
        """Pick a random UA from config or fallback pool."""
        pool = self.app_cfg.get("user_agents") or [
            # sensible desktop Chromium UAs as fallback
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/126.0.0.0 Chrome/126.0.0.0 Safari/537.36",
        ]
        return random.choice(pool).strip()

    def _create_driver(self, profile_dir: str | None = None):
        import undetected_chromedriver as uc

        ua = self._pick_user_agent()
        opts = uc.ChromeOptions()
        opts.add_argument("--lang=en-GB")
        opts.add_argument("--window-size=1280,2000")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument(f"--user-agent={ua}")  # UA at startup

        if profile_dir:
            opts.add_argument(f"--user-data-dir={profile_dir}")

        driver = uc.Chrome(options=opts)
        # ---- timeouts on the driver ----
        driver.set_page_load_timeout(self.app_cfg.get("page_load_timeout"))
        driver.set_script_timeout(self.app_cfg.get("script_timeout"))

        # Also override via CDP so subrequests match.
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
        except Exception:
            pass

        self.current_user_agent = ua
        return driver

    def rotate_user_agent(self) -> bool:
        """Rotate UA on the same driver via CDP (does not recreate the driver)."""
        ua = self._pick_user_agent()
        try:
            self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
            self.current_user_agent = ua
            return True
        except Exception:
            return False

    # ---------- robots.txt ----------

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
            headers = {"User-Agent": self.current_user_agent or "Mozilla/5.0"}
            timeout_s = random.uniform(3, 5)
            r = requests.get(robots_url, headers=headers, timeout=timeout_s)
            rp.parse([] if r.status_code >= 400 else r.text.splitlines())
        except Exception:
            rp.parse([])

        ROBOTS_CACHE[netloc] = rp
        ROBOTS_TIME[netloc] = now
        return rp

    # ---------- cookies ----------

    def _cookies_accepted(self, driver, names=("OptanonConsent", "OptanonAlertBoxClosed")) -> bool:
        """Quick check for common OneTrust cookies."""
        now = int(time.time())
        try:
            for name in names:
                c = driver.get_cookie(name)
                if not c:
                    continue
                if "expiry" not in c or not isinstance(c["expiry"], (int, float)) or c["expiry"] > now:
                    return True
            return False
        except Exception:
            return False

    def _accept_cookies(self, driver, timeout) -> bool:
        """Minimal cookie clicker for a simple 'Accept all' button."""
        try:
            WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')]"))
            ).click()
            print("Cookies accepted.")
            return True
        except Exception:
            return False

    # ---------- main API ----------

    def fetch_html(self, url: str) -> str:
        """Get HTML with robots.txt check & minimal cookie handling."""
        # robots.txt enforcement using the same UA as the driver
        rp = self._get_rp(url)
        ua = self.current_user_agent or "Mozilla/5.0"
        if not rp.can_fetch(ua, url):
            raise PermissionError(f"Blocked by robots.txt: {url}")

        d = self.driver
        d.get(url)

        if not self._cookies_accepted(d):
            self._accept_cookies(d)

        WebDriverWait(d, self.app_cfg["driver_load_timeout"]).until(
            lambda drv: drv.execute_script("return document.readyState") in ("interactive", "complete")
        )
        return d.page_source

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass
