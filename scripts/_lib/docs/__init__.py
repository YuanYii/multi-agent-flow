"""
_lib/docs 向前兼容重定向垫片 (防存量单测断裂)
核心实现已归口至 _lib.discovery.legacy_migrator
"""
from _lib.discovery.legacy_migrator import (
    EXCLUDE_DIRS,
    CATEGORY_KEYWORDS,
    classify_document,
    scan_and_migrate_legacy_docs,
)

__all__ = [
    "EXCLUDE_DIRS",
    "CATEGORY_KEYWORDS",
    "classify_document",
    "scan_and_migrate_legacy_docs",
]
