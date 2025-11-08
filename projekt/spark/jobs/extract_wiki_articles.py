# spark/jobs/extract_wiki_articles.py
"""
Parse Wikipedia XML dump and extract relevant articles WITH FULL TEXT.
Creates searchable Wikipedia index with complete article content.
"""
from pathlib import Path
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.functions import broadcast


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
    df_terms = (
        df_brands.select(F.col("brand_normalized").alias("term"))
        .union(df_categories.select(F.col("category_normalized").alias("term")))
        .union(df_categories.select(F.col("category_main").alias("term")))
        .union(df_ingredients.select(F.col("ingredient_normalized").alias("term")))
        .where(F.col("term").isNotNull())
        .where(F.length(F.col("term")) > 0)
        .select(F.trim(F.regexp_replace(F.lower("term"), "[^a-z0-9]+", " ")).alias("term"))
        .distinct()
    )

    unique_terms = df_terms.select("term").distinct()
    n_terms = unique_terms.count()
    print(f"Searching for {n_terms} unique terms in Wikipedia")


    # ============================================
    # STEP 2: Read Wikipedia
    # ============================================
    df_wiki = (
        spark.read
        .format("xml")
        .option("rowTag", "page")
        .load(WIKI_PATH)
    )

    # ============================================
    # STEP 3: Filter using INNER JOIN (not UDF!)
    # ============================================
    df_wiki_processed = (
        df_wiki
        .select(
            F.col("title").alias("wiki_title"),
            F.col("revision.text._VALUE").alias("wiki_text"),
            F.col("ns").alias("namespace"),
            F.col("id").alias("wiki_id")
        )
        .where(F.col("namespace").cast("int") == 0)
        .where(F.col("wiki_text").isNotNull())
        .where(~F.col("wiki_text").rlike("(?is)^\\s*#redirect\\b"))
        .withColumn(
            "title_normalized",
            F.trim(F.regexp_replace(F.lower("wiki_title"), "[^a-z0-9]+", " "))
        )
    )


    print("Filtering articles by exact title match...")

    #exact match filter using join
    df_filtered = (
        df_wiki_processed.join(broadcast(df_terms), df_wiki_processed.title_normalized == df_terms.term, "inner")
        .select(df_wiki_processed["*"])
        .distinct()
    )

    filtered_count = df_filtered.count()
    print(f"Filtered to {filtered_count:,} relevant articles (exact matches)")

    # Extract metadata but KEEP wiki_text
    df_articles = (
        df_filtered

        # ============================================
        # MATCHING FIELDS
        # ============================================

        .withColumn("title_normalized",
                    F.lower(F.col("wiki_title"))
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