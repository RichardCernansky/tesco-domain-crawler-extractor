# spark/jobs/enrich_products.py
"""
Enrich products with Wikipedia data using lookup tables.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T


def enrich_products_with_wiki(APP_CFG: dict):
    """
    Join products with Wikipedia lookup tables to add enrichment data.

    Output: products_enriched.ndjson
    """

    PRODUCTS_PATH = str(Path(APP_CFG["spark_storage_path"]) / "products_postprocessed.ndjson")
    BRAND_LOOKUP = str(Path(APP_CFG["spark_storage_path"]) / "brand_to_wiki.parquet")
    CATEGORY_LOOKUP = str(Path(APP_CFG["spark_storage_path"]) / "category_to_wiki.parquet")
    INGREDIENT_LOOKUP = str(Path(APP_CFG["spark_storage_path"]) / "ingredient_to_wiki.parquet")
    OUT_PATH = str(Path(APP_CFG["spark_storage_path"]) / "products_enriched.ndjson")

    spark = (
        SparkSession.builder
        .appName("enrich-products-wiki")
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

    # Load data
    df_products = (
        spark.read.text(PRODUCTS_PATH)
        .select(F.from_json(F.col("value"), schema).alias("j"))
        .select("j.*")
    )

    df_brand_lookup = spark.read.parquet(BRAND_LOOKUP)
    df_category_lookup = spark.read.parquet(CATEGORY_LOOKUP)
    df_ingredient_lookup = spark.read.parquet(INGREDIENT_LOOKUP)

    print(f"Products to enrich: {df_products.count()}")

    # Join with brand lookup
    df_with_brand = (
        df_products.alias("p")
        .join(
            df_brand_lookup.alias("b"),
            F.col("p.brand") == F.col("b.brand"),
            "left"
        )
        .select(
            "p.*",
            F.struct(
                F.col("b.wiki_id").alias("wiki_id"),
                F.col("b.wiki_title").alias("wiki_title"),
                F.col("b.wiki_description").alias("description"),
                F.col("b.infobox_type").alias("infobox_type"),
                F.col("b.categories").alias("categories"),
                F.col("b.confidence").alias("confidence"),
                F.col("b.match_method").alias("match_method")
            ).alias("brand_wiki")
        )
    )

    # Join with category lookup
    df_with_category = (
        df_with_brand.alias("p")
        .join(
            df_category_lookup.alias("c"),
            F.col("p.category") == F.col("c.category"),
            "left"
        )
        .select(
            "p.*",
            F.struct(
                F.col("c.wiki_id").alias("wiki_id"),
                F.col("c.wiki_title").alias("wiki_title"),
                F.col("c.wiki_description").alias("description"),
                F.col("c.confidence").alias("confidence")
            ).alias("category_wiki")
        )
    )

    # Join with ingredient lookup (explode and aggregate back)
    df_ingredients_exploded = (
        df_with_category
        .select("product_id", F.explode("ingredients").alias("ingredient"))
    )

    df_ingredients_matched = (
        df_ingredients_exploded.alias("i")
        .join(
            df_ingredient_lookup.alias("il"),
            F.col("i.ingredient") == F.col("il.ingredient"),
            "left"
        )
        .where(F.col("il.wiki_id").isNotNull())  # Only keep matched ingredients
        .select(
            "i.product_id",
            F.struct(
                F.col("i.ingredient").alias("name"),
                F.col("il.wiki_id").alias("wiki_id"),
                F.col("il.wiki_title").alias("wiki_title"),
                F.col("il.wiki_description").alias("description"),
                F.col("il.ingredient_type").alias("type"),
                F.col("il.confidence").alias("confidence")
            ).alias("ingredient_wiki")
        )
        .groupBy("product_id")
        .agg(F.collect_list("ingredient_wiki").alias("ingredients_wiki"))
    )

    # Final join
    df_enriched = (
        df_with_category.alias("p")
        .join(
            df_ingredients_matched.alias("iw"),
            "product_id",
            "left"
        )
        .select(
            "p.*",
            F.coalesce("iw.ingredients_wiki", F.array()).alias("ingredients_wiki")
        )
        # Add enrichment statistics
        .withColumn("wiki_enrichment", F.struct(
            (F.col("brand_wiki.wiki_id").isNotNull()).alias("has_brand_wiki"),
            (F.col("category_wiki.wiki_id").isNotNull()).alias("has_category_wiki"),
            F.size("ingredients_wiki").alias("ingredients_wiki_count"),
            (
                    F.when(F.col("brand_wiki.wiki_id").isNotNull(), 1).otherwise(0) +
                    F.when(F.col("category_wiki.wiki_id").isNotNull(), 1).otherwise(0) +
                    F.size("ingredients_wiki")
            ).alias("total_wiki_matches")
        ))
    )

    # Write enriched products
    (
        df_enriched
        .select(F.to_json(F.struct(*df_enriched.columns)).alias("json"))
        .write.mode("overwrite").text(OUT_PATH)
    )

    print(f"\n=== Enrichment Results ===")
    print(f"Total products: {df_enriched.count()}")
    print(f"With brand wiki: {df_enriched.filter('brand_wiki.wiki_id IS NOT NULL').count()}")
    print(f"With category wiki: {df_enriched.filter('category_wiki.wiki_id IS NOT NULL').count()}")

    # Average ingredients matched
    avg_ingredients = df_enriched.agg(F.avg(F.size("ingredients_wiki"))).collect()[0][0]
    print(f"Avg ingredients with wiki: {avg_ingredients:.2f}")

    print(f"Output: {OUT_PATH}")

    spark.stop()