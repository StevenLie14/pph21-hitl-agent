from __future__ import annotations

import re

READ_CHARS = 1500
SNIPPET = 240


class DocumentTools:
    def __init__(self, text: str):
        self.text = " ".join((text or "").split())
        self.lower = self.text.lower()

    def search(self, query: str, n: int = 5) -> list[dict]:
        q = " ".join(str(query or "").lower().split())[:120]
        if not q:
            return []
        hits = [m.start() for m in re.finditer(re.escape(q), self.lower)]
        if not hits:
            words = re.findall(r"[\w/.-]{3,}", q)[:8]
            first = [m.start() for m in re.finditer(re.escape(words[0]), self.lower)] if words else []
            scored = sorted(((sum(w in self.lower[max(0, p - 150):p + 300] for w in words), p) for p in first),
                            key=lambda x: (-x[0], x[1]))
            hits = [p for s, p in scored if s >= max(1, len(words) - 1)]
        out, last = [], -10_000
        for p in sorted(hits):
            if p - last < SNIPPET:
                continue
            last = p
            out.append({"posisi": p, "potongan": self.text[max(0, p - SNIPPET // 2):p + SNIPPET]})
        return out[-n:] if len(out) > n else out

    def read(self, position) -> str:
        try:
            p = max(0, min(int(position), len(self.text)))
        except (TypeError, ValueError):
            return "(posisi harus angka)"
        return self.text[p:p + READ_CHARS]
