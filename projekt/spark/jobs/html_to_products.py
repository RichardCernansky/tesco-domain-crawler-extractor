# PySpark: extrakcia produktov priamo v Spark SQL podľa regexov z configu
# Výstup: data/out/products_from_spark_regex.ndjson/part-*
#
# Spustenie:
#   spark-submit spark/jobs/html_to_products_sql.py
#
# Pointa:
# - Načíta všetky *.html ako (path, html)
# - Aplikuje regexy zo site_config.json (presne tvoje vzory)
# - Zloží normalizovaný záznam produktu (name, brand, price, ingredients, ...)
# - Odfiltruje nekompletné (vyžaduje aspoň name + price)
# - Zapíše NDJSON (jeden JSON objekt na riadok), pripravené na ďalšie Spark joby


from typing import Iterable
from pathlib import Path
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.column import Column

def null_if_empty(c: Column) -> Column:
    """Return NULL if c is NULL or only whitespace, else c."""
    return (
        F.when(c.isNull(), None)
         .when(F.length(F.trim(c)) == 0, None)
         .otherwise(c)
    )

def inline_flags(flags_list):
    m = {"I": "i", "S": "s", "M": "m", "U": "u"}
    return f"(?{''.join(m[f] for f in flags_list if f in m)})" if flags_list else ""

def rx(col_html: Column, pattern_with_flags: str, group: int = 1) -> Column:
    """Safe regexp_extract: returns NULL when no match/empty."""
    return null_if_empty(F.regexp_extract(col_html, pattern_with_flags, group))

def first_nonempty_str(*cols: Iterable[Column]) -> Column:
    """First non-empty (after trimming) among the given Columns."""
    # keep only real Columns (filter out accidental None)
    cols = [c for c in cols if isinstance(c, Column)]
    if not cols:
        # return a NULL literal Column so callers can still use it
        return F.lit(None).cast("string")
    cleaned = [null_if_empty(c) for c in cols]
    return F.coalesce(*cleaned)



def parse_products_spark(APP_CFG: dict, SITE_CFG: dict):

    RX = SITE_CFG["regexes"]                 # slovník "regexes" z configu
    FLAGS = inline_flags(RX.get("flags", []))  # napr. (?is) keď máš ["I","S"] v configu

    HTML_GLOB  = str(Path(APP_CFG["storage_path"])  / "*.html")  # zdrojové HTML súbory
    OUT_NDJSON = str(Path(APP_CFG["spark_storage_path"]) / "products_spark.ndjson")  # cieľový NDJSON adresár
    CHECKPOINT_DIR = str(Path(APP_CFG["spark_storage_path"]) / "_checkpoints") # Adresár pre checkpoint

    # --------------------------- spark session -----------------------------------
    spark = (
        SparkSession.builder
        .appName("html-to-products-sql")     # názov jobu
        .master("local[*]")                  # lokálny režim, využije všetky CPU thready
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")   # potlač INFO logy, WARN stačí

    # *** FIX: Set checkpoint directory ***
    # This is required for .checkpoint() to work
    spark.sparkContext.setCheckpointDir(CHECKPOINT_DIR)

    print("master:", spark.sparkContext.master)
    print("defaultParallelism:", spark.sparkContext.defaultParallelism)

    # --------------------------- load HTML files ---------------------------------
    df_html = spark.sparkContext.wholeTextFiles(HTML_GLOB).toDF(["source_file", "html"])
    html = F.col("html")  # skrátená referencia na HTML stĺpec

    # --------------------------- apply regexy ------------------------------------
    # BODY (ak existuje <body>...</body>, ohranič parsovanie na jeho obsah; inak použi celé HTML)
    body = F.coalesce(
        rx(html, FLAGS + RX["body_regex"], group=1),
        html  # fallback: celé HTML
    )

    # NAME (povinné pole)
    name = rx(body, FLAGS + RX["name_regex"], group=1)
    # BRAND (môže byť None)
    brand = rx(body, FLAGS + RX["brand_regex"], group=1)
    # CATEGORY (breadcrumb leaf – posledná vetva kategórie na stránke)
    category = rx(body, FLAGS + RX["category_regex"], group=1)
    # INGREDIENTS:
    ingredients = rx(body, FLAGS + RX["ingredients_regex"], group=1)
    description = rx(body, FLAGS + RX["description_regex"], group=1)
    highlights  = rx(body, FLAGS + RX["highlights_lines_regex"], group=1)

    price_candidates    = []  # kandidáti na hlavnú cenu
    unitpair_candidates = []  # kandidáti na "7.96/kg"
    for key, pat in RX["price_regexes"].items():
        # group(1) = price
        price_candidates.append(rx(body, FLAGS + pat, group=1))
        # group(2) = unitpair "7.96/kg"
        unitpair_candidates.append(rx(body, FLAGS + pat, group=2))

    # vyber prvý neprázdny hit naprieč všetkými vzormi
    price    = first_nonempty_str(*price_candidates)
    unitpair = first_nonempty_str(*unitpair_candidates)
    #
    price_currency = F.lit("£")
    #

    # # NUTRITION:
    # # - z mapy názov->regex v configu zložíme Spark map<string,string>
    # # - každý regex ťahá group(1) pre konkrétny nutrient (energy/fat/...)
    nut_pairs = []
    for k, pat in RX["nutrition_regexes"].items():
        nut_pairs += [F.lit(k), rx(body, FLAGS + pat, group=1)]
    nutrition_table = F.create_map(*nut_pairs) if nut_pairs else F.map_from_arrays(F.array(), F.array())

    # --------------------------- STAGE 1: Calculate Fields ---------------------------
    # Zloženie finálneho DataFrame so schémou produktu.
    # product_id: deterministický pozitívny hash cesty (stabilné ID naprieč behmi)
    df_calculated = (
        df_html
        .select(
            F.abs(F.hash("source_file")).alias("product_id"),
            "source_file",
            name.alias("name"),
            brand.alias("brand"),
            category.alias("category"),
            price_currency.alias("price_currency"),
            price.alias("price"),
            ingredients.alias("ingredients"),
            description.alias("description"),
            nutrition_table.alias("nutrition_table"),
            unitpair.alias("unitpair"),
            highlights.alias("highlights"),
        )
    )

    # --------------------------- *** FIX: CHECKPOINT *** -----------------------------
    # This materializes the results of the complex stage above and truncates
    # the query plan. The next stage will be simple and compile easily.
    print("Checkpointing calculated DataFrame to break query plan...")
    df_calculated = df_calculated.checkpoint()
    print("Checkpoint complete.")


    # --------------------------- STAGE 2: Filter and Write ---------------------------
    # This stage is now very simple and will not cause a CodeGen error.
    df_final = (
        df_calculated
        # Minimálny "completeness gate": vyžaduj name + price
        .where(F.col("name").isNotNull() & F.col("price").isNotNull())
    )

    # --------------------------- write NDJSON (iba) ------------------------------
    # Uloženie ako NDJSON: každý riadok je JSON objekt (to_json(struct(*cols)))
    # - .repartition(8) nastav podľa I/O (viac part-* -> paralelnejší zápis)
    # - .mode("overwrite") pre idempotentné behy (prepíše staré výsledky)
    (
        df_final.select(F.to_json(F.struct(*df_final.columns)).alias("json"))
          .repartition(8)
          .write.mode("overwrite").text(OUT_NDJSON)
    )

    # Rýchle info pre konzolu
    print(f"OK: rows={df_final.count()}") # Count from the final, filtered DF
    print(f"NDJSON : {OUT_NDJSON}")

    # Shutdown
    spark.stop()

