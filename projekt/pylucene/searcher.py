import lucene
from java.nio.file import Paths
from org.apache.lucene.analysis.standard import StandardAnalyzer
from org.apache.lucene.index import DirectoryReader
from org.apache.lucene.queryparser.classic import QueryParser, MultiFieldQueryParser
from org.apache.lucene.search import IndexSearcher, BooleanQuery
from org.apache.lucene.store import FSDirectory

INDEX_FOLDER = "./pylucene/product_index"

SEARCH_FIELDS = [
    "name",
    "description",
    "ingredients",
    "highlights",
    "brand",
    "category",
    "brand_description",
    "ingredient_wiki_names",
]


def _get_searcher_and_analyzer():
    if not lucene.getVMEnv():
        lucene.initVM()

    # Set this EVERY time, not just on VM init
    BooleanQuery.setMaxClauseCount(4096)

    directory = FSDirectory.open(Paths.get(INDEX_FOLDER))
    reader = DirectoryReader.open(directory)
    searcher = IndexSearcher(reader)
    analyzer = StandardAnalyzer()
    return searcher, analyzer


def search_products(query_text, top_k=10, field=None, fuzzy=True):
    searcher, analyzer = _get_searcher_and_analyzer()
    tokens = [t for t in query_text.strip().split() if t]
    if not tokens:
        return []

    if fuzzy:
        processed = []
        for tok in tokens:
            if len(tok) >= 3 and len(tok) <= 15:
                processed.append(tok + "~")
            else:
                processed.append(tok)
        tokens = processed

    # Use AND instead of OR to reduce clause explosion
    q_string = " ".join(tokens)  # Changed from " OR ".join(tokens)

    if field:
        parser = QueryParser(field, analyzer)
        parser.setDefaultOperator(QueryParser.Operator.OR)
        lucene_query = parser.parse(q_string)
    else:
        parser = MultiFieldQueryParser(SEARCH_FIELDS, analyzer)
        parser.setDefaultOperator(QueryParser.Operator.OR)
        lucene_query = MultiFieldQueryParser.parse(parser, q_string)

    hits = searcher.search(lucene_query, top_k)
    results = []
    for hit in hits.scoreDocs:
        doc = searcher.doc(hit.doc)
        results.append(
            {
                "score": hit.score,
                "name": doc.get("name"),
                "brand": doc.get("brand"),
                "category": doc.get("category"),
                "price_num": doc.get("price_num"),
            }
        )
    return results