import time, requests, random, tempfile, shutil
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROBOTS_CACHE, ROBOTS_TIME = {}, {}
ROBOTS_TTL = 60 * 60

def _norm_proxy(p: str) -> str:
    p = p.strip()
    if not p:
        return ""
    if "://" in p:
        return p
    # nodemaven: host:port:user:pass
    parts = p.split(":", 3)
    if len(parts) == 4 and "@" not in p:
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if "@" in p:
        creds, addr = p.split("@", 1)
        if ":" in addr:
            return f"http://{creds}@{addr}"
        return f"http://{creds}@{addr}:80"
    if ":" in p:
        host, port = p.split(":", 1)
        return f"http://{host}:{port}"
    return f"http://{p}:80"

class Fetcher:
    def __init__(self, crawler):
        self.crawler = crawler
        self.app_cfg = crawler.app_cfg

        self.rotate_after_pages = int(self.app_cfg.get("proxy_rotate_after_pages", 5))
        self.max_attempts = int(self.app_cfg.get("proxy_max_attempts", 4))
        self.use_ephemeral_profile = bool(self.app_cfg.get("ephemeral_profile", True))

        self.proxies = self._load_proxies()
        self.current_user_agent = None
        self.current_proxy = None

        self.profile = self._get_profile()
        self.temp_profile_dir = None

        self.driver = None
        self._restart_driver()
        self._pages_left = self.rotate_after_pages

    def _load_proxies(self):
        out = []
        lst = self.app_cfg.get("proxies") or []
        out.extend(lst if isinstance(lst, list) else [])
        pth = self.app_cfg.get("proxies_path")
        if pth:
            for line in Path(pth).read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.strip().startswith("#"):
                    out.append(line.strip())
        out = [_norm_proxy(p) for p in out if p.strip()]
        out = list(dict.fromkeys(out))
        return out

    def _pick_proxy(self) -> str | None:
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def _get_profile(self) -> str:
        base = Path.home() / ".uc"
        name = self.app_cfg.get("uc_profile") or "default"
        return str(base / name)

    def _pick_user_agent(self) -> str:
        pool = self.app_cfg.get("user_agents") or [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/126.0.0.0 Chrome/126.0.0.0 Safari/537.36",
        ]
        return random.choice(pool).strip()

    def _create_driver(self, profile_dir: str | None = None, proxy: str | None = None):
        from seleniumwire.undetected_chromedriver import Chrome, ChromeOptions

        ua = self._pick_user_agent()
        opts = ChromeOptions()
        opts.add_argument("--lang=en-GB")
        opts.add_argument("--window-size=1280,2000")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--ignore-ssl-errors=yes")
        opts.set_capability("acceptInsecureCerts", True)  # let Chrome proceed
        opts.add_argument(f"--user-agent={ua}")
        if profile_dir:
            opts.add_argument(f"--user-data-dir={profile_dir}")

        sw_opts = {}
        if proxy:
            sw_opts = {
                "proxy": {"http": proxy, "https": proxy},
                "verify_ssl": False,  # upstream certs not verified by mitm
            }

        driver = Chrome(options=opts, seleniumwire_options=sw_opts)

        # Extra belt-and-braces via DevTools
        try:
            driver.execute_cdp_cmd("Security.setIgnoreCertificateErrors", {"ignore": True})
        except Exception:
            pass

        driver.set_page_load_timeout(self.app_cfg.get("page_load_timeout"))
        driver.set_script_timeout(self.app_cfg.get("script_timeout"))
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
        except Exception:
            pass

        self.current_user_agent = ua
        self.current_proxy = proxy
        return driver

    def _restart_driver(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        prof = self.profile
        if self.use_ephemeral_profile:
            if self.temp_profile_dir:
                shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
            self.temp_profile_dir = tempfile.mkdtemp(prefix="uc_prof_")
            prof = self.temp_profile_dir
        self.driver = self._create_driver(prof, self._pick_proxy())
        self._pages_left = self.rotate_after_pages

    def rotate_user_agent(self) -> bool:
        ua = self._pick_user_agent()
        try:
            self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
            self.current_user_agent = ua
            return True
        except Exception:
            return False

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
            proxies = {"http": self.current_proxy, "https": self.current_proxy} if self.current_proxy else None
            timeout_s = random.uniform(3, 5)
            r = requests.get(robots_url, headers=headers, proxies=proxies, timeout=timeout_s)
            rp.parse([] if r.status_code >= 400 else r.text.splitlines())
        except Exception:
            rp.parse([])
        ROBOTS_CACHE[netloc] = rp
        ROBOTS_TIME[netloc] = now
        return rp

    def _cookies_accepted(self, driver, names=("OptanonConsent", "OptanonAlertBoxClosed")) -> bool:
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
        try:
            WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')]"))
            ).click()
            return True
        except Exception:
            return False

    def _ensure_driver(self):
        if self.driver is None or self._pages_left <= 0:
            self._restart_driver()

    def fetch_html(self, url: str) -> str:
        rp = self._get_rp(url)
        ua = self.current_user_agent or "Mozilla/5.0"
        if not rp.can_fetch(ua, url):
            raise PermissionError(f"Blocked by robots.txt: {url}")
        last_exc = None
        for _ in range(self.max_attempts):
            self._ensure_driver()
            d = self.driver
            try:
                d.get(url)
                if not self._cookies_accepted(d):
                    self._accept_cookies(d, self.app_cfg["driver_load_timeout"])
                WebDriverWait(d, self.app_cfg["driver_load_timeout"]).until(
                    lambda drv: drv.execute_script("return document.readyState") in ("interactive", "complete")
                )
                self._pages_left -= 1
                return d.page_source
            except Exception as e:
                last_exc = e
                self._restart_driver()
                self.rotate_user_agent()
        raise last_exc or RuntimeError("Failed to fetch")

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        finally:
            if self.temp_profile_dir:
                shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
