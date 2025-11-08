# spark/jobs/extract_unique_entities.py
"""
Extract unique brands, categories, and ingredients from products.
Creates distinct sets for Wikipedia matching.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T

def extract_unique_entities(APP_CFG: dict):
    """
    Extract unique brands, categories, and ingredients from postprocessed products.

    Output:
        - unique_brands.parquet
        - unique_categories.parquet
        - unique_ingredients.parquet
    """

    PRODUCTS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "products_postprocessed.ndjson")
    BRANDS_OUT = str(Path(APP_CFG["spark_storage_path"]) / "unique_brands.parquet")
    CATEGORIES_OUT = str(Path(APP_CFG["spark_storage_path"]) / "unique_categories.parquet")
    INGREDIENTS_OUT = str(Path(APP_CFG["spark_storage_path"]) / "unique_ingredients.parquet")

    spark = (
        SparkSession.builder
        .appName("extract-unique-entities")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Schema for products
    schema = T.StructType([
        T.StructField("product_id", T.LongType()),
        T.StructField("source_file", T.StringType()),
        T.StructField("name", T.StringType()),
        T.StructField("brand", T.StringType()),
        T.StructField("category", T.StringType()),
        T.StructField("price_currency", T.StringType()),
        T.StructField("price", T.StringType()),
        T.StructField("ingredients", T.ArrayType(T.StringType())),
        T.StructField("description", T.StringType()),
        T.StructField("nutrition_table", T.MapType(T.StringType(), T.StringType())),
        T.StructField("highlights", T.StringType()),
        T.StructField("unit_bundle", T.StructType([
            T.StructField("price", T.StringType()),
            T.StructField("unit", T.StringType())
        ])),
        T.StructField("price_num", T.DoubleType())
    ])

    # Read products
    df_products = (
        spark.read.text(PRODUCTS_PATH)
        .select(F.from_json(F.col("value"), schema).alias("j"))
        .select("j.*")
    )

    print(f"Total products: {df_products.count()}")

    # Extract unique brands
    df_brands = (
        df_products
        .select("brand")
        .where(F.col("brand").isNotNull())
        .where(F.length(F.trim("brand")) > 0)
        .distinct()
        .withColumn("brand_normalized", F.lower(F.col("brand")))
        .withColumn("brand_normalized", F.regexp_replace("brand_normalized", r"\s+", " "))
        .withColumn("brand_normalized", F.trim("brand_normalized"))
    )

    df_brands.write.mode("overwrite").parquet(BRANDS_OUT)
    print(f"Unique brands: {df_brands.count()} -> {BRANDS_OUT}")

    # Extract unique categories
    df_categories = (
        df_products
        .select("category")
        .where(F.col("category").isNotNull())
        .where(F.length(F.trim("category")) > 0)
        .distinct()
        .withColumn("category_normalized", F.lower(F.col("category")))
        .withColumn("category_normalized", F.regexp_replace("category_normalized", r"\s+", " "))
        .withColumn("category_normalized", F.trim("category_normalized"))
        # Extract main category keywords (before &, -, or "and")
        .withColumn("category_main",
                    F.regexp_extract("category_normalized", r"^([^&\-]+?)(?:\s+(?:&|and|-)|\s*$)", 1))
        .withColumn("category_main", F.trim("category_main"))
    )

    df_categories.write.mode("overwrite").parquet(CATEGORIES_OUT)
    print(f"Unique categories: {df_categories.count()} -> {CATEGORIES_OUT}")

    # Extract unique ingredients
    df_ingredients = (
        df_products
        .select(F.explode("ingredients").alias("ingredient"))
        .where(F.col("ingredient").isNotNull())
        .where(F.length(F.trim("ingredient")) > 0)
        .distinct()
        .withColumn("ingredient_normalized", F.lower(F.col("ingredient")))
        .withColumn("ingredient_normalized", F.regexp_replace("ingredient_normalized", r"\s+", " "))
        .withColumn("ingredient_normalized", F.trim("ingredient_normalized"))

        # Skip too generic ingredients
        .withColumn("is_generic",
                    F.when(F.col("ingredient_normalized").isin(["water", "salt"]), True)
                    .when(F.length("ingredient_normalized") < 3, True)
                    .otherwise(False)
                    )
    )

    df_ingredients.write.mode("overwrite").parquet(INGREDIENTS_OUT)
    print(f"Unique ingredients: {df_ingredients.count()} -> {INGREDIENTS_OUT}")

    # Summary statistics
    print("\n=== Summary ===")
    print(f"Brands:      {df_brands.count()}")
    print(f"Categories:  {df_categories.count()}")
    print(f"Ingredients: {df_ingredients.count()}")
    print(f"  - Generic (water, salt): {df_ingredients.filter('is_generic').count()}")
    print(f"  - Valid:   {df_ingredients.filter('NOT is_generic').count()}")

    spark.stop()