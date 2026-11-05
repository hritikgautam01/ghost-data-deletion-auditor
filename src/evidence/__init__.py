"""
Evidence extraction and forensics package for Ghost Data Still Exists.
"""

from .manifest import EvidenceManifest
from .json_extractor import (
    ExtractedEvidenceRecord,
    JSONExtractionResult,
    extract_all_records,
    extract_eligible_json,
    extract_from_file,
)
from .log_parser import (
    LogExtractionResult,
    extract_all_log_records,
    extract_eligible_logs_and_text,
    extract_identifiers_from_payload,
    extract_log_records_from_file,
    parse_handover_line,
    parse_key_value_pairs,
    parse_log_line,
)

from .sql_engine import (
    SQLExtractionResult,
    extract_all_sql_records,
    extract_eligible_sql,
    extract_identifiers_from_row,
    extract_sql_records_from_file,
    get_table_names,
    is_sqlite_binary_file,
)

from .doc_extractor import (
    DocExtractionResult,
    extract_all_doc_records,
    extract_doc_records_from_file,
    extract_eligible_docs_and_images,
    extract_text_from_pdf_bytes,
)

__all__ = [
    "EvidenceManifest",
    "ExtractedEvidenceRecord",
    "JSONExtractionResult",
    "LogExtractionResult",
    "SQLExtractionResult",
    "DocExtractionResult",
    "extract_from_file",
    "extract_eligible_json",
    "extract_all_records",
    "extract_log_records_from_file",
    "extract_eligible_logs_and_text",
    "extract_all_log_records",
    "extract_sql_records_from_file",
    "extract_eligible_sql",
    "extract_all_sql_records",
    "extract_doc_records_from_file",
    "extract_eligible_docs_and_images",
    "extract_all_doc_records",
    "extract_text_from_pdf_bytes",
    "is_sqlite_binary_file",
    "extract_identifiers_from_row",
    "get_table_names",
    "parse_key_value_pairs",
    "parse_log_line",
    "parse_handover_line",
    "extract_identifiers_from_payload",
]
