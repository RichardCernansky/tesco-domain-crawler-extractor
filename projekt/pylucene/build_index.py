import lucene
import json
import glob
from pathlib import Path

DATA_FOLDER = "./data/wiki/out/products_enriched.ndjson"
INDEX_FOLDER ="./pylucene/product_index"

lucene.initVM()

part_files = glob.glob(f"{DATA_FOLDER}/part-*")

if not part_files:
    raise FileNotFoundError(f"No part files found in {DATA_FOLDER}")

data_file = part_files[0]  # Máme len 1 súbor
print(f"Loading data from: {data_file}")


from java.nio.file import Paths
from org.apache.lucene.analysis.standard import StandardAnalyzer
from org.apache.lucene.document import (
    Document, Field, TextField, StringField,
    IntPoint, StoredField, LongPoint
)
from org.apache.lucene.index import IndexWriter, IndexWriterConfig
from org.apache.lucene.store import FSDirectory

def build_pylucene_index():
    directory = FSDirectory.open(Paths.get(INDEX_FOLDER))
    analyzer = StandardAnalyzer()
    config = IndexWriterConfig(analyzer)
    writer = IndexWriter(directory, config)

    count = 0
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue

            product = json.loads(line)
            doc = Document()

            # BASIC PRODUCT FIELDS
            # Product ID (for exact lookup)
            doc.add(LongPoint("product_id", product.get("product_id", 0)))
            doc.add(StoredField("product_id", product.get("product_id", 0)))

            # Textové polia (fulltextové vyhľadávanie)
            doc.add(TextField("name", product.get("name", ""), Field.Store.YES))
            doc.add(TextField("description", product.get("description", ""), Field.Store.YES))
            doc.add(TextField("highlights", product.get("highlights", ""), Field.Store.YES))

            # String polia (presné vyhľadávanie, filtre)
            doc.add(StringField("brand", product.get("brand", ""), Field.Store.YES))
            doc.add(StringField("category", product.get("category", ""), Field.Store.YES))
            doc.add(StringField("price_currency", product.get("price_currency", ""), Field.Store.YES))

            # Ingredients (zreťazené do stringu pre full-text search)
            ingredients = " ".join(product.get("ingredients", []))
            doc.add(TextField("ingredients", ingredients, Field.Store.YES))

            # Price (numeric)
            if product.get("price_num"):
                # Use DoublePoint for decimal prices
                from org.apache.lucene.document import DoublePoint

                doc.add(DoublePoint("price_num", product["price_num"]))
                doc.add(StoredField("price_num", product["price_num"]))

            # BRAND WIKI ENRICHMENT
            brand_wiki = product.get("brand_wiki", {})

            if brand_wiki and brand_wiki.get("wiki_id"):
                # Brand info jako StringFields (exact match)
                doc.add(StringField("brand_wiki_title",
                                    brand_wiki.get("wiki_title", ""), Field.Store.YES))

                doc.add(StringField("brand_wiki_url",
                                    brand_wiki.get("wiki_url", ""), Field.Store.YES))

                # TextField pre searchable fields
                doc.add(TextField("brand_description",
                                  brand_wiki.get("description", ""), Field.Store.YES))

                doc.add(StringField("brand_introduced",
                                    brand_wiki.get("introduced", ""), Field.Store.YES))

                doc.add(StringField("brand_origin",
                                    brand_wiki.get("origin", ""), Field.Store.YES))

                doc.add(StringField("brand_website",
                                    brand_wiki.get("website", ""), Field.Store.YES))

                doc.add(StringField("brand_infobox_type",
                                    brand_wiki.get("infobox_type", ""), Field.Store.YES))

                # Categories array to string
                brand_categories = " ".join(brand_wiki.get("categories", []))
                doc.add(TextField("brand_categories", brand_categories, Field.Store.YES))

            # INGREDIENTS WIKI ENRICHMENT
            ingredients_wiki = product.get("ingredients_wiki", [])

            # Combine all ingredient descriptions for full-text search
            ingredient_descriptions = []
            ingredient_names = []
            ingredient_types = []

            for ing in ingredients_wiki:
                if ing.get("description"):
                    ingredient_descriptions.append(ing["description"])
                if ing.get("name"):
                    ingredient_names.append(ing["name"])
                if ing.get("type"):
                    ingredient_types.append(ing["type"])

            # Index combined ingredient data
            doc.add(TextField("ingredient_descriptions",
                              " ".join(ingredient_descriptions), Field.Store.YES))

            doc.add(TextField("ingredient_wiki_names",
                              " ".join(ingredient_names), Field.Store.YES))

            doc.add(TextField("ingredient_types",
                              " ".join(ingredient_types), Field.Store.YES))

            # Store structured ingredient data as JSON (for display)
            if ingredients_wiki:
                doc.add(StoredField("ingredients_wiki_json",
                                    json.dumps(ingredients_wiki)))

            # WIKI ENRICHMENT COUNTERS
            wiki_enrich = product.get("wiki_enrichment", {})

            # Boolean: is there brand wiki?
            has_brand = 1 if wiki_enrich.get("has_brand_wiki") else 0
            doc.add(IntPoint("has_brand_wiki", has_brand))
            doc.add(StoredField("has_brand_wiki", has_brand))

            # Počet matchnutých ingrediencií
            ingredients_count = wiki_enrich.get("ingredients_wiki_count", 0)
            doc.add(IntPoint("ingredients_wiki_count", ingredients_count))
            doc.add(StoredField("ingredients_wiki_count", ingredients_count))

            # Flag counters (pre-filtering)
            allergen_cnt = wiki_enrich.get("allergen_count", 0)
            doc.add(IntPoint("allergen_count", allergen_cnt))
            doc.add(StoredField("allergen_count", allergen_cnt))

            sweetener_cnt = wiki_enrich.get("sweetener_count", 0)
            doc.add(IntPoint("sweetener_count", sweetener_cnt))
            doc.add(StoredField("sweetener_count", sweetener_cnt))

            carcinogen_cnt = wiki_enrich.get("carcinogen_count", 0)
            doc.add(IntPoint("carcinogen_count", carcinogen_cnt))
            doc.add(StoredField("carcinogen_count", carcinogen_cnt))

            # Total wiki matches
            total_matches = wiki_enrich.get("total_wiki_matches", 0)
            doc.add(IntPoint("total_wiki_matches", total_matches))
            doc.add(StoredField("total_wiki_matches", total_matches))

            writer.addDocument(doc)
            count += 1

            if count % 1000 == 0:
                print(f"Indexed {count} documents...")

    writer.commit()
    writer.close()

    print(f"\nSuccessfully indexed {count} products!")
    print(f"Index location: {INDEX_FOLDER}")