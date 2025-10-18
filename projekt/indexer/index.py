import json, math
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any
from my_utils import load_jsonl
from indexer.tokenizer import tokenize


def idf(N, n0):
    return math.log(N / n0)

class Index:
    def __init__(self, app_cfg):
        self.app_cfg = app_cfg
        self.load_index(app_cfg["index_path"])

    def load_index(self, path: str):
        self.docs = load_jsonl(self.app_cfg["products_path"])
        with open(path, "r", encoding="utf-8") as f:
            self.index = json.load(f)
        self.N = self.index["__meta__"]["N"]
        self.postings = self.index["postings"]
        self.max_id = max(int(d["product_id"]) for d in self.docs if d.get("product_id") is not None)
        self.l2_dists = self.index["__meta__"]["l2_dists"]

        return

    def score_idf(self, t_count, n0):
        return t_count * idf(self.N, n0)

    def score_idf_l2(self, t_count, n0, l2):
        return t_count * idf(self.N, n0) / l2 * 100

    def search(self, mode: str, query: str, topk: int) -> List[Tuple[int, float]]:
        tokens = tokenize(query)

        scores = defaultdict(float)
        for d in self.docs:
            for tok in tokens:
                l2_dist = self.l2_dists[int(d["product_id"])]
                tok_posting = self.postings[tok]
                n0 = tok_posting[0]
                for did, t_count in tok_posting[2:]:
                    if did == d["product_id"]:
                       scores[did]  += self.score_idf(t_count, n0) if mode == "idf" else self.score_idf_l2(t_count, n0, l2_dist)

        out = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:topk]
        return out

