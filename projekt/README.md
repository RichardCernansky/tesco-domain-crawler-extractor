# Docker run

## Indexer ##
```bash
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/build_index.py:/app/pylucene/build_index.py \
  scraper-pylucene \
  python /app/pylucene/build_index.py
```

## TO ##
```bash
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


```bash
docker run -it --rm \
  -v $(pwd)/pylucene/product_index:/app/pylucene/product_index \
  -v $(pwd)/pylucene/searcher.py:/app/pylucene/searcher.py \
  scraper-pylucene \
 python /app/pylucene/searcher.py
```