import json, math
from collections import defaultdict, Counter  # defaultdict for score accumulation; Counter unused here
from typing import Dict, List, Tuple, Any      # type hints for clarity
from my_utils import load_jsonl                # helper: reads NDJSON lines into Python objects
from indexer.tokenizer import tokenize         # project tokenizer for queries


def idf(N, n0):
    return math.log(N / n0)  # inverse document frequency: ln(N / n0); needs math imported

class Index:
    def __init__(self, app_cfg):
        self.app_cfg = app_cfg                                   # keep app configuration (paths, options)
        self.load_index(app_cfg["index_path"])                   # eager-load index structures on init

    def load_index(self, path: str):
        self.docs = load_jsonl(self.app_cfg["products_path"])    # load product docs (each must have product_id)
        with open(path, "r", encoding="utf-8") as f:
            self.index = json.load(f)                            # load serialized inverted index JSON
        self.N = self.index["__meta__"]["N"]                     # total number of documents
        self.postings = self.index["postings"]                   # term -> [n0, (maybe meta), (doc_id, tf), ...]
        self.max_id = max(int(d["product_id"]) for d in self.docs if d.get("product_id") is not None)  # track largest doc id
        self.l2_dists = self.index["__meta__"]["l2_dists"]       # precomputed L2 norms per doc_id for normalization

        return                                                   # explicit no-op

    def score_idf(self, t_count, n0):
        return t_count * idf(self.N, n0)                         # plain TF * IDF

    def score_idf_l2(self, t_count, n0, l2):
        return t_count * idf(self.N, n0) / l2 * 100              # TF * IDF normalized by L2, scaled for readability

    def search(self, mode: str, query: str, topk: int) -> List[Tuple[int, float]]:
        tokens = tokenize(query)                                 # tokenize user query into terms

        scores = defaultdict(float)                              # doc_id -> accumulated score
        for d in self.docs:                                      # iterate all documents (outer loop)
            for tok in tokens:                                   # score each query token
                l2_dist = self.l2_dists[int(d["product_id"])]    # fetch L2 norm for the current doc
                tok_posting = self.postings[tok]                 # postings list for this token
                n0 = tok_posting[0]                              # document frequency (df) for IDF
                for did, t_count in tok_posting[2:]:             # iterate (doc_id, term_frequency) pairs
                    if did == d["product_id"]:                   # only score current doc if it contains the token
                       scores[did]  += self.score_idf(t_count, n0) if mode == "idf" else self.score_idf_l2(t_count, n0, l2_dist)
                                                                  # choose scoring function based on mode

        out = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:topk]  # top-k docs by score desc
        return out                                               # list of (doc_id, score)
