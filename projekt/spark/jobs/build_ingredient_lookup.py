# spark/jobs/build_ingredient_lookup.py
"""
Match ingredients to Wikipedia articles and create lookup table.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T, Window


def build_ingredient_lookup(APP_CFG: dict):
    """
    Match unique ingredients to Wikipedia articles.

    Output: ingredient_to_wiki.parquet
    """

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

    df_ingredients = spark.read.parquet(INGREDIENTS_PATH)
    df_wiki = spark.read.parquet(WIKI_PATH)

    # Filter out generic ingredients
    df_ingredients = df_ingredients.filter("NOT is_generic")

    print(f"Ingredients to match: {df_ingredients.count()}")

    # Exact match only for ingredients (they're usually standardized)
    df_lookup = (
        df_ingredients.alias("i")
        .join(
            df_wiki.alias("w"),
            F.col("i.ingredient_normalized") == F.col("w.title_normalized"),
            "left"
        )
        .select(
            F.col("i.ingredient"),
            F.col("i.ingredient_normalized"),
            F.col("w.wiki_id"),
            F.col("w.wiki_title"),
            F.col("w.wiki_description"),
            F.col("w.categories"),
            # Classify ingredient type from categories
            F.when(F.array_contains(F.col("w.categories"), "Chemical compounds"), "chemical")
            .when(F.array_contains(F.col("w.categories"), "Food additives"), "additive")
            .when(F.array_contains(F.col("w.categories"), "Cooking oils"), "oil")
            .when(F.array_contains(F.col("w.categories"), "Spices"), "spice")
            .when(F.array_contains(F.col("w.categories"), "Fish"), "fish")
            .when(F.array_contains(F.col("w.categories"), "Sugars"), "sugar")
            .otherwise("other")
            .alias("ingredient_type"),
            F.when(F.col("w.wiki_id").isNotNull(), 0.90).otherwise(0.0).alias("confidence")
        )
    )

    df_lookup.write.mode("overwrite").parquet(OUT_PATH)

    print(f"\n=== Ingredient Lookup Results ===")
    print(f"Total ingredients: {df_ingredients.count()}")
    print(f"Matched: {df_lookup.filter('wiki_id IS NOT NULL').count()}")
    print(f"Unmatched: {df_lookup.filter('wiki_id IS NULL').count()}")
    print(f"Output: {OUT_PATH}")

    # Show ingredient types distribution
    print("\nIngredient types:")
    df_lookup.groupBy("ingredient_type").count().orderBy(F.desc("count")).show()

    spark.stop()