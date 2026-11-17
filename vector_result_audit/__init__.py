"""Independent, offline acceptance checks for dense-vector retrieval results."""
from .audit import VERSION as __version__, audit_snapshot
from .schema import InputError

__all__ = ["__version__", "audit_snapshot", "InputError"]
