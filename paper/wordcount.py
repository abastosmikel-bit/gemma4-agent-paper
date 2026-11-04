"""Word count for the Kaggle writeup limit (3,000 words, counting title, abstract, captions, tables, references).

Excludes HTML comments, image links and markdown syntax. A word is a whitespace-separated token with a letter or
digit in it (so "|", "---", "→" don't count; "L2", "0.24", "[3," do). Prints per-section counts and the total.
Usage: python paper/wordcount.py [paper/draft.md]
"""
import re
import sys
from pathlib import Path

text = Path(sys.argv[1] if len(sys.argv) > 1 else "paper/draft.md").read_text()
text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # image embeds

sections, current = {}, "(front)"
for line in text.splitlines():
    if line.startswith("#"):
        current = line.lstrip("#").strip()
        sections.setdefault(current, 0)
        sections[current] += len([w for w in current.split() if re.search(r"[A-Za-z0-9]", w)])
        continue
    words = [w for w in re.split(r"[\s|]+", line) if re.search(r"[A-Za-z0-9]", w)]
    sections[current] = sections.get(current, 0) + len(words)

for name, n in sections.items():
    print(f"{n:5d}  {name}")
print(f"{sum(sections.values()):5d}  TOTAL (limit 3,000; internal target 2,800)")
