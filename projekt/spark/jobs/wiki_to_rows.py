# PySpark job: načítať enwiki multistream XML dump a vyrobiť NDJSON:
# - data/out/wiki/main.ndjson/part-*   (ns=0: hlavné články)
# - data/out/wiki/categories.ndjson/part-* (ns=14: Category)
#
# Spustenie:
#   spark-submit --packages com.databricks:spark-xml_2.12:0.16.0 spark/jobs/wiki_to_rows.py

from pathlib import Path
from pyspark.sql import SparkSession, functions as F

# --------------------------- cesty -------------------------------------------
APP_ROOT = Path(__file__).resolve().parents[2]
WIKI_BZ2 = str(APP_ROOT / "data" / "wiki" / "enwiki-20251020-pages-articles-multistream.xml.bz2")
OUT_MAIN = str(APP_ROOT / "data" / "out" / "wiki" / "main.ndjson")
OUT_CAT  = str(APP_ROOT / "data" / "out" / "wiki" / "categories.ndjson")
Path(OUT_MAIN).parent.mkdir(parents=True, exist_ok=True)

# --------------------------- normalizácia ------------------------------------
def norm(col):
    # zjednotenie: lower + odstránenie interpunkcie + normalizácia whitespacu
    c = F.lower(F.trim(col))
    c = F.regexp_replace(c, r"[\u2000-\u206F\u2E00-\u2E7F'\".,!?;:()\\[\\]{}<>|`~@#$%^&*_+=/\\-]", " ")
    c = F.trim(F.regexp_replace(c, r"\s+", " "))
    return F.nullif(c, F.lit(""))

# --------------------------- spark session -----------------------------------
spark = (
    SparkSession.builder
    .appName("wiki-to-rows")
    .master("local[*]")
    .config("spark.sql.caseSensitive", "false")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# --------------------------- načítanie XML -----------------------------------
# spark-xml rozbalí bz2 priamo; každá <page> = 1 riadok
df = (
    spark.read.format("com.databricks.spark.xml")
    .option("rowTag", "page")
    .load(WIKI_BZ2)
)

# výber polí; text je v revision.text._VALUE
df = df.select(
    F.col("id").cast("long").alias("page_id"),
    F.col("ns").cast("int").alias("ns"),
    F.col("title").alias("title"),
    F.col("revision.text._VALUE").alias("text")
)

# "lead" = prvý odsek pred "== Heading ==" (rýchly sumar pre tooltipy)
lead = F.trim(F.regexp_extract(F.coalesce(F.col("text"), F.lit("")), r"(?is)^(.*?)(?:\n==|\Z)", 1))
lead_plain = F.trim(F.regexp_replace(lead, r"(?is)<[^>]+>", " "))
lead_plain = F.trim(F.regexp_replace(lead_plain, r"\s+", " "))

# normalizovaný titul pre joiny
title_norm = norm(F.col("title"))

# split podľa namespace
main = (
    df.where(F.col("ns") == 0)
      .select("page_id", "title", title_norm.alias("title_norm"), lead_plain.alias("lead"))
)
cats = (
    df.where(F.col("ns") == 14)
      .select("page_id", "title", title_norm.alias("title_norm"), lead_plain.alias("lead"))
)

# --------------------------- write NDJSON ------------------------------------
(
    main.select(F.to_json(F.struct(*main.columns)).alias("json"))
        .repartition(8)
        .write.mode("overwrite").text(OUT_MAIN)
)
(
    cats.select(F.to_json(F.struct(*cats.columns)).alias("json"))
        .repartition(2)
        .write.mode("overwrite").text(OUT_CAT)
)

print("OK wiki main:", main.count(), "| wiki categories:", cats.count())
spark.stop()
