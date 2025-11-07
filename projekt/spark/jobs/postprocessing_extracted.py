import re
from html import unescape
from pathlib import Path
from typing import List, Optional

from pyspark.sql import SparkSession, functions as F, types as T

# ---------------- config-driven paths ----------------
def run_postprocess(APP_CFG: dict):
    IN_NDJSON  = str(Path(APP_CFG["spark_storage_path"]) / "products_spark.ndjson")
    OUT_NDJSON = str(Path(APP_CFG["spark_storage_path"]) / "products_postprocessed.ndjson")

    spark = (
        SparkSession.builder
        .appName("products-postprocess")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # ---------- schema matching your first-stage output ----------
    schema = T.StructType([
        T.StructField("product_id",      T.LongType()),
        T.StructField("source_file",     T.StringType()),
        T.StructField("name",            T.StringType()),
        T.StructField("brand",           T.StringType()),
        T.StructField("category",        T.StringType()),
        T.StructField("price_currency",  T.StringType()),
        T.StructField("price",           T.StringType()),
        T.StructField("ingredients",     T.StringType()),   # raw HTML block from stage 1
        T.StructField("description",     T.StringType()),   # raw HTML block from stage 1
        T.StructField("nutrition_table", T.MapType(T.StringType(), T.StringType())),
        T.StructField("unitpair",        T.StringType()),   # e.g. "7.96/kg"
        T.StructField("highlights",      T.StringType()),   # raw HTML block from stage 1
    ])

    # ---------- read NDJSON ----------
    df0 = (
        spark.read.text(IN_NDJSON)
             .select(F.from_json(F.col("value"), schema).alias("j"))
             .select("j.*")
    )

    # ---------- UDFs (your exact logic) ----------
    @F.udf(returnType=T.StringType())
    def strip_html_plain(s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
        s = re.sub(r'(?is)<!--.*?-->', ' ', s)
        s = re.sub(r'(?i)<br\s*/?>', ' ', s)
        s = re.sub(r'(?i)</(p|div|li|tr|th|td|h[1-6])\s*>', ' ', s)
        s = re.sub(r'(?s)<[^>]*>', ' ', s)
        s = unescape(s).replace('\xa0', ' ')
        s = s.replace('\r', ' ').replace('\n', ' ')
        s = re.sub(r'^\s*ingredients?\s*[:\-\u2013\u2014]\s*', '', s, flags=re.I)
        s = re.sub(r'\s+', ' ', s).strip(' .;,[]')
        return s if s else None

    def _get_ingredients(inner: str) -> List[str]:
        def split_ingredients(s: str, sep: str):
            parts, buf, depth = [], [], 0
            for ch in s:
                if ch == '(':
                    depth += 1
                elif ch == ')' and depth > 0:
                    depth -= 1
                if ch == sep and depth == 0:
                    part = ''.join(buf).strip()
                    if part:
                        parts.append(part)
                    buf = []
                else:
                    buf.append(ch)
            tail = ''.join(buf).strip()
            if tail:
                parts.append(tail)
            return parts

        if not inner:
            return []

        first_level_parts = split_ingredients(inner, ",")
        second_level_parts = []
        for p in first_level_parts:
            ingredient_split = split_ingredients(p, " ")
            for s in ingredient_split:
                if any(ch.isdigit() for ch in s):
                    continue
                t = (s or "").strip(" ()[]")
                if t:
                    second_level_parts.append(t)

        all_ingredients = []
        for p in second_level_parts:
            if ',' in p:
                all_ingredients.extend(split_ingredients(p, ","))
            else:
                all_ingredients.append(p)
        return all_ingredients

    get_ingredients_udf = F.udf(_get_ingredients, T.ArrayType(T.StringType()))

    # ---------- transform ----------
    df = (
        df0
        # clean text fields
        .withColumn("description", strip_html_plain(F.col("description")))
        .withColumn("highlights",  strip_html_plain(F.col("highlights")))
        .withColumn("ingredients_text", strip_html_plain(F.col("ingredients")))
        # tokenize ingredients -> array<string>
        .withColumn("ingredients", get_ingredients_udf(F.col("ingredients_text")))
        # derive unit_bundle from unitpair
        .withColumn("unit_price", F.regexp_extract(F.col("unitpair"), r"(?is)^([0-9]+(?:\.[0-9]+)?)\s*/", 1))
        .withColumn("unit_unit",  F.regexp_extract(F.col("unitpair"), r"(?is)/\s*([A-Za-z]+)\s*$", 1))
        .withColumn("unit_bundle", F.struct(
            F.col("unit_price").alias("price"),
            F.col("unit_unit").alias("unit")
        ))
        # optional numeric price
        .withColumn("price_num", F.col("price").cast("double"))
    )

    # tidy helper cols
    df_out = df.drop("ingredients_text", "unit_price", "unit_unit")

    # ---------- write NDJSON ----------
    (
        df_out
        .select(F.to_json(F.struct(*df_out.columns)).alias("json"))
        .write.mode("overwrite").text(OUT_NDJSON)
    )

    print("OK. Wrote:", OUT_NDJSON)
    spark.stop()