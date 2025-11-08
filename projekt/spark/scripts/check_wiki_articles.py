# check_wiki_articles.py
"""
Quick check of extracted Wikipedia articles.
"""

from pathlib import Path
from pyspark.sql import SparkSession, functions as F


def check_wiki_articles():
    """
    Read and display stats about extracted Wikipedia articles.
    """

    WIKI_ARTICLES_PATH = "data/wiki/out/wiki_articles.parquet"

    spark = (
        SparkSession.builder
        .appName("check-wiki-articles")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Read the parquet file (fast!)
    df = spark.read.parquet(WIKI_ARTICLES_PATH)

    print("\n=== Wikipedia Articles Stats ===")
    print(f"Total articles: {df.count()}")
    print(f"With infobox: {df.filter('has_infobox').count()}")

    # Schema
    print("\nSchema:")
    df.printSchema()

    # Sample articles
    print("\nSample articles (10):")
    df.select(
        "wiki_title",
        "title_normalized",
        "has_infobox",
        "infobox_type",
        F.length("wiki_text").alias("text_length")
    ).show(10, truncate=False)

    # Top infobox types
    print("\nTop infobox types:")
    df.filter("has_infobox AND infobox_type != ''") \
        .groupBy("infobox_type") \
        .count() \
        .orderBy(F.desc("count")) \
        .show(20, truncate=False)

    # Sample full record
    print("\nSample full record (1st article):")
    sample = df.select(
        "wiki_id",
        "wiki_title",
        "title_normalized",
        "has_infobox",
        "infobox_type",
        "categories",
        "wiki_url",
        F.substring("wiki_text", 1, 500).alias("wiki_text_preview")
    ).first()

    print(f"\nID: {sample.wiki_id}")
    print(f"Title: {sample.wiki_title}")
    print(f"Normalized: {sample.title_normalized}")
    print(f"Has infobox: {sample.has_infobox}")
    print(f"Infobox type: {sample.infobox_type}")
    print(f"Categories: {sample.categories[:5] if sample.categories else []}")
    print(f"URL: {sample.wiki_url}")
    print(f"\nText preview (first 500 chars):\n{sample.wiki_text_preview}")

    spark.stop()


if __name__ == "__main__":
    check_wiki_articles()