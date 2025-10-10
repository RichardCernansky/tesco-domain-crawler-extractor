# crawler/crawler.py
import json, time, re, hashlib
from pathlib import Path
from collections import deque
from urllib.parse import urlsplit, urlunsplit, urljoin
import random

from .fetcher import Fetcher  # your Selenium-based fetcher

def _normalize(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    s = urlsplit(url)
    s = s._replace(scheme=s.scheme.lower(), netloc=s.netloc.lower(), fragment="")
    path = s.path or "/"
    return urlunsplit((s.scheme, s.netloc, path, s.query, ""))

def _content_hash(html: str) -> str:
    return hashlib.sha256((html or "").encode("utf-8", "ignore")).hexdigest()

def _url_fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8", "ignore")).hexdigest()

class Crawler:
    """
    Disk-log crawler:
      - VISITED URLs in app_cfg["visited_path"] (one URL per line)
      - STACK pushes in app_cfg["stack_path"]   (append-only JSONL of {"event":"push",...})
      - Per-page metadata in app_cfg["metadata_path"] (NDJSON)
      - HTML saved under app_cfg["storage_path"] (flat files)
    """
    def __init__(self, site_cfg: dict, app_cfg: dict):
        self.site_cfg = site_cfg
        self.app_cfg  = app_cfg

        # file paths come from app_cfg (they exist)
        self.storage_root  = Path(self.app_cfg["storage_path"])
        self.stack_path    = Path(self.app_cfg["stack_path"])
        self.visited_path  = Path(self.app_cfg["visited_path"])
        self.metadata_path = Path(self.app_cfg["metadata_path"])

        # profile + fetcher (profile path only passed if your Fetcher uses it)
        self.fetcher = Fetcher(self)
        self.timeout = int(self.app_cfg.get("time_out", 2))
        self.sleep_min = float(self.app_cfg.get("sleep_min"))
        self.sleep_max = float(self.app_cfg.get("sleep_max"))

    # ---------- public API ----------
    def crawl(self):
        start_url = self.site_cfg["start_url"]
        max_pages = self.site_cfg["max_pages"]
        visited = self._load_visited_set()

        # rebuild frontier from existing pushes (never wipe the stack)
        frontier = self._replay_pushes(visited)

        # seed only if nothing is pending
        if not frontier:
            su = _normalize(start_url)
            self._append_push(su)
            frontier = self._replay_pushes(visited)


        processed = 0
        seen_this_run = set(u for (u, _, _) in frontier)

        while frontier and (max_pages is None or processed < max_pages):
            num_already_visited = len(frontier)
            if (processed % 20) == 0:
                print(f"Number of STORED: {processed}")
                print(f"Number of in-stack: {num_already_visited}")

            url, depth, ref = frontier.popleft()
            if url in visited:
                continue

            start_t = time.time()
            status, error = "ok", None
            html, content_path = "", None

            self._jitter()
            try:
                html = self.fetcher.fetch_html(url)

                if not html:
                    status = "empty"
            except Exception as e:
                status = "error"
                error = str(e)

            if html:
                ts = int(time.time())
                uhash = _url_fingerprint(url)[:12]
                chash = _content_hash(html)[:12]
                fname = f"{ts}_{uhash}_{chash}.html"
                fpath = (self.storage_root / fname)
                fpath.write_text(html, encoding="utf-8", errors="ignore")
                content_path = fpath.as_posix()

            # mark visited (disk + memory)
            with self.visited_path.open("a", encoding="utf-8") as f:
                f.write(url + "\n")
            visited.add(url)

            # metadata
            meta = {
                "url": url,
                "depth": depth,
                "referrer": ref,
                "status": status,
                "http_code": None,  # Selenium-only
                "fetched_at": start_t,
                "elapsed_sec": time.time() - start_t,
                # title
                "outlink_count": 0,
                "content_hash": _content_hash(html) if html else None,
                "content_path": content_path,
                "error": error,
            }

            # expand links only on success
            if status == "ok" and html:
                links = self._extract_links(html)
                meta["outlink_count"] = len(links)
                for href in links:
                    cand = _normalize(href, base=url)
                    if not self._in_scope(cand):
                        continue
                    if cand in visited or cand in seen_this_run: # if seen -> skip
                        continue
                    frontier.append((cand, depth + 1, url))
                    seen_this_run.add(cand)
                    self._append_push(cand)

            with self.metadata_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

            processed += 1
            print(url)

        print(f"Number of processed: {processed}")
        return {"processed": processed, "visited_count": len(visited)}

    def _jitter(self):
        time.sleep(random.uniform(self.sleep_min, self.sleep_max))

    def _load_visited_set(self) -> set[str]:
        with self.visited_path.open("r", encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}

    def _append_push(self, url: str):
        # store ONLY the URL (one per line), no JSON
        with self.stack_path.open("a", encoding="utf-8") as f:
            f.write(url.strip() + "\n")

    def _replay_pushes(self, visited_set: set[str]) -> deque:
        q = deque()
        queued = set()
        with self.stack_path.open("r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if not u:
                    continue
                norm = _normalize(u)
                if norm in visited_set or norm in queued:
                    continue
                # depth/referrer info is not stored; default to 0 / None
                q.append((norm, 0, None))
                queued.add(norm)
        return q

    def _extract_links(self, html: str) -> list[str]:
        """Extract all hrefs using the regex from config."""
        pat = self.site_cfg["regexes"]["href_regex"]  # e.g. href=["']([^"']+)["']
        return re.findall(pat, html , flags=re.I | re.S)

    def _in_scope(self, url: str) -> bool:
        """Keep only site-specific links using the filter regex from config."""
        filt = self.site_cfg["regexes"]["href_filter_tesco"]  # e.g. ^(?:https?:)?//(?:...)?tesco\.com(?:/|$)|^/
        return re.match(filt, url, flags=re.I) is not None