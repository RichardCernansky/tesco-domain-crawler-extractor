# Manuál ovládania programu

Program spúšťa jednotlivé kroky pipeline: sťahovanie stránok, extrakciu produktov, stavbu indexu, dotazovanie, štatistiky a testy.

Konfigurácie sa načítajú zo súborov: `data/configs/site_config.json` a `data/configs/app_config.json`.

## Základná syntax
```bash
python cli.py <príkaz> [voľby] [argumenty]
```

Dostupné príkazy: `fetch-pages`, `extract-products`, `build-index`, `query`, `stats`, `test`

---

## Príkaz: fetch-pages

Sťahuje (crawl) stránky produktov podľa NDJSON konfigurácií (každý riadok jedna položka).

### Použitie
```bash
python cli.py fetch-pages
```

### Vstupy
Konfigurácia webov a zdrojov v `site_config.json` (a/alebo NDJSON zo súborov definovaných v konfigurácii).

### Výstupy
Uložené HTML súbory podľa nastavení v `app_config.json` (cieľové priečinky určuje konfigurácia).

---

## Príkaz: extract-products

Parsuje uložené HTML a emituje produkty do NDJSON.

### Použitie
```bash
python cli.py extract-products
```

### Vstupy
HTML súbory stiahnuté cez `fetch-pages`.

### Výstupy
`data/products.ndjson`

Program zároveň vypíše: `[OK] products written to data/products.ndjson.`

---

## Príkaz: build-index

Postaví vyhľadávací index z pripravených dát.

### Použitie
```bash
python cli.py build-index
```

### Vstupy
Cesty a nastavenia indexu z `app_config.json` (napr. zdrojový NDJSON, cieľový priečinok indexu).

### Výstupy
Vytvorený/aktualizovaný index (umiestnenie podľa `app_config.json`).

---

## Príkaz: query

Spustí dotaz nad postaveným indexom.

### Použitie
```bash
python cli.py query --mode {idf,idf_l2} --topk <N> terms...
```

### Parametre
- `--mode` :: povinné — režim skórovania (`idf` alebo `idf_l2`)
- `--topk` :: povinné — počet vrátených výsledkov (napr. 10)
- `terms` :: povinné, 1+ — kľúčové slová; viacslovné frázy daj do úvodzoviek

---

## Príkaz: stats

Vypíše štatistiky (stav indexu, počty dokumentov, prípadne ďalšie metriky podľa implementácie `stats()`).

### Použitie
```bash
python cli.py stats
```

### Výstupy
Textový výpis štatistík do konzoly.

---

## Príkaz: test

Spustí interné testy/overenia pipeline (podľa implementácie `test()`; typicky validácia extrakcie, konzistencie dát ap.).

### Použitie
```bash
python cli.py test
```

### Výstupy
Textový report testov do konzoly (pass/fail, prípadne zhrnutie).

---

## Poznámky

Cesty k dátam a umiestnenia výstupov riadi `app_config.json`; správanie crawlera a extraktora riadi `site_config.json`.

Poradie typického behu: `fetch-pages` → `extract-products` → `build-index` → `query` (voliteľne `stats`, `test` kedykoľvek).

---

# Docker PyLucene Index runs

## Indexer
```bash
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/build_index.py:/app/pylucene/build_index.py \
  scraper-pylucene \
  python /app/pylucene/build_index.py
```

## Tokenization Pipeline
```
Text Input
    ↓
[StandardTokenizer]     ← Rozdelí na tokeny
    ↓
[LowerCaseFilter]       ← Lowercase
    ↓
[StopFilter]            ← Odstráni "the", "and", "is"...
    ↓
Indexed Tokens
```

## Searcher
```bash
docker run -it --rm \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/searcher.py:/app/pylucene/searcher.py \
  scraper-pylucene \
  python /app/pylucene/searcher.py
```