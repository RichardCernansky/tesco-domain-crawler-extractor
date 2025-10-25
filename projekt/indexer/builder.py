from collections import defaultdict, Counter
from typing import List, Dict, Any
from indexer.tokenizer import tokenize
from indexer.index import idf
import json
import math


class IndexBuilder:
    def __init__(self, app_cfg):
        self.app_cfg = app_cfg  # app-level config (paths, options)

    def doc_text(self, d: dict) -> str:
        # Build a single concatenated text field from selected product attributes
        parts = [
            str(d.get("name") or ""),        # product name
            str(d.get("brand") or ""),       # brand
            str(d.get("category") or ""),    # category
            str(d.get("description") or ""), # description
        ]
        ing = d.get("ingredients")
        if isinstance(ing, list):
            parts.append(" ".join(str(x) for x in ing if x))  # join ingredient list
        else:
            parts.append(str(ing or ""))  # accept string or empty
        return " ".join(p for p in parts if p)  # final doc text (no empty parts)

    def save(self, obj: Dict[str, Any], path: str) -> None:
        # Persist index structure to JSON file (UTF-8, keep unicode)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def find_term_doc(self, postings, term, did, N):
        # Lookup tf-idf weight for (term, did) using postings header [n0, total_tf, ...]
        term_query =  postings.get(term)  # may be None if term not indexed
        for doc_id, tf in term_query[2:]:
            n0 = term_query[0]  # document frequency for this term
            if doc_id == did:
                return tf * idf(N, n0)  # classic TF * IDF
        # Note: returns None if (term, did) pair does not exist

    def build(self, docs: List[dict]) -> Dict[str, Any]:
        postings: Dict[str, list] = defaultdict(list)  # inverted lists per term

        N = len(docs)  # total number of documents
        max_id = max(int(d["product_id"]) for d in docs if d.get("product_id") is not None)
        doc_len = [-1] * (max_id + 1) # preallocate doc lengths by doc_id (for metadata)

        # build index
        # for all documents
        for d in docs:
            did = int(d["product_id"])  # integer document id
            tokens = tokenize(self.doc_text(d)) # tokenize the composed document text
            doc_len[did] = len(tokens)  # store raw token count as doc length
            tf = Counter(tokens) # term frequencies within this doc
            for term, count in tf.items():
                postings[term].append([did, int(count)]) # append posting (doc_id, tf)

        finalized = {}
        # go through the postings to get the document frequency df=n0
        for term, plist in postings.items():
            plist.sort(key=lambda x: x[0])  # sort postings by doc_id for deterministic order
            total_tf = sum(c for _, c in plist)  # sum of term counts across all docs
            n0  = len(plist)  # document frequency (df)
            finalized[term] = [n0, int(total_tf)] + plist  # header + postings payload

        # sort postings in alphabetical order
        postings_sorted = dict(sorted(finalized.items(), key=lambda kv: kv[0]))  # term-lex order

        # build l2 distances
        l2_per_doc = [-1] * (max_id + 1)  # preallocate per-doc L2 norms
        for d in docs:
            did = int(d["product_id"])
            tokens = tokenize(self.doc_text(d))  # re-tokenize (to rebuild tf for weights)
            tf = Counter(tokens)
            ws = []
            for term, count in tf.items():
                w = self.find_term_doc(postings_sorted, term, did, N)  # TF*IDF weight for (t,d)
                ws.append(w)
            # output
            l2_per_doc[did] = math.sqrt(sum(w*w for w in ws))  # Euclidean norm of doc vector

        # pack metadata and postings into output structure
        out = {"__meta__": {"N": N, "doc_len": doc_len, "l2_dists": l2_per_doc}}
        out["postings"] = postings_sorted
        return out
