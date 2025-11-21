"""
PyLucene search examples - 2 examples for each query type
"""
import lucene
from org.apache.lucene.util import Version
from java.nio.file import Paths
from org.apache.lucene.analysis.standard import StandardAnalyzer
from org.apache.lucene.document import IntPoint, DoublePoint
from org.apache.lucene.index import DirectoryReader, Term
from org.apache.lucene.queryparser.classic import QueryParser, MultiFieldQueryParser
from org.apache.lucene.search import (
    IndexSearcher, BooleanQuery, BooleanClause,
    TermQuery, PhraseQuery, FuzzyQuery
)
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.queryparser.classic import QueryParser, MultiFieldQueryParser

INDEX_FOLDER = "./pylucene/product_index"


def print_header(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_results(hits, searcher, max_results=5):
    print(f"\nFound: {hits.totalHits.value} products\n")
    for i, hit in enumerate(hits.scoreDocs[:max_results], 1):
        doc = searcher.doc(hit.doc)
        print(f"  {i}. [Score: {hit.score:.2f}] {doc.get('name')}")
        print(f"     Brand: {doc.get('brand')} | Category: {doc.get('category')}")


def search_examples():
    lucene.initVM()
    print("Lucene Version:", Version.LATEST)

    directory = FSDirectory.open(Paths.get(INDEX_FOLDER))
    reader = DirectoryReader.open(directory)
    searcher = IndexSearcher(reader)
    analyzer = StandardAnalyzer()

    single_parser = QueryParser("name", analyzer)

    search_fields = [
        "name",
        "description",
        "ingredients",
        "highlights",
        "brand",
        "category",
        "brand_description",
        "ingredient_wiki_names",
    ]

    # Create instance with fields and analyzer
    multi_parser = MultiFieldQueryParser(search_fields, analyzer)

    def multi_parse(q):
        return MultiFieldQueryParser.parse(multi_parser, q)

    print_header("PYLUCENE SEARCH EXAMPLES")

    print_header("1️⃣  TERM QUERY")

    print("\nExample 1a: Multi-field search")
    print("Query: chocolate")
    query = multi_parse("chocolate")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 1b: Single-field search")
    print("Query: name:organic")
    query = single_parser.parse("organic")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print_header("2️⃣  FUZZY QUERY")

    print("\nExample 2a: Multi-field fuzzy")
    print("Query: choclate~ (typo)")
    query = multi_parse("choclate~")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 2b: Single-field fuzzy")
    print("Query: name:orgnic~ (typo)")
    query = single_parser.parse("orgnic~")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print_header("3️⃣  BOOLEAN QUERY")

    print("\nExample 3a: Multi-field AND")
    print("Query: chocolate organic")
    query = multi_parse("chocolate organic")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 3b: Mixed with NOT")
    print("Query: chocolate category:Snacks NOT brand:Nestle")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("chocolate"), BooleanClause.Occur.MUST)

    cat_parser = QueryParser("category", analyzer)
    bool_builder.add(cat_parser.parse("Snacks"), BooleanClause.Occur.MUST)

    brand_query = TermQuery(Term("brand", "nestle"))
    bool_builder.add(brand_query, BooleanClause.Occur.MUST_NOT)

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print_header("4️⃣  RANGE QUERY")

    print("\nExample 4a: Text + allergen range")
    print("Query: chocolate AND allergen_count:[0 TO 2]")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("chocolate"), BooleanClause.Occur.MUST)
    bool_builder.add(
        IntPoint.newRangeQuery("allergen_count", 0, 2),
        BooleanClause.Occur.MUST,
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 4b: Price range")
    print("Query: category:Wine AND price_num:[5.0 TO 15.0]")

    bool_builder = BooleanQuery.Builder()
    cat_parser = QueryParser("category", analyzer)
    bool_builder.add(cat_parser.parse("Wine"), BooleanClause.Occur.MUST)
    bool_builder.add(
        DoublePoint.newRangeQuery("price_num", 5.0, 15.0),
        BooleanClause.Occur.MUST,
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print_header("5️⃣  PHRASE QUERY")

    phrase_fields = [
        "name",
        "description",
        "ingredients",
        "highlights",
        "brand_description",
        "ingredient_wiki_names",
    ]

    phrase_parser = MultiFieldQueryParser(phrase_fields, analyzer)

    def multi_phrase_parse(q):
        return MultiFieldQueryParser.parse(phrase_parser, q)

    print("\nExample 5a: Multi-field phrase")
    print('Query: "gluten free"')
    query = multi_phrase_parse('"gluten free"')
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 5b: Phrase with slop")
    print('Query: "dark chocolate"~2 (max 2 words between)')

    phrase_builder = PhraseQuery.Builder()
    phrase_builder.add(Term("description", "dark"))
    phrase_builder.add(Term("description", "chocolate"))
    phrase_builder.setSlop(2)

    hits = searcher.search(phrase_builder.build(), 10)
    print_results(hits, searcher)


if __name__ == "__main__":
    search_examples()
