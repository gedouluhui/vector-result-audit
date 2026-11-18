"""Data-only conversions. No engine imports, connections or ID guessing."""
import sys
from .schema import InputError, _identifier, _number, validate_snapshot, DEFAULT_MAX_WORK, MAX_RESULT_ROWS


def _mapping(id_map, *, faiss=False):
    if not isinstance(id_map, dict) or not id_map or len(id_map) > 100000:
        raise InputError("id_map must be a nonempty explicit mapping, at most 100000 entries")
    targets = set()
    for source, target in id_map.items():
        valid = type(source) is int and source >= 0
        if not faiss:
            valid = valid or (type(source) is str and bool(source))
        if not valid:
            raise InputError("id_map keys must be provider IDs, not booleans or Faiss sentinels")
        _identifier(target, "id_map target")
        if target in targets:
            raise InputError("id_map must be one-to-one; distinct provider IDs cannot alias a document")
        targets.add(target)
    return id_map


def _matrix(value, name):
    shape = getattr(value, "shape", None)
    if shape is not None:
        if len(shape) != 2 or any(type(n) is not int or n < 0 for n in shape):
            raise InputError(name + ": expected a 2-D array")
        if shape[0] > 10000 or shape[1] > 10000 or shape[0] * shape[1] > MAX_RESULT_ROWS:
            raise InputError(name + ": too many result rows")
        value = value.tolist()
    if not isinstance(value, list) or len(value) > 10000:
        raise InputError(name + ": expected a bounded nested list or 2-D array")
    lengths = []
    for row in value:
        if not isinstance(row, list):
            raise InputError(name + ": each query must be a list")
        lengths.append(len(row))
    if sum(lengths) > MAX_RESULT_ROWS or any(n > 10000 for n in lengths):
        raise InputError(name + ": too many result rows")
    if len(set(lengths)) > 1:
        raise InputError(name + ": ragged arrays are not Faiss search output")
    return value


def faiss_rows(labels, scores, *, id_map):
    """Map Faiss search labels/scores; -1 -> position-preserving null padding.

    IndexFlatL2 scores are squared L2. The caller still declares the snapshot's
    metric, encoding, eligibility and allow_null_padding; nothing is inferred.
    """
    mapping = _mapping(id_map, faiss=True)
    labels, scores = _matrix(labels, "labels"), _matrix(scores, "scores")
    if len(labels) != len(scores) or any(len(a) != len(b) for a,b in zip(labels,scores)):
        raise InputError("labels and scores must have identical shape")
    output = []
    for ids, values in zip(labels, scores):
        rows = []
        for label, score in zip(ids, values):
            if type(label) is not int:
                raise InputError("Faiss labels must be integers, not booleans/floats")
            if label == -1:
                rows.append({"id": None, "score": None})
            elif label not in mapping:
                raise InputError(f"unmapped Faiss label {label!r}")
            else:
                rows.append({"id": mapping[label], "score": _number(score, "Faiss score", -sys.float_info.max, sys.float_info.max)})
        output.append(rows)
    return output


def qdrant_rows(points, *, id_map):
    """Convert QueryResponse.points (ScoredPoints or id/score dicts) for one query."""
    mapping = _mapping(id_map)
    if not isinstance(points, (list, tuple)) or len(points) > MAX_RESULT_ROWS:
        raise InputError("Qdrant points must be a bounded list/tuple")
    rows = []
    for point in points:
        if isinstance(point, dict):
            pid, score = point.get("id"), point.get("score")
        else:
            pid, score = getattr(point, "id", None), getattr(point, "score", None)
        if type(pid) not in (int, str) or pid not in mapping:
            raise InputError(f"invalid or unmapped Qdrant point ID {pid!r}")
        rows.append({"id": mapping[pid], "score": _number(score, "Qdrant score", -sys.float_info.max, sys.float_info.max)})
    return rows


def attach_results(snapshot, rows, *, max_work=DEFAULT_MAX_WORK):
    """Replace every query's results by position in a validated private copy."""
    data = validate_snapshot(snapshot, max_work=max_work)
    if not isinstance(rows, list) or len(rows) != len(data["queries"]):
        raise InputError("one result list is required for every query; no truncating zip")
    for query, result in zip(data["queries"], rows):
        query["results"] = result
    return validate_snapshot(data, max_work=max_work)
