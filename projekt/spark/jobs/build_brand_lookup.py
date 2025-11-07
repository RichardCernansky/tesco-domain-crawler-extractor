# spark/jobs/build_brand_lookup.py
"""
Match brands to Wikipedia articles and create lookup table.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T, Window


def build_brand_lookup(APP_CFG: dict):
    """
    Match unique brands to Wikipedia articles.

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
    print(f"Wikipedia articles: {df_wiki.count()}")

    # TIER 1: Exact title match
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
            F.col("w.wiki_description"),
            F.col("w.has_infobox"),
            F.col("w.infobox_type"),
            F.col("w.categories"),
            F.lit("exact").alias("match_method"),
            F.when(F.col("w.wiki_id").isNotNull(), 0.95).otherwise(0.0).alias("confidence")
        )
    )

    # TIER 2: Match with common suffixes
    brand_variations = (
        df_brands
        .select(
            "brand",
            "brand_normalized",
            # Generate variations
            F.array(
                F.col("brand_normalized"),
                F.concat(F.col("brand_normalized"), F.lit(" brand")),
                F.concat(F.col("brand_normalized"), F.lit(" company")),
                F.concat(F.col("brand_normalized"), F.lit(" corporation"))
            ).alias("variations")
        )
        .select("brand", "brand_normalized", F.explode("variations").alias("variation"))
    )

    df_variation = (
        brand_variations.alias("b")
        .join(
            df_wiki.alias("w"),
            F.col("b.variation") == F.col("w.title_normalized"),
            "left"
        )
        .where(F.col("w.wiki_id").isNotNull())
        .select(
            F.col("b.brand"),
            F.col("b.brand_normalized"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_description"),
            F.col("w.has_infobox"),
            F.col("w.infobox_type"),
            F.col("w.categories"),
            F.lit("variation").alias("match_method"),
            F.lit(0.85).alias("confidence")
        )
    )

    # TIER 3: Token-based matching (all tokens must be present)
    df_tokens = (
        df_brands.alias("b")
        .withColumn("brand_tokens", F.split("brand_normalized", " "))
        .join(
            df_wiki.alias("w"),
            "wiki_id"  # Cross join placeholder
        )
        # Check if all brand tokens are in wiki title tokens
        .withColumn("tokens_match",
                    F.size(F.array_intersect(F.col("brand_tokens"), F.col("w.title_tokens")))
                    == F.size("brand_tokens")
                    )
        .where(F.col("tokens_match"))
        .where(F.col("w.has_infobox"))  # Only with infobox for quality
        .select(
            F.col("b.brand"),
            F.col("b.brand_normalized"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_description"),
            F.col("w.has_infobox"),
            F.col("w.infobox_type"),
            F.col("w.categories"),
            F.lit("tokens").alias("match_method"),
            # Prefer shorter titles (more likely to be exact entity)
            (0.75 / (1 + F.length("w.wiki_title") * 0.01)).alias("confidence")
        )
    )

    # Combine all tiers
    df_all_matches = df_exact.union(df_variation).union(df_tokens)

    # For each brand, pick best match
    window = Window.partitionBy("brand").orderBy(F.desc("confidence"))

    df_lookup = (
        df_all_matches
        .withColumn("rank", F.row_number().over(window))
        .where(F.col("rank") == 1)
        .drop("rank")
        # Add match quality flags
        .withColumn("needs_review",
                    (F.col("confidence") < 0.7) | (~F.col("has_infobox")))
    )

    # Write lookup table
    df_lookup.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Brand Lookup Results ===")
    print(f"Total brands: {df_brands.count()}")
    print(f"Matched: {df_lookup.filter('wiki_id IS NOT NULL').count()}")
    print(f"Unmatched: {df_lookup.filter('wiki_id IS NULL').count()}")
    print(f"High confidence (>0.8): {df_lookup.filter('confidence > 0.8').count()}")
    print(f"Needs review: {df_lookup.filter('needs_review').count()}")
    print(f"Output: {OUT_PATH}")

    # Show sample matches
    print("\nSample matches:")
    df_lookup.filter("wiki_id IS NOT NULL").show(10, truncate=False)

    spark.stop()