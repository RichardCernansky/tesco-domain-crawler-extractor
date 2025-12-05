# Manuál ovládania programu

Program poskytuje pipeline na spracovanie produktových stránok: sťahovanie HTML, extrakciu produktov, Spark enrichment, budovanie indexov (klasický aj PyLucene), dotazovanie, štatistiky a testovanie.

## Konfigurácie sa načítavajú zo súborov:
```bash
data/configs/site_config.json
data/configs/app_config.json
```

## Základná syntax
```
python cli.py <príkaz> [voľby] [argumenty]
```

### Dostupné príkazy:
```bash
fetch-pages
extract-products
build-index
query
search (PyLucene)
build-pylucene-index
stats
test
spark-extract, spark-eue, spark-ewa, spark-build-lookups, spark-enrich
```

## Príkaz: fetch-pages

Stiahne HTML stránky podľa NDJSON konfigurácií.
```
python cli.py fetch-pages
```

**Vstupy:** definované v site_config.json  
**Výstupy:** uložené HTML súbory podľa app_config.json

## Príkaz: extract-products

Parsuje HTML a generuje NDJSON s produktmi.
```
python cli.py extract-products
```

**Výstup:**
```
data/products.ndjson
```

Program vypíše:
```
[OK] products written to data/products.ndjson
```

## Príkaz: build-index

Buduje klasický TF-IDF index.
```
python cli.py build-index
```

**Vstup:** cesty a nastavenia z app_config.json  
**Výstup:** adresár indexu

## Príkaz: query

Dopytuje klasický index a meria čas vyhľadávania.
```
python cli.py query --mode {idf,idf_l2} --topk <N> terms...
```

**Parametre:**
- `--mode` :: spôsob skórovania (idf, idf_l2)
- `--topk` :: počet výsledkov
- `terms` :: 1+ kľúčových slov

Program vypíše čas začiatku aj koniec dopytu v milisekundách.

## Príkaz: search (PyLucene)

Používa PyLucene index, podporuje fuzzy vyhľadávanie a meria reálny čas dotazu.
```
python cli.py search --topk 10 --field name muffin chocolate
```

**Voliteľné:**
- `--field` :: prehľadáva iba vybrané pole
- `--no-fuzzy` :: vypne fuzzy matching

**Výstup:** čas spustenia + trvanie dotazu v ms.

## Príkaz: build-pylucene-index

Vytvorí PyLucene index v adresári pylucene/product_index.
```
python cli.py build-pylucene-index
```

## Spark pipeline

### Extrakcia produktov cez Spark
```
python cli.py spark-extract
```

### Extrakcia unikátnych entít
```
python cli.py spark-eue
```

### Extrakcia článkov z Wikipédie
```
python cli.py spark-ewa
```

### Budovanie brand/ingredient lookup tabuliek
```
python cli.py spark-build-lookups
```

### Enrichment produktov
```
python cli.py spark-enrich
```

## Príkaz: stats

Vypíše štatistiku indexu a dát.
```
python cli.py stats
```

## Príkaz: test

Spúšťa interné overenia pipeline.
```
python cli.py test
```

## Odporúčaný spôsob: Spúšťanie v Dockeri

Najspoľahlivejšie je spúšťať indexer aj PyLucene search v Dockeri, pretože PyLucene používa natívne knižnice.

### Build PyLucene index
```bash
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/build_index.py:/app/pylucene/build_index.py \
  scraper-pylucene \
  python /app/pylucene/build_index.py
```

### Spustenie PyLucene searchera
```bash
docker run -it --rm \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/searcher.py:/app/pylucene/searcher.py \
  scraper-pylucene \
  python /app/pylucene/searcher.py
```

## Tokenizačná pipeline (PyLucene)
```
Text Input
    ↓
[StandardTokenizer]
    ↓
[LowerCaseFilter]
    ↓
[StopFilter]
    ↓
Indexed Tokens
```

## Typický workflow
```bash
1. fetch-pages
2. extract-products
3. spark-extract (a voliteľný enrichment)
4. build-index
5. build-pylucene-index
6. query alebo search
7. stats / test podľa potreby
```