from pathlib import Path

src_dir = Path("data/wiki/out/products_spark.ndjson")
dst_file =  Path("data/wiki/out/products_spark_merged.ndjson")

with open(dst_file, "w", encoding="utf-8") as out:
    for part in sorted(src_dir.glob("part-*")):   # only Spark parts
        with open(part, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                # keep one JSON per line
                out.write(s + "\n")

print(f"✓ merged into {dst_file}")
