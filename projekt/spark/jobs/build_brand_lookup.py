# spark/jobs/build_brand_lookup.py
"""
Match brands to Wikipedia articles and extract detailed brand info.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T, Window


def build_brand_lookup(APP_CFG: dict):
    """
    Match unique brands to Wikipedia articles and extract brand details.

    Output: brand_to_wiki.parquet
    """

    BRANDS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_brands.parquet")
    WIKI_PATH = str(Path(APP_CFG["spark_storage_path"]) / "wiki_articles.parquet")
    OUT_PATH = str(Path(APP_CFG["spark_storage_path"]) / "brand_to_wiki.parquet")

    spark = (
        SparkSession.builder
        .appName("build-brand-lookup")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Load data
    df_brands = spark.read.parquet(BRANDS_PATH)
    df_wiki = spark.read.parquet(WIKI_PATH)

    print(f"Brands to match: {df_brands.count()}")
    print(f"Wikipedia articles available: {df_wiki.count()}")

    # ============================================
    # TIER 1: Exact title match
    # ============================================
    df_exact = (
        df_brands.alias("b")
        .join(
            df_wiki.alias("w"),
            F.col("b.brand_normalized") == F.col("w.title_normalized"),
            "left"
        )
        .select(
            F.col("b.brand"),
            F.col("b.brand_normalized"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_url"),
            F.col("w.wiki_text"),
            F.col("w.has_infobox"),
            F.col("w.infobox_type"),
            F.col("w.categories"),
        )
    )

    df_all_matches = df_exact




    # ============================================
    # EXTRACT DETAILED INFO FROM wiki_text
    # ============================================
    df_lookup = (
        df_all_matches

        # Extract first paragraph as description
        .withColumn("clean_text",
                    F.regexp_replace(F.col("wiki_text"), r"\{\{[^}]+\}\}", " ")
                    )
        .withColumn("clean_text",
                    F.regexp_replace(F.col("clean_text"), r"\[\[([^\]]+\|)?([^\]]+)\]\]", "$2")
                    )
        .withColumn("first_para",
                    F.regexp_extract(F.col("clean_text"), r"(?s)\A\s*(.+?)(?:\n\s*\n|$)", 1)
                    )
        .withColumn("wiki_description",
                           F.regexp_replace(F.trim(F.col("first_para")), r"\s+", " ")
                    )


        # Extract from infobox (if exists)
        .withColumn("introduced",
                    F.regexp_extract(F.col("wiki_text"),        r"(?i)(?:introduced|founded|established).*?(\d{4})", 1)
                    )

        .withColumn("origin",
                    F.regexp_extract(F.col("wiki_text"),  r"(?is)(?:origin|headquarters)\b.*?\[([^\]]+)\]", 1)
                    )

        .withColumn("website",
                    F.regexp_extract(F.col("wiki_text"),  r"(?is)website\b.*?\b(www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s\]|}<]*)?)", 1)
                    )


        # Drop the full wiki_text (we've extracted what we need)
        .drop("wiki_text", "clean_text")

        # Select final columns
        .select(
            # Brand info
            "brand",
            "brand_normalized",

            # Wikipedia match info
            "wiki_id",
            "wiki_title",
            "wiki_url",
            "wiki_description",

            # Extracted brand details
            "introduced",
            "origin",
            "website",

            # Metadata
            "has_infobox",
            "infobox_type",
            "categories",
        )
    )

    # Write lookup table
    df_lookup.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Brand Lookup Results ===")
    print(f"Total brands: {df_brands.count()}")
    print(f"Matched: {df_lookup.filter('wiki_id IS NOT NULL').count()}")
    print(f"Unmatched: {df_lookup.filter('wiki_id IS NULL').count()}")
    print(f"With description: {df_lookup.where((F.col('wiki_description').isNotNull()) & (F.col('wiki_description') != '')).count()}")
    print(f"With introduced year: {df_lookup.where((F.col('introduced').isNotNull()) & (F.col('introduced') != '')).count()}")
    print(f"With origin: {df_lookup.where((F.col('origin').isNotNull()) & (F.length('origin') > 0)).count()}")
    print(f"With website: {df_lookup.where((F.col('website').isNotNull()) & (F.length('website') > 0)).count()}")
    print(f"Output: {OUT_PATH}")

    # Show sample matches with extracted data
    print("\nSample matches with extracted data:")
    df_lookup.filter("wiki_id IS NOT NULL").select(
        "brand",
        "wiki_title",
        "introduced",
        "origin",
        "website",
    ).show(10, truncate=False)

    # Save 10 samples to JSON file
    # SAMPLES_PATH = str(Path(APP_CFG["spark_storage_path"]) / "brand_lookup_samples.json")
    # df_lookup.filter("wiki_id IS NOT NULL"
    # ).select(
    #     "brand",
    #     "wiki_title",
    #     "introduced",
    #     "origin",
    #     "wiki_description",
    #     "wiki_url",
    #
    # ).limit(10).coalesce(1).write.mode("overwrite").json(SAMPLES_PATH)
    #
    # print(f"\nSaved 10 samples to: {SAMPLES_PATH}")

    spark.stop()