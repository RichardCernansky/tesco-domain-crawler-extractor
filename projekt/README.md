# Manuál ovládania programu

Program poskytuje pipeline na spracovanie produktových stránok: sťahovanie HTML, extrakciu produktov, Spark enrichment, budovanie indexov (klasický aj PyLucene), dotazovanie, štatistiky a testovanie.

## Príprava prostredia

### Docker Build

Program vyžaduje PyLucene, preto je odporúčané použiť Docker kontajner.

#### 1. Build Docker image
```bash
docker build -t scraper-pylucene .
```

#### 2. Spustenie kontajnera
```bash
docker run -it \               
  -v /Users/richardcernansky/Desktop/VINF/projekt:/usr/src/app \
  scraper-pylucene:latest \
  /bin/bash
```

Po spustení kontajnera sa dostanete do shellu, kde môžete vykonávať všetky príkazy.

## Konfigurácie

Konfigurácie sa načítavajú zo súborov:
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

## Príkazy na sťahovanie a extrakciu

### fetch-pages

Stiahne HTML stránky podľa NDJSON konfigurácií.
```bash
python cli.py fetch-pages
```

**Vstupy:** definované v `site_config.json`  
**Výstupy:** uložené HTML súbory podľa `app_config.json`

### extract-products

Parsuje HTML a generuje NDJSON s produktmi.
```bash
python cli.py extract-products
```

**Výstup:** `data/products.ndjson`

Program vypíše:
```
[OK] products written to data/products.ndjson
```

## Spark pipeline

### spark-extract

Extrahuje produkty cez Apache Spark z HTML súborov.
```bash
python cli.py spark-extract
```

**Vstup:** HTML súbory z `fetch-pages`  
**Výstup:** NDJSON súbory v `data/spark/extracted/`

### spark-eue

Extrahuje unikátne entity (brands, ingredients) z produktov.
```bash
python cli.py spark-eue
```

**Vstup:** produktové dáta  
**Výstup:** zoznam unikátnych brands a ingredients

### spark-ewa

Extrahuje články z Wikipédie pre enrichment.
```bash
python cli.py spark-ewa
```

**Vstup:** Wikipedia dump  
**Výstup:** relevantné články pre brands a ingredients

### spark-build-lookups

Buduje brand/ingredient lookup tabuľky pre enrichment.
```bash
python cli.py spark-build-lookups
```

**Vstup:** extrahované entity a Wikipedia články  
**Výstup:** lookup tabuľky v `data/lookups/`

### spark-enrich

Obohacuje produkty o Wikipedia informácie.
```bash
python cli.py spark-enrich
```

**Vstup:** produktové dáta + lookup tabuľky  
**Výstup:** obohátené produkty v `data/wiki/out/products_enriched.ndjson/`

## Budovanie indexov

### build-index

Buduje klasický TF-IDF index (custom implementácia).
```bash
python cli.py build-index
```

**Vstup:** cesty a nastavenia z `app_config.json`  
**Výstup:** adresár indexu v `data/index/`

### build-pylucene-index

Vytvorí PyLucene index v adresári `pylucene/product_index`.
```bash
python cli.py build-pylucene-index
```

**Vstup:** obohátené produkty  
**Výstup:** PyLucene index v `pylucene/product_index/`

## Vyhľadávanie

### query

Dopytuje klasický TF-IDF index a meria čas vyhľadávania.
```bash
python cli.py query --mode {idf,idf_l2} --topk <N> <terms...>
```

**Parametre:**
- `--mode` - spôsob skórovania (`idf`, `idf_l2`)
- `--topk` - počet výsledkov (default: 10)
- `<terms>` - 1+ kľúčových slov

**Príklad:**
```bash
python cli.py query --mode idf_l2 --topk 10 chocolate milk
```

Program vypíše čas začiatku aj konca dopytu v milisekundách.

### search

Používa PyLucene index, podporuje fuzzy vyhľadávanie a meria reálny čas dotazu.
```bash
python cli.py search --topk 10 --field <pole> <terms...>
```

**Parametre:**
- `--topk` - počet výsledkov (default: 10)
- `--field` - prehľadáva iba vybrané pole (voliteľné)
- `--no-fuzzy` - vypne fuzzy matching (voliteľné)
- `<terms>` - kľúčové slová

**Príklady:**
```bash
# Základné vyhľadávanie
python cli.py search chocolate muffin

# Vyhľadávanie v konkrétnom poli
python cli.py search --field name chocolate

# Bez fuzzy matchingu
python cli.py search --no-fuzzy chocolate muffin

# S limitom výsledkov
python cli.py search --topk 20 milk semi skimmed
```

**Výstup:** čas spustenia + trvanie dotazu v ms + zoznam produktov so skóre.

## Ostatné príkazy

### stats

Vypíše štatistiku indexu a dát.
```bash
python cli.py stats
```

**Výstup:**
- Počet produktov
- Počet indexovaných dokumentov
- Veľkosť indexu
- Distribúcia kategórií
- Ďalšie metriky

### test

Spúšťa interné overenia pipeline.
```bash
python cli.py test
```

**Účel:** validácia funkčnosti jednotlivých komponentov

## Tokenizačná pipeline (PyLucene)

PyLucene používa nasledujúcu tokenizačnú pipeline:
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

**Popis krokov:**
- `StandardTokenizer` - rozdelí text na tokeny
- `LowerCaseFilter` - prevedie na malé písmená
- `StopFilter` - odstráni stop slová (the, a, an, in, ...)

## Typický workflow

Odporúčané poradie vykonávania príkazov:
```bash
# 1. Stiahnutie stránok
python cli.py fetch-pages

# 2. Extrakcia produktov
python cli.py extract-products

# 3. Spark pipeline (voliteľné, ale odporúčané pre enrichment)
python cli.py spark-extract
python cli.py spark-eue
python cli.py spark-ewa
python cli.py spark-build-lookups
python cli.py spark-enrich

# 4. Budovanie indexov
python cli.py build-index
python cli.py build-pylucene-index

# 5. Vyhľadávanie
python cli.py query --mode idf_l2 --topk 10 chocolate milk
python cli.py search --topk 10 chocolate milk

# 6. Štatistiky a testy
python cli.py stats
python cli.py test
```