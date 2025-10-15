from typing import List
from .types import CleanDoc
from .extract_base import domain_weight

def sort_and_unique_citations(docs: List[CleanDoc], top: int = 12) -> List[str]:
    uniq = {}
    for d in docs:
        if d.url and d.url not in uniq:
            uniq[d.url] = domain_weight(d.url)
    return [u for u,_ in sorted(uniq.items(), key=lambda kv: -kv[1])][:top]