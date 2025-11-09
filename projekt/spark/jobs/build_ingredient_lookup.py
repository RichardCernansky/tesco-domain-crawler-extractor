# spark/jobs/build_ingredient_lookup.py
from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T, Window


def build_ingredient_lookup(APP_CFG: dict):
    INGREDIENTS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "unique_ingredients.parquet")
    WIKI_PATH = str(Path(APP_CFG["spark_storage_path"]) / "wiki_articles.parquet")
    OUT_PATH = str(Path(APP_CFG["spark_storage_path"]) / "ingredient_to_wiki.parquet")

    spark = (
        SparkSession.builder
        .appName("build-ingredient-lookup")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Load data
    df_ingredients = spark.read.parquet(INGREDIENTS_PATH)
    df_wiki = spark.read.parquet(WIKI_PATH)

    print(f"to match: {df_ingredients.count()}")
    print(f"Wikipedia articles available: {df_wiki.count()}")

    # ============================================
    # TIER 1: Exact title match
    # ============================================
    df_exact = (
        df_ingredients.alias("i")
        .join(
            df_wiki.alias("w"),
            F.col("i.ingredient_normalized") == F.col("w.title_normalized"),
            "inner"
        )
        .select(
            F.col("i.ingredient"),
            F.col("i.ingredient_normalized"),
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

        # Check if text contains "sweetener" (case-insensitive)
        .withColumn("is_sweetener",
                    F.col("wiki_text").rlike(r"(?i)\bsweetener\b")
        )
        .withColumn("is_allergen",
                    F.col("wiki_text").rlike(r"(?i)\b(allergen|allergic|allergy|hypersensitivity)\b")
        )
        .withColumn("is_carcinogenic",
                    F.col("wiki_text").rlike(r"(?i)\b(carcinogen|carcinogenic|cancer)\b")
            )


        # Drop the full wiki_text (we've extracted what we need)
        .drop("wiki_text", "clean_text")

        # Select final columns
        .select(
            "ingredient",
            "ingredient_normalized",

            # Wikipedia match info
            "wiki_id",
            "wiki_title",
            "wiki_url",
            "wiki_description",

            "introduced",
            "origin",
            "website",

            "is_sweetener",
            "is_allergen",
            "is_carcinogenic",

            # Metadata
            "has_infobox",
            "infobox_type",
            "categories",
        )
    )

    # Write lookup table
    df_lookup.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Ingredient Lookup Results ===")
    print(f"Total ingredients: {df_ingredients.count()}")
    print(f"Matched: {df_lookup.filter('wiki_id IS NOT NULL').count()}")
    print(f"With description: {df_lookup.where((F.col('wiki_description').isNotNull()) & (F.col('wiki_description') != '')).count()}")
    print(f"With introduced year: {df_lookup.where((F.col('introduced').isNotNull()) & (F.col('introduced') != '')).count()}")
    print(f"With origin: {df_lookup.where((F.col('origin').isNotNull()) & (F.length('origin') > 0)).count()}")
    print(f"With website: {df_lookup.where((F.col('website').isNotNull()) & (F.length('website') > 0)).count()}")
    print(f"Number of sweeteners: {df_lookup.where((F.col('is_sweetener') == True)).count()}")
    print(f"Number of allergens: {df_lookup.where((F.col('is_allergen') == True)).count()}")
    print(f"Number of carcinogens: {df_lookup.where((F.col('is_carcinogenic') == True)).count()}")
    print(f"Output: {OUT_PATH}")

    # Show sample matches with extracted data
    print("\nSample matches with extracted data:")
    df_lookup.filter("wiki_id IS NOT NULL").select(
        "ingredient",
        "wiki_title",
        "introduced",
        "origin",
        # "website",
        "is_sweetener",
    ).show(10, truncate=False)


    spark.stop()