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
    TermQuery, PhraseQuery, FuzzyQuery,
)
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.queryparser.classic import QueryParser, MultiFieldQueryParser  # duplicate import but harmless

INDEX_FOLDER = "./pylucene/product_index"  # on-disk index location shared with Docker container


def print_header(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_results(hits, searcher, max_results=10):
    print(f"\nFound: {hits.totalHits.value} products\n")  # uses Lucene's TotalHits object
    for i, hit in enumerate(hits.scoreDocs[:max_results], 1):
        doc = searcher.doc(hit.doc)  # loads stored fields for this hit
        print(f"  {i}. [Score: {hit.score:.2f}] {doc.get('name')}")
        print(f"     Brand: {doc.get('brand')} | Category: {doc.get('category')}")
        price = doc.get('price_num')
        if price:
            print(f"     Price: {price}")  # price_num was stored as a string field alongside the numeric point field


def search_examples():
    lucene.initVM()  # starts the embedded JVM for PyLucene
    print("Lucene Version:", Version.LATEST)

    directory = FSDirectory.open(Paths.get(INDEX_FOLDER))  # opens the FSDirectory backing the index
    reader = DirectoryReader.open(directory)  # low-level index reader
    searcher = IndexSearcher(reader)  # search API on top of the reader
    analyzer = StandardAnalyzer()  # tokenizer + filters, must match what was used at indexing time

    single_parser = QueryParser("name", analyzer)  # default field parser for single-field queries

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

    multi_parser = MultiFieldQueryParser(search_fields, analyzer)  # parser that knows all text fields

    def multi_parse(q):
        return MultiFieldQueryParser.parse(multi_parser, q)  # uses the parser instance with all configured fields

    print_header("PYLUCENE SEARCH EXAMPLES")

    print_header("TERM QUERY")

    print("\nExample 1a: Multi-field search with multiple terms")
    print("Query: (chocolate OR cocoa) AND (milk OR dark)")

    bool_builder = BooleanQuery.Builder()  # explicit boolean composition instead of relying on parser precedence
    bool_builder.add(multi_parse("chocolate OR cocoa"), BooleanClause.Occur.MUST)  # first clause group
    bool_builder.add(multi_parse("milk OR dark"), BooleanClause.Occur.MUST)  # second clause group

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 1b: Multi-field search with brand and ingredient")
    print("Query: (wine OR beer) AND ingredients:malt")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("wine OR beer"), BooleanClause.Occur.MUST)
    ing_parser = QueryParser("ingredients", analyzer)  # forces term to match only the ingredients field
    bool_builder.add(ing_parser.parse("malt"), BooleanClause.Occur.MUST)

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print_header("FUZZY QUERY")

    print("\nExample 2a: Multi-field fuzzy with term combination")
    print("Query: (choclate~ OR strawbery~) AND (candy OR snack)")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("choclate~ OR strawbery~"), BooleanClause.Occur.MUST)  # fuzzy variants for typos
    bool_builder.add(multi_parse("candy OR snack"), BooleanClause.Occur.MUST)

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 2b: Fuzzy search with price range")
    print("Query: orgnic~ AND price_num:[0.0 TO 10.0]")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("orgnic~"), BooleanClause.Occur.MUST)  # fuzzy brand/descriptor
    bool_builder.add(
        DoublePoint.newRangeQuery("price_num", 0.0, 10.0),  # numeric price range filter
        BooleanClause.Occur.MUST,
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print_header("BOOLEAN QUERY")

    print("\nExample 3a: Multi-field OR")
    print("Query: rowntrees OR fruit OR pastilles OR gums OR jelly OR tots OR vegan OR artificial OR colours")
    query = multi_parse("rowntrees OR fruit OR pastilles OR gums OR jelly OR tots OR vegan OR artificial OR colours")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 3b: Multi-field OR")
    print("Query: halloween OR led OR pumpkin OR lantern OR string OR lights OR maple OR garland OR wreath OR battery")

    query = multi_parse("halloween OR led OR pumpkin OR lantern OR string OR lights OR maple OR garland OR wreath OR battery")
    hits = searcher.search(query, 10)
    print_results(hits, searcher)

    print_header("RANGE QUERY")

    print("\nExample 4a: Complex filter - chocolate with low allergens and price range")
    print("Query: chocolate AND allergen_count:[0 TO 2] AND price_num:[1.0 TO 5.0] NOT category:Bakery")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("chocolate"), BooleanClause.Occur.MUST)  # base text query
    bool_builder.add(
        IntPoint.newRangeQuery("allergen_count", 0, 2),  # integer point range on allergen_count
        BooleanClause.Occur.MUST,
    )
    bool_builder.add(
        DoublePoint.newRangeQuery("price_num", 1.0, 5.0),  # double point range on price_num
        BooleanClause.Occur.MUST,
    )

    cat_parser = QueryParser("category", analyzer)
    bool_builder.add(cat_parser.parse("Bakery"), BooleanClause.Occur.MUST_NOT)  # exclusion by category

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 4b: Products with wiki enrichment and moderate price")
    print("Query: (chocolate OR candy OR snack) AND price_num:[2.0 TO 10.0] AND ingredients_wiki_count:[1 TO 100]")

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_parse("chocolate OR candy OR snack"), BooleanClause.Occur.MUST)
    bool_builder.add(
        DoublePoint.newRangeQuery("price_num", 2.0, 10.0),
        BooleanClause.Occur.MUST,
    )
    bool_builder.add(
        IntPoint.newRangeQuery("ingredients_wiki_count", 1, 100),  # ensures products have some wiki enrichment
        BooleanClause.Occur.MUST,
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print_header("PHRASE QUERY")

    phrase_fields = [
        "name",
        "description",
        "ingredients",
        "highlights",
        "brand_description",
        "ingredient_wiki_names",
    ]

    phrase_parser = MultiFieldQueryParser(phrase_fields, analyzer)  # separate parser focused on phrase-relevant fields

    def multi_phrase_parse(q):
        return MultiFieldQueryParser.parse(phrase_parser, q)  # uses same trick as multi_parse but with phrase fields

    print("\nExample 5a: Phrase search with allergen restriction")
    print('Query: "gluten free" AND allergen_count:[0 TO 3]')

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(multi_phrase_parse('"gluten free"'), BooleanClause.Occur.MUST)  # exact phrase in any phrase_field
    bool_builder.add(
        IntPoint.newRangeQuery("allergen_count", 0, 3),
        BooleanClause.Occur.MUST,
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)

    print("\n" + "-" * 80)
    print("\nExample 5b: Multi-phrase with slop and exclusions")
    print('Query: "dark chocolate"~2 AND ingredients_wiki_count:[3 TO 100] NOT sweetener_count:[1 TO 100]')

    phrase_builder = PhraseQuery.Builder()
    phrase_builder.add(Term("description", "dark"))  # phrase anchored in the description field
    phrase_builder.add(Term("description", "chocolate"))
    phrase_builder.setSlop(2)  # allows up to 2 intervening terms between "dark" and "chocolate"

    bool_builder = BooleanQuery.Builder()
    bool_builder.add(phrase_builder.build(), BooleanClause.Occur.MUST)
    bool_builder.add(
        IntPoint.newRangeQuery("ingredients_wiki_count", 3, 100),
        BooleanClause.Occur.MUST,
    )
    bool_builder.add(
        IntPoint.newRangeQuery("sweetener_count", 1, 100),
        BooleanClause.Occur.MUST_NOT,  # exclude products with any sweeteners
    )

    hits = searcher.search(bool_builder.build(), 10)
    print_results(hits, searcher)


if __name__ == "__main__":
    search_examples()  # entry point when script is executed directly
