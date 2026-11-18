"""Binary64 reference with direct scores and stable cosine normalization."""
import math
from .schema import InputError

NUMERICAL_POLICY = "binary64-scaled-cosine-v2"


def _normalized(vector):
    scale = max(abs(x) for x in vector)
    if scale == 0:
        raise InputError("cosine is undefined for zero norm")
    scaled = [x / scale for x in vector]
    norm = math.hypot(*scaled)
    return [x / norm for x in scaled]


def reference(a, b, metric, score_kind=None):
    """Return (display distance, smaller-is-better rank value, optional score).

    Inputs have already been validated. Scores use their direct formula rather
    than a potentially lossy round trip through display distance.
    """
    if metric == "l2":
        distance = rank = math.dist(a, b)
        score = math.fsum((x - y) ** 2 for x, y in zip(a, b)) if score_kind == "squared_l2" else distance
    elif metric == "inner_product":
        dot = math.fsum(x * y for x, y in zip(a, b))
        distance = rank = -dot
        score = dot if score_kind == "dot" else -dot
    elif metric == "cosine":
        na, nb = _normalized(a), _normalized(b)
        similarity = max(-1.0, min(1.0, math.fsum(x * y for x, y in zip(na, nb))))
        distance, rank = 1.0 - similarity, -similarity
        score = similarity if score_kind == "cosine_similarity" else distance
    else:
        raise InputError("unsupported metric")
    if not all(math.isfinite(value) for value in (distance, rank, score)):
        raise InputError("computed reference value is not finite")
    return distance, rank, score if score_kind is not None else None


def distance(a, b, metric):
    """Display distance; use reference() for ranking and direct score evidence."""
    return reference(a, b, metric)[0]
