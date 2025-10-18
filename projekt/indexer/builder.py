from collections import defaultdict, Counter
from typing import List, Dict, Any
from indexer.tokenizer import tokenize
import json
import math

class IndexBuilder:
    def __init__(self, app_cfg):
        self.app_cfg = app_cfg

    def doc_text(self, d: dict) -> str:
        parts = [
            str(d.get("name") or ""),
            str(d.get("brand") or ""),
            str(d.get("category") or ""),
            str(d.get("description") or ""),
        ]
        ing = d.get("ingredients")
        if isinstance(ing, list):
            parts.append(" ".join(str(x) for x in ing if x))
        else:
            parts.append(str(ing or ""))
        return " ".join(p for p in parts if p)

    def save(self, obj: Dict[str, Any], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    @staticmethod
    def idf(N, n0):
        return math.log(N/n0)

    def find_term_doc(self, postings, term, did, N):
        term_query =  postings.get(term)
        for doc_id, tf in term_query[2:]:
            n0 = term_query[0]
            if doc_id == did:
                return tf * self.idf(N, n0)

    def build(self, docs: List[dict]) -> Dict[str, Any]:
        postings: Dict[str, list] = defaultdict(list)

        N = len(docs)
        max_id = max(int(d["product_id"]) for d in docs if d.get("product_id") is not None)
        doc_len = [-1] * (max_id + 1)

        # build index
        for d in docs:
            did = int(d["product_id"])
            tokens = tokenize(self.doc_text(d))
            doc_len[did] = len(tokens)
            tf = Counter(tokens)
            for term, count in tf.items():
                postings[term].append([did, int(count)])

        finalized = {}
        for term, plist in postings.items():
            plist.sort(key=lambda x: x[0])
            total_tf = sum(c for _, c in plist)
            n0  = len(plist)
            finalized[term] = [n0, int(total_tf)] + plist

        postings_sorted = dict(sorted(finalized.items(), key=lambda kv: kv[0]))

        # build l2 distances
        l2_per_doc = [-1] * (max_id + 1)
        for d in docs:
            did = int(d["product_id"])
            tokens = tokenize(self.doc_text(d))
            tf = Counter(tokens)
            ws = []
            for term, count in tf.items():
                w = self.find_term_doc(postings_sorted, term, did, N)
                ws.append(w)

            #output
            l2_per_doc[did] = math.sqrt(sum(w*w for w in ws))


        out = {"__meta__": {"N": N, "doc_len": doc_len, "l2_dists": l2_per_doc}}
        out["postings"] = postings_sorted
        return out
