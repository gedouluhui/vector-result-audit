"""Strict, bounded snapshot input. No code is executed from input files."""
import json
import math
import sys
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_WORK = 5_000_000
MAX_RESULT_ROWS = 10000
MAX_EVIDENCE_ROWS = 20000
SCORE_KINDS = {"l2": {"l2", "squared_l2"}, "inner_product": {"dot", "negative_dot"},
               "cosine": {"cosine_similarity", "cosine_distance"}}


class InputError(ValueError):
    """The requested audit cannot be evaluated within the supported contract."""


def _fields(obj, required, optional, path):
    if not isinstance(obj, dict):
        raise InputError(f"{path}: expected an object")
    missing = set(required) - obj.keys()
    unknown = obj.keys() - set(required) - set(optional)
    if missing or unknown:
        raise InputError(f"{path}: missing keys {sorted(missing)!r}; unknown keys {sorted(map(str, unknown))!r}")


def _integer(value, path, low, high):
    if type(value) is not int or not low <= value <= high:
        raise InputError(f"{path}: expected integer in [{low}, {high}]")
    return value


def _number(value, path, low=-1e100, high=1e100):
    if type(value) not in (int, float):
        raise InputError(f"{path}: expected a finite number, not a boolean")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: number outside supported range") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise InputError(f"{path}: number outside [{low}, {high}]")
    return value


def _identifier(value, path):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise InputError(f"{path}: expected nonempty string ID, max 256 characters")
    # Reject lone surrogates: reports must be writable as valid UTF-8.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputError(f"{path}: ID is not valid Unicode") from exc
    return value


def _list(value, path, minimum=0, maximum=100000):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise InputError(f"{path}: expected list with {minimum}..{maximum} entries")
    return value


def _vector(value, path, dimension, metric):
    _list(value, path, 1, 4096)
    if dimension is not None and len(value) != dimension:
        raise InputError(f"{path}: dimension differs from corpus")
    result = [_number(x, f"{path}[{i}]") for i, x in enumerate(value)]
    if metric == "cosine" and math.hypot(*result) == 0:
        raise InputError(f"{path}: cosine is undefined for zero norm")
    return result


def validate_snapshot(data, *, max_work=DEFAULT_MAX_WORK):
    """Return a canonical private copy; reject unsupported inputs, never sample."""
    _integer(max_work, "max_work", 1, 10**15)
    _fields(data, {"schema_version", "metric", "k", "corpus", "queries"},
            {"score_kind", "score_atol", "score_rtol", "min_recall", "allow_null_padding",
             "require_scores", "require_sorted"}, "snapshot")
    _integer(data["schema_version"], "schema_version", 1, 1)
    metric = data["metric"]
    if not isinstance(metric, str) or metric not in SCORE_KINDS:
        raise InputError("metric: expected l2, inner_product, or cosine")
    k = _integer(data["k"], "k", 1, 10000)
    kind = data.get("score_kind")
    if kind is not None and (not isinstance(kind, str) or kind not in SCORE_KINDS[metric]):
        raise InputError("score_kind: incompatible with metric")
    atol = _number(data.get("score_atol", 1e-8), "score_atol", 0, 1)
    rtol = _number(data.get("score_rtol", 1e-6), "score_rtol", 0, 1)
    minimum = data.get("min_recall")
    if minimum is not None:
        minimum = _number(minimum, "min_recall", 0, 1)
    padding = data.get("allow_null_padding", False)
    if type(padding) is not bool:
        raise InputError("allow_null_padding: expected boolean")
    policies = {key: data.get(key, False) for key in ("require_scores", "require_sorted")}
    for key, value in policies.items():
        if type(value) is not bool:
            raise InputError(f"{key}: expected boolean")
    if policies["require_scores"] and kind is None:
        raise InputError("require_scores needs an explicit score_kind")
    raw_corpus = _list(data["corpus"], "corpus", 1)
    raw_queries = _list(data["queries"], "queries", 1, 10000)
    _fields(raw_corpus[0], {"id", "vector"}, set(), "corpus[0]")
    dimension = len(_list(raw_corpus[0]["vector"], "corpus[0].vector", 1, 4096))
    work = len(raw_corpus) * len(raw_queries) * dimension
    if work > max_work:
        raise InputError(f"work budget exceeded: {work} scalar comparisons requested, limit {max_work}; no audit performed")
    # Budget report expansion before copying result dictionaries or building evidence.
    result_rows, evidence_rows = 0, len(raw_queries)
    for i, item in enumerate(raw_queries):
        path = f"queries[{i}]"
        _fields(item, {"id", "vector", "eligible_ids", "results"}, set(), path)
        rows = _list(item["results"], path + ".results", 0, 10000)
        selected = item["eligible_ids"]
        eligible_count = len(raw_corpus) if selected is None else len(_list(selected, path + ".eligible_ids"))
        result_rows += len(rows)
        evidence_rows += len(rows) + min(k, eligible_count)
        if result_rows > MAX_RESULT_ROWS:
            raise InputError(f"total result rows exceed {MAX_RESULT_ROWS}; no audit performed")
        if evidence_rows > MAX_EVIDENCE_ROWS:
            raise InputError(f"evidence rows exceed {MAX_EVIDENCE_ROWS} (queries + returned rows + reference top-k); no audit performed")
    corpus, known = [], set()
    for i, item in enumerate(raw_corpus):
        path = f"corpus[{i}]"
        _fields(item, {"id", "vector"}, set(), path)
        identifier = _identifier(item["id"], path + ".id")
        if identifier in known:
            raise InputError(path + ": duplicate corpus ID")
        vector = _vector(item["vector"], path + ".vector", dimension, metric)
        dimension = len(vector)
        known.add(identifier)
        corpus.append({"id": identifier, "vector": vector})
    queries, query_ids = [], set()
    for i, item in enumerate(raw_queries):
        path = f"queries[{i}]"
        _fields(item, {"id", "vector", "eligible_ids", "results"}, set(), path)
        identifier = _identifier(item["id"], path + ".id")
        if identifier in query_ids:
            raise InputError(path + ": duplicate query ID")
        query_ids.add(identifier)
        vector = _vector(item["vector"], path + ".vector", dimension, metric)
        eligible = item["eligible_ids"]
        if eligible is not None:
            _list(eligible, path + ".eligible_ids")
            eligible = [_identifier(x, path + ".eligible_ids") for x in eligible]
            if len(set(eligible)) != len(eligible) or not set(eligible) <= known:
                raise InputError(path + ": eligible IDs must be unique and present in corpus")
        rows = []
        for j, row in enumerate(_list(item["results"], path + ".results", 0, 10000)):
            row_path = f"{path}.results[{j}]"
            _fields(row, {"id"}, {"score"}, row_path)
            rid = row["id"]
            if rid is not None:
                rid = _identifier(rid, row_path + ".id")
            score = row.get("score")
            if score is not None:
                score = _number(score, row_path + ".score", -sys.float_info.max, sys.float_info.max)
                if kind is None:
                    raise InputError(row_path + ": supplied scores require score_kind")
            rows.append({"id": rid, "score": score})
        queries.append({"id": identifier, "vector": vector, "eligible_ids": eligible, "results": rows})
    return {"schema_version": 1, "metric": metric, "k": k, "score_kind": kind,
            "score_atol": atol, "score_rtol": rtol, "min_recall": minimum,
            "allow_null_padding": padding, **policies, "corpus": corpus, "queries": queries}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def parse_snapshot(raw, *, max_work=DEFAULT_MAX_WORK):
    """Decode a byte snapshot once, rejecting duplicate keys and non-JSON numbers."""
    def reject_constant(value):
        raise InputError(f"nonfinite JSON literal: {value}")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("invalid UTF-8 JSON: " + str(exc)) from exc
    return validate_snapshot(data, max_work=max_work)


def read_snapshot(path, *, max_bytes=MAX_BYTES, max_work=DEFAULT_MAX_WORK):
    """Return (validated data, raw bytes), so hashes describe the bytes audited."""
    _integer(max_bytes, "max_bytes", 1, 2**40)
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except OSError as exc:
        raise InputError("cannot read snapshot: " + str(exc)) from exc
    if len(raw) > max_bytes:
        raise InputError(f"input exceeds {max_bytes} byte limit")
    return parse_snapshot(raw, max_work=max_work), raw


def load_snapshot(path, *, max_bytes=MAX_BYTES, max_work=DEFAULT_MAX_WORK):
    return read_snapshot(path, max_bytes=max_bytes, max_work=max_work)[0]
