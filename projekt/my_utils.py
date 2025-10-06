import re
from html import unescape

def flags(flag_list):
    f = 0
    if not flag_list:
        return f
    for x in flag_list:
        u = x.upper()
        if u == "I": f |= re.IGNORECASE
        if u == "S": f |= re.DOTALL
        if u == "M": f |= re.MULTILINE
    return f

def get_ingredients(inner: str):
    def split_ingredients(s: str, sep: str):
        parts, buf, depth = [], [], 0
        for ch in s:
            if ch == '(':
                depth += 1
            elif ch == ')' and depth > 0:
                depth -= 1
            if ch == sep and depth == 0:
                part = ''.join(buf).strip()
                if part: parts.append(part)
                buf = []
            else:
                buf.append(ch)
        tail = ''.join(buf).strip()
        if tail: parts.append(tail)
        return parts

    first_level_parts = split_ingredients(inner, ",")
    second_level_parts = []
    for p in first_level_parts:
        ingredient_split = split_ingredients(p, " ")
        for s in ingredient_split:
            if '(' in s and ')' in s:
                has_number = any(ch.isdigit() for ch in s)
                if has_number:
                    continue  # skip this s
                second_level_parts.append(s.strip('()'))
            else:
                second_level_parts.append(s)

    all_ingredients = []
    for p in second_level_parts:
        if ',' in p:
            all_ingredients.extend(split_ingredients(p, ","))
        else:
            all_ingredients.append(p)
    return all_ingredients

def strip_html_plain(s: str) -> str:
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?is)<!--.*?-->', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>', ' ', s)
    s = re.sub(r'(?i)</(p|div|li|tr|th|td|h[1-6])\s*>', ' ', s)
    s = re.sub(r'(?s)<[^>]*>', ' ', s)
    s = unescape(s).replace('\xa0', ' ')
    s = s.replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r'^\s*ingredients?\s*[:\-\u2013\u2014]\s*', '', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' .;,[]')

def create_driver(profile_dir: str | None = None, headless: bool = True, driver_path: str | None = None):
    import undetected_chromedriver as uc
    opts = uc.ChromeOptions()
    opts.add_argument("--lang=en-GB")
    opts.add_argument("--window-size=1280,2000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-first-run");
    opts.add_argument("--no-default-browser-check")
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
    # driver.execute_cdp_cmd("Network.enable", {})
    # driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": [
    #     "*.jpg","*.jpeg","*.png","*.gif","*.webp","*.svg",
    #     "*.woff","*.woff2","*.ttf","*.mp4","*.avi","*.m4v","*.mp3"
    # ]})
    return driver
