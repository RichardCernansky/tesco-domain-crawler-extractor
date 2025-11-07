# spark/jobs/extract_wiki_articles.py
"""
Parse Wikipedia XML dump and extract relevant articles WITH FULL TEXT.
Creates searchable Wikipedia index with complete article content.
"""
from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T


def extract_wiki_articles(APP_CFG: dict):
    """
    Parse Wikipedia XML dump and extract articles with full text.

    Output: wiki_articles.parquet (with full wiki_text for later extraction)
    """

    WIKI_PATH = APP_CFG["wiki_file"]
    OUT_PATH = str(Path(APP_CFG["spark_storage_path"]) / "wiki_articles.parquet")
    BRANDS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_brands.parquet")
    CATEGORIES_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_categories.parquet")
    INGREDIENTS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_ingredients.parquet")

    spark = (
        SparkSession.builder
        .appName("extract-wiki-articles")
        .master("local[*]")
        .config("spark.jars.packages", "com.databricks:spark-xml_2.12:0.18.0")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print(f"Reading Wikipedia XML from: {WIKI_PATH}")

    # Load entities first
    df_brands = spark.read.parquet(BRANDS_PATH)
    df_categories = spark.read.parquet(CATEGORIES_PATH)
    df_ingredients = spark.read.parquet(INGREDIENTS_PATH).filter("NOT is_generic")

    # Create search patterns
    search_terms = (
        df_brands.select(F.col("brand_normalized").alias("term"))
        .union(df_categories.select(F.col("category_normalized").alias("term")))
        .union(df_categories.select(F.lower(F.col("category_main")).alias("term")))
        .union(df_ingredients.select(F.col("ingredient_normalized").alias("term")))
        .distinct()
        .collect()
    )

    search_set = set(row.term for row in search_terms if row.term)
    print(f"Searching for {len(search_set)} unique terms in Wikipedia")

    # Broadcast for efficient filtering
    search_set_bc = spark.sparkContext.broadcast(search_set)

    # Read Wikipedia
    df_wiki = (
        spark.read
        .format("xml")
        .option("rowTag", "page")
        .load(WIKI_PATH)
    )

    # Filter function
    @F.udf(returnType=T.BooleanType())
    def is_relevant_article(title: str) -> bool:
        if not title:
            return False
        normalized = title.lower().replace("-", " ").replace("_", " ")
        normalized = " ".join(normalized.split())
        for term in search_set_bc.value:
            if term in normalized or normalized in term:
                return True
        return False

    df_filtered = (
        df_wiki
        .select(
            F.col("title").alias("wiki_title"),
            F.col("revision.text._VALUE").alias("wiki_text"),
            F.col("ns").alias("namespace"),
            F.col("id").alias("wiki_id")
        )
        .where(F.col("namespace") == 0)
        .where(~F.lower(F.col("wiki_text")).like("#redirect%")) # exclude redirects
        .where(F.col("wiki_text").isNotNull())
        .where(is_relevant_article("wiki_title"))
    )

    print(f"Filtered to {df_filtered.count()} relevant articles")

    # Extract metadata but KEEP wiki_text
    df_articles = (
        df_filtered

        # ============================================
        # MATCHING FIELDS
        # ============================================

        .withColumn("title_normalized",
                    F.lower(F.regexp_replace("wiki_title", "[^a-z0-9]", " "))
                    )
        .withColumn("title_normalized",
                    F.regexp_replace("title_normalized", r"\s+", " ")
                    )
        .withColumn("title_normalized", F.trim("title_normalized"))

        .withColumn("title_tokens",
                    F.split(F.col("title_normalized"), " ")
                    )

        # ============================================
        # BASIC QUALITY SIGNALS (quick extraction)
        # ============================================

        .withColumn("has_infobox",
                    F.col("wiki_text").rlike("(?i)\\{\\{infobox")
                    )

        .withColumn("infobox_type",
                    F.regexp_extract(F.col("wiki_text"), r"(?i)\{\{infobox\s+([a-z\s]+)", 1)
                    )

        .withColumn("categories",
                    F.expr("regexp_extract_all(wiki_text, '\\\\[\\\\[Category:([^\\\\]]+)\\\\]\\\\]', 1)")
                    )

        # ============================================
        # METADATA
        # ============================================

        .withColumn("text_length", F.length("wiki_text"))

        .withColumn("wiki_url",
                    F.concat(
                        F.lit("https://en.wikipedia.org/wiki/"),
                        F.regexp_replace("wiki_title", " ", "_")
                    )
                    )

        # ============================================
        # SELECT ALL COLUMNS (including full wiki_text)
        # ============================================
        .select(
            # IDs
            "wiki_id",
            "wiki_title",

            # For matching
            "title_normalized",
            "title_tokens",

            # Basic metadata (pre-extracted for convenience)
            "has_infobox",
            "infobox_type",
            "categories",
            "wiki_url",
            "text_length",

            # FULL TEXT (for detailed extraction in lookup jobs)
            "wiki_text"  # ← KEEPING THE FULL TEXT
        )
    )

    # Write to parquet (parquet will compress this efficiently)
    df_articles.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Wikipedia Articles Extracted ===")
    print(f"Total articles: {df_articles.count()}")
    print(f"With infobox: {df_articles.filter('has_infobox').count()}")
    print(f"Output: {OUT_PATH}")

    # Storage info

    size_bytes = sum(f.stat().st_size for f in Path(OUT_PATH).rglob('*') if f.is_file())
    size_mb = size_bytes / (1024 * 1024)
    print(f"Storage size: {size_mb:.1f} MB")

    # Show sample
    print("\nSample articles:")
    df_articles.select(
        "wiki_title",
        "title_normalized",
        "has_infobox",
        "infobox_type",
        F.substring("wiki_text", 1, 100).alias("text_preview")
    ).show(10, truncate=False)

    spark.stop()