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
    df_ingredient_lookup = spark.read.parquet(INGREDIENT_LOOKUP)

    print(f"Products to enrich: {df_products.count()}")

    # ============================================
    # JOIN WITH BRAND LOOKUP
    # ============================================
    df_with_brand = (
        df_products.alias("p")
        .join(
            df_brand_lookup.alias("b"),
            F.col("p.brand") == F.col("b.brand"),
            "left"
        )
        .select(
            "p.*",
            # Create brand_wiki struct with all brand Wikipedia data
            F.struct(
                F.col("b.wiki_id").alias("wiki_id"),
                F.col("b.wiki_title").alias("wiki_title"),
                F.col("b.wiki_url").alias("wiki_url"),
                F.col("b.wiki_description").alias("description"),
                F.col("b.introduced").alias("introduced"),
                F.col("b.origin").alias("origin"),
                F.col("b.website").alias("website"),
                F.col("b.infobox_type").alias("infobox_type"),
                F.col("b.categories").alias("categories")
            ).alias("brand_wiki")
        )
    )

    # ============================================
    # JOIN WITH INGREDIENT LOOKUP + COUNT FLAGS
    # ============================================

    # Step 1: Explode ingredients array to get one row per ingredient
    df_ingredients_exploded = (
        df_with_brand
        .select(
            "product_id",
            F.explode("ingredients").alias("ingredient")
        )
    )

    # Step 2: Join with ingredient lookup
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
            # Create a struct for each matched ingredient
            F.struct(
                F.col("i.ingredient").alias("name"),
                F.col("il.wiki_id").alias("wiki_id"),
                F.col("il.wiki_title").alias("wiki_title"),
                F.col("il.wiki_url").alias("wiki_url"),
                F.col("il.wiki_description").alias("description"),
                F.col("il.infobox_type").alias("type"),
                F.col("il.categories").alias("categories"),
                # Include boolean flags
                F.col("il.is_sweetener"),
                F.col("il.is_allergen"),
                F.col("il.is_carcinogenic")
            ).alias("ingredient_wiki"),
            # Also keep the flags separately for counting
            F.col("il.is_sweetener"),
            F.col("il.is_allergen"),
            F.col("il.is_carcinogenic")
        )
    )

    # Step 3: Group by product_id and aggregate
    df_ingredients_aggregated = (
        df_ingredients_matched
        .groupBy("product_id")
        .agg(
            # Collect all matched ingredients
            F.collect_list("ingredient_wiki").alias("ingredients_wiki"),
            # Count boolean flags
            F.sum(F.when(F.col("is_sweetener"), 1).otherwise(0)).alias("sweetener_count"),
            F.sum(F.when(F.col("is_allergen"), 1).otherwise(0)).alias("allergen_count"),
            F.sum(F.when(F.col("is_carcinogenic"), 1).otherwise(0)).alias("carcinogen_count")
        )
    )

    # ============================================
    # FINAL JOIN - Add ingredients_wiki back to products
    # ============================================
    df_enriched = (
        df_with_brand.alias("p")
        .join(
            df_ingredients_aggregated.alias("iw"),
            "product_id",
            "left"
        )
        .select(
            "p.*",
            # Use coalesce to handle products with no matched ingredients
            F.coalesce("iw.ingredients_wiki", F.array()).alias("ingredients_wiki"),
            # Ingredient flag counts (0 if no matches)
            F.coalesce("iw.sweetener_count", F.lit(0)).alias("sweetener_count"),
            F.coalesce("iw.allergen_count", F.lit(0)).alias("allergen_count"),
            F.coalesce("iw.carcinogen_count", F.lit(0)).alias("carcinogen_count")
        )
        # Add enrichment statistics
        .withColumn("wiki_enrichment", F.struct(
            (F.col("brand_wiki.wiki_id").isNotNull()).alias("has_brand_wiki"),
            F.size("ingredients_wiki").alias("ingredients_wiki_count"),
            F.col("sweetener_count"),
            F.col("allergen_count"),
            F.col("carcinogen_count"),
            (
                    F.when(F.col("brand_wiki.wiki_id").isNotNull(), 1).otherwise(0) +
                    F.size("ingredients_wiki")
            ).alias("total_wiki_matches")
        ))
    )

    # ============================================
    # WRITE ENRICHED PRODUCTS
    # ============================================
    (
        df_enriched
        .select(F.to_json(F.struct(*df_enriched.columns)).alias("json"))
        .write.mode("overwrite").text(OUT_PATH)
    )

    print(f"\n=== Enrichment Results ===")
    print(f"Total products: {df_enriched.count()}")
    print(f"With brand wiki: {df_enriched.filter('brand_wiki.wiki_id IS NOT NULL').count()}")

    # Average ingredients matched per product
    avg_ingredients = df_enriched.agg(F.avg(F.size("ingredients_wiki"))).collect()[0][0]
    print(f"Avg ingredients with wiki per product: {avg_ingredients:.2f}")

    # Products with at least one wiki match
    products_with_wiki = df_enriched.filter("wiki_enrichment.total_wiki_matches > 0").count()
    print(f"Products with at least one wiki match: {products_with_wiki}")

    # Ingredient flag statistics
    print(f"\n=== Ingredient Flag Statistics ===")
    print(f"Products with sweeteners: {df_enriched.filter('sweetener_count > 0').count()}")
    print(f"Products with allergens: {df_enriched.filter('allergen_count > 0').count()}")
    print(f"Products with carcinogens: {df_enriched.filter('carcinogen_count > 0').count()}")

    # Average counts
    avg_sweeteners = df_enriched.agg(F.avg("sweetener_count")).collect()[0][0]
    avg_allergens = df_enriched.agg(F.avg("allergen_count")).collect()[0][0]
    avg_carcinogens = df_enriched.agg(F.avg("carcinogen_count")).collect()[0][0]
    print(f"Avg sweeteners per product: {avg_sweeteners:.2f}")
    print(f"Avg allergens per product: {avg_allergens:.2f}")
    print(f"Avg carcinogens per product: {avg_carcinogens:.2f}")

    print(f"\nOutput: {OUT_PATH}")

    # ============================================
    # SHOW SAMPLE ENRICHED PRODUCT
    # ============================================
    print("\n=== Sample Enriched Product ===")
    sample = df_enriched.filter("brand_wiki.wiki_id IS NOT NULL").first()

    if sample:
        import json
        sample_dict = sample.asDict()

        # Pretty print the sample
        print(json.dumps({
            "product_id": sample_dict["product_id"],
            "name": sample_dict["name"],
            "brand": sample_dict["brand"],
            "category": sample_dict["category"],
            "brand_wiki": {
                "title": sample_dict["brand_wiki"]["wiki_title"] if sample_dict["brand_wiki"] else None,
                "url": sample_dict["brand_wiki"]["wiki_url"] if sample_dict["brand_wiki"] else None,
                "website": sample_dict["brand_wiki"]["website"] if sample_dict["brand_wiki"] else None,
                "introduced": sample_dict["brand_wiki"]["introduced"] if sample_dict["brand_wiki"] else None,
                "description": sample_dict["brand_wiki"]["description"][:100] + "..." if sample_dict["brand_wiki"] and
                                                                                         sample_dict["brand_wiki"][
                                                                                             "description"] else None,
            },
            "ingredients_wiki_count": len(sample_dict["ingredients_wiki"]) if sample_dict["ingredients_wiki"] else 0,
            "sweetener_count": sample_dict["sweetener_count"],
            "allergen_count": sample_dict["allergen_count"],
            "carcinogen_count": sample_dict["carcinogen_count"],
            "ingredients_wiki_sample": [
                {
                    "name": ing["name"],
                    "wiki_title": ing["wiki_title"],
                    "is_sweetener": getattr(ing, "is_sweetener", False),
                    "is_allergen": getattr(ing, "is_allergen", False),
                    "is_carcinogenic": getattr(ing, "is_carcinogenic", False)
                }
                for ing in (sample_dict["ingredients_wiki"][:5] if sample_dict["ingredients_wiki"] else [])
            ],
            "wiki_enrichment": sample_dict["wiki_enrichment"]
        }, indent=2, default=str))

    # SHOW PRODUCTS WITH HIGHEST COUNTS
    print("\n=== Products with Most Allergens ===")
    df_enriched.filter("allergen_count > 0").select(
        "name", "brand", "allergen_count"
    ).orderBy(F.desc("allergen_count")).show(5, truncate=False)

    spark.stop()