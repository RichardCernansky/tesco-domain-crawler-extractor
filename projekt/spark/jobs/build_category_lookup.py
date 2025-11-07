# spark/jobs/build_category_lookup.py
"""
Match categories to Wikipedia articles and create lookup table.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T, Window


def build_category_lookup(APP_CFG: dict):
    """
    Match unique categories to Wikipedia articles.

    Output: category_to_wiki.parquet
    """

    CATEGORIES_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_categories.parquet")
    WIKI_PATH = str(Path(APP_CFG["spark_storage_path"]) / "wiki_articles.parquet")
    OUT_PATH = str(Path(APP_CFG["spark_storage_path"]) / "category_to_wiki.parquet")

    spark = (
        SparkSession.builder
        .appName("build-category-lookup")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    df_categories = spark.read.parquet(CATEGORIES_PATH)
    df_wiki = spark.read.parquet(WIKI_PATH)

    print(f"Categories to match: {df_categories.count()}")

    # Match 1: Exact match on main category
    df_main_match = (
        df_categories.alias("c")
        .join(
            df_wiki.alias("w"),
            F.lower(F.col("c.category_main")) == F.col("w.title_normalized"),
            "left"
        )
        .select(
            F.col("c.category"),
            F.col("c.category_normalized"),
            F.col("c.category_main"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_description"),
            F.col("w.categories"),
            F.lit("main_category").alias("match_method"),
            F.when(F.col("w.wiki_id").isNotNull(), 0.80).otherwise(0.0).alias("confidence")
        )
    )

    # Match 2: Exact match on full normalized category
    df_exact_match = (
        df_categories.alias("c")
        .join(
            df_wiki.alias("w"),
            F.col("c.category_normalized") == F.col("w.title_normalized"),
            "left"
        )
        .select(
            F.col("c.category"),
            F.col("c.category_normalized"),
            F.col("c.category_main"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_description"),
            F.col("w.categories"),
            F.lit("exact").alias("match_method"),
            F.when(F.col("w.wiki_id").isNotNull(), 0.75).otherwise(0.0).alias("confidence")
        )
    )

    # Combine matches and pick best
    df_all_matches = df_main_match.union(df_exact_match)

    window = Window.partitionBy("category").orderBy(F.desc("confidence"))

    df_lookup = (
        df_all_matches
        .withColumn("rank", F.row_number().over(window))
        .where(F.col("rank") == 1)
        .drop("rank")
    )

    df_lookup.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Category Lookup Results ===")
    print(f"Total categories: {df_categories.count()}")
    print(f"Matched: {df_lookup.filter('wiki_id IS NOT NULL').count()}")
    print(f"Unmatched: {df_lookup.filter('wiki_id IS NULL').count()}")
    print(f"Output: {OUT_PATH}")

    spark.stop()