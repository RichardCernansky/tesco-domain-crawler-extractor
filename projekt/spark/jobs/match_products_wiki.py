# PySpark job: join produktov s Wikipedia tabuľkami (brand/ingredients/category)
# Vstupy: NDJSON z predošlých jobov
# Výstup: data/out/products_enriched.ndjson/part-*
#
# Spustenie:
#   spark-submit spark/jobs/match_products_wiki.py

from pathlib import Path
from pyspark.sql import SparkSession, functions as F

APP_ROOT = Path(__file__).resolve().parents[2]

# ---------- NDJSON vstupy ----------
P_NDJSON   = str(APP_ROOT / "data" / "out" / "products_from_spark_regex.ndjson")
W_MAIN_ND  = str(APP_ROOT / "data" / "out" / "wiki" / "main.ndjson")
W_CAT_ND   = str(APP_ROOT / "data" / "out" / "wiki" / "categories.ndjson")
OUT_ND     = str(APP_ROOT / "data" / "out" / "products_enriched.ndjson")
Path(OUT_ND).parent.mkdir(parents=True, exist_ok=True)

def norm(col):
    c = F.lower(F.trim(col))
    c = F.regexp_replace(c, r"[\u2000-\u206F\u2E00-\u2E7F'\".,!?;:()\\[\\]{}<>|`~@#$%^&*_+=/\\-]", " ")
    c = F.trim(F.regexp_replace(c, r"\s+", " "))
    return F.nullif(c, F.lit(""))

spark = (
    SparkSession.builder
    .appName("match-products-wiki")
    .master("local[*]")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# ---------- načítanie NDJSON ----------
# Spark pri read.json načíta každý riadok ako objekt (NDJSON)
prod = spark.read.json(P_NDJSON)
wiki = spark.read.json(W_MAIN_ND).withColumnRenamed("lead", "lead_main")
cats = spark.read.json(W_CAT_ND).withColumnRenamed("lead", "lead_cat")

# ---------- normalizácie pre join ----------
prod = (
    prod
    .withColumn("brand_norm",    norm(F.col("brand")))
    .withColumn("category_norm", norm(F.col("category")))
    .withColumn("category_title_norm", norm(F.concat(F.lit("Category:"), F.col("category"))))
)

# ---------- INGREDIENTS: explode a normalizácia ----------
prod_ing = (
    prod.withColumn("ingredient_raw", F.explode_outer("ingredients"))
        .withColumn("ingredient_norm", norm(F.col("ingredient_raw")))
        .where(F.col("ingredient_norm").isNotNull() & (F.length("ingredient_norm") > 0))
)

# ---------- JOIN: brand ↔ wiki(main) ----------
brand_hit = (
    prod.select("product_id", "brand", "brand_norm")
        .join(
            wiki.select("page_id", "title", "title_norm", "lead_main"),
            on=prod["brand_norm"] == wiki["title_norm"],
            how="left"
        )
        .groupBy("product_id")
        .agg(F.first(F.struct("page_id", "title", "lead_main"), ignorenulls=True).alias("brand_wiki"))
)

# ---------- JOIN: ingredients[] ↔ wiki(main) ----------
ing_hit = (
    prod_ing.join(
        wiki.select("page_id", "title", "title_norm", "lead_main"),
        on=prod_ing["ingredient_norm"] == wiki["title_norm"],
        how="left"
    )
    .groupBy("product_id")
    .agg(
        # set unikátnych wiki stránok k ingredienciám (null sa vyhodí)
        F.collect_set(
            F.when(F.col("page_id").isNotNull(), F.struct("page_id", "title", "lead_main"))
        ).alias("ingredient_wiki_set")
    )
)

# ---------- JOIN: category ↔ wiki(Category:) ----------
cat_hit = (
    prod.select("product_id", "category", "category_title_norm")
        .join(
            cats.select("page_id", "title", "title_norm", "lead_cat"),
            on=prod["category_title_norm"] == cats["title_norm"],
            how="left"
        )
        .groupBy("product_id")
        .agg(F.first(F.struct("page_id", "title", "lead_cat"), ignorenulls=True).alias("category_wiki"))
)

# ---------- Zloženie späť + metriky/proveniencia ----------
enriched = (
    prod.join(brand_hit, "product_id", "left")
        .join(ing_hit, "product_id", "left")
        .join(cat_hit, "product_id", "left")
        .withColumn(
            "ingredient_hits_count",
            F.size(F.expr("filter(coalesce(ingredient_wiki_set, array()), x -> x is not null)"))
        )
        .withColumn(
            "wiki_pages_used_count",
            F.col("ingredient_hits_count") +
            F.when(F.col("brand_wiki").isNotNull(), F.lit(1)).otherwise(F.lit(0)) +
            F.when(F.col("category_wiki").isNotNull(), F.lit(1)).otherwise(F.lit(0))
        )
        .withColumn(
            "wiki_provenance",
            F.struct(
                F.col("brand_wiki"),
                F.col("category_wiki"),
                F.col("ingredient_wiki_set").alias("ingredients_wiki")
            )
        )
)

# ---------- write NDJSON ----------
(
    enriched.select(F.to_json(F.struct(*enriched.columns)).alias("json"))
            .repartition(8)
            .write.mode("overwrite").text(OUT_ND)
)

print("OK enriched:", enriched.count(), "|", OUT_ND)
spark.stop()
