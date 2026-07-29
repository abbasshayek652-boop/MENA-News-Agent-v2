from difflib import SequenceMatcher

TIER_WEIGHT = {"A": 3.0, "B": 2.0, "C": 1.0}

FOCUS_KEYWORDS = [
    "lebanon", "beirut", "لبنان", "بيروت",
    "gaza", "غزة",
    "israel", "إسرائيل",
    "hezbollah", "حزب الله",
    "syria", "سوريا",
]


def _sim(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _kw_score(text: str) -> int:
    blob = (text or "").lower()
    return sum(1 for k in FOCUS_KEYWORDS if k.lower() in blob)


def dedupe_and_rank(items: list[dict], title_threshold: float = 0.86) -> list[dict]:
    clusters: list[list[dict]] = []
    for it in items:
        placed = False
        for cl in clusters:
            if _sim(it.get("title", ""), cl[0].get("title", "")) >= title_threshold:
                cl.append(it)
                placed = True
                break
        if not placed:
            clusters.append([it])

    reps: list[dict] = []
    for cl in clusters:
        cl_sorted = sorted(
            cl,
            key=lambda x: (
                -TIER_WEIGHT.get(x.get("tier", "C"), 1.0),
                -_kw_score((x.get("title", "") + " " + x.get("snippet", ""))),
            ),
        )
        reps.append(cl_sorted[0])

    return sorted(
        reps,
        key=lambda x: (
            -TIER_WEIGHT.get(x.get("tier", "C"), 1.0),
            -_kw_score((x.get("title", "") + " " + x.get("snippet", ""))),
        ),
    )
