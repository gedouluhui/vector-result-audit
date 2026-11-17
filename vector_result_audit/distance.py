"""Binary64 exhaustive reference; no BLAS-dependent reduction order."""
import math
from .schema import InputError


def distance(a, b, metric):
    if metric == "l2":
        result = math.dist(a, b)
    elif metric == "inner_product":
        result = -math.fsum(x * y for x, y in zip(a, b))
    elif metric == "cosine":
        na, nb = math.hypot(*a), math.hypot(*b)
        similarity = math.fsum((x / na) * (y / nb) for x, y in zip(a, b))
        result = 1.0 - max(-1.0, min(1.0, similarity))
    else:
        raise InputError("unsupported metric")
    if not math.isfinite(result):
        raise InputError("computed reference distance is not finite")
    return result


def encoded_score(reference_distance, metric, score_kind):
    if score_kind == "squared_l2":
        value = reference_distance * reference_distance
    elif score_kind == "dot":
        value = -reference_distance
    elif score_kind == "cosine_similarity":
        value = 1.0 - reference_distance
    else:
        value = reference_distance
    if not math.isfinite(value):
        raise InputError("computed reference score is not finite")
    return value
