import requests, concurrent.futures, time, json

PROXIES = [
    "118.174.115.252:8080","62.60.236.119:3128","95.47.238.254:3128",
    "223.206.115.167:8080","27.79.238.203:16000","181.78.3.133:999",
    "116.98.183.148:1010","164.163.42.17:10000","27.79.236.43:16000",
    "49.48.46.181:8080","45.175.155.42:999","27.79.170.65:16000",
    "42.119.154.222:16000","27.79.148.128:16000","27.79.251.238:16000",
    "42.114.161.88:16000","183.81.95.214:16000","14.172.146.226:20399",
    "171.229.223.57:8081",
]

def norm(p): return p if "://" in p else f"http://{p}"

def check(p, timeout=6):
    proxy = norm(p)
    proxies = {"http": proxy, "https": proxy}
    t0 = time.time()
    try:
        r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=timeout)
        r.raise_for_status()
        ip = r.json().get("origin", "?")
        return {"proxy": proxy, "ok": True, "latency_s": round(time.time()-t0,2), "ip": ip}
    except Exception as e:
        return {"proxy": proxy, "ok": False, "err": str(e)}

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    results = list(ex.map(check, PROXIES))

good = [x for x in results if x["ok"]]
bad  = [x for x in results if not x["ok"]]
print("WORKING:", json.dumps(good, indent=2))
print("FAILED:", len(bad))
