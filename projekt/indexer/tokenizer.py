from typing import List
import re

def tokenize(txt: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", txt or "") if t]

