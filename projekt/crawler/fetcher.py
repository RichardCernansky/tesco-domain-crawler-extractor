import time, requests, random
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import undetected_chromedriver.v2 as uc  # Import the correct version of undetected_chromedriver
from undetected_chromedriver.v2 import Chrome, ChromeOptions

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
        pool = self.app_cfg.get("user_agents")
        return random.choice(pool).strip()

    def _pick_proxy(self) -> str:
        """Pick a random proxy from the list."""
        proxy_pool = self.app_cfg.get("proxy_list")
        return random.choice(proxy_pool).strip()

    def rotate_user_agent(self) -> bool:
        """Rotate UA on the same driver via CDP (does not recreate the driver)."""
        ua = self._pick_user_agent()
        try:
            self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
            self.current_user_agent = ua
            print(f"User-Agent rotated to: {ua}")
            return True
        except Exception:
            return False

    def _set_proxy(self, proxy):

        """Set the proxy on the Chrome driver."""
        options = ChromeOptions()
        options.add_argument(f'--proxy-server={proxy}')
        self.driver = Chrome(options=options)

    def rotate_proxy(self):
        """Rotate the proxy by restarting the driver."""
        proxy = self._pick_proxy()  # Pick a random proxy from the list
        try:
            # Set a new proxy by restarting the driver with the new proxy
            if self.driver:
                self.driver.quit()  # Quit the previous driver instance

            self._set_proxy(proxy)
            print(f"Proxy rotated to: {proxy}")
            return True
        except Exception as e:
            print(f"Failed to rotate proxy: {e}")
            return False

    def _create_driver(self, profile_dir: str | None = None):
        import undetected_chromedriver.v2 as uc  # Correct import for undetected_chromedriver v2

        ua = self._pick_user_agent()  # Pick a random user agent from the pool
        opts = uc.ChromeOptions()  # Set Chrome options

        opts.add_argument("--lang=en-GB")
        opts.add_argument("--window-size=1280,2000")
        opts.add_argument("--disable-blink-features=AutomationControlled")  # Avoid automation detection
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument(f"--user-agent={ua}")  # Set the user-agent at startup

        # Add profile directory if provided
        if profile_dir:
            opts.add_argument(f"--user-data-dir={profile_dir}")  # Use a specific user profile

        # Do not add --headless argument, no headless mode will be used
        # opts.add_argument("--headless")  # Removed headless mode

        # Initialize Chrome with undetected_chromedriver
        driver = uc.Chrome(options=opts)  # Automatically handles chromedriver path

        # Set timeouts for the driver
        driver.set_page_load_timeout(self.app_cfg.get("page_load_timeout"))
        driver.set_script_timeout(self.app_cfg.get("script_timeout"))

        # Also override the user-agent via CDP (for network subrequests)
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
        except Exception:
            pass

        # Store the current user agent
        self.current_user_agent = ua
        return driver  # Return the created driver

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
