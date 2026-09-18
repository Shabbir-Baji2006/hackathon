from __future__ import annotations
import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, Union
from loopkit.schemas import TraceRecord

# Regex patterns for common PII
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
PHONE_PATTERN = re.compile(r'(\+?\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b')
SSN_AADHAAR_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b|\b\d{4}\s\d{4}\s\d{4}\b|\b\d{12}\b')
API_KEY_PATTERN = re.compile(r'(tvly-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,})')

def redact_pii(text: str) -> str:
    """Redacts emails, phone numbers, national IDs, and accidental API keys from text."""
    if not isinstance(text, str):
        return text
    
    redacted = API_KEY_PATTERN.sub("[REDACTED_API_KEY]", text)
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    redacted = SSN_AADHAAR_PATTERN.sub("[REDACTED_ID_NUM]", redacted)
    redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted

def sanitize_data(data: Any) -> Any:
    """Recursively redacts PII from nested dictionaries, lists, or strings."""
    if isinstance(data, str):
        return redact_pii(data)
    elif isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data

class TraceWriter:
    """Writes JSON trace records per step with automatic PII redaction."""

    def __init__(self, output_dir: str = "demo_evidence"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_step(self, trace_record: Union[TraceRecord, Dict[str, Any]], filename: str) -> None:
        """Appends a single JSON trace record as a line to the target trace file."""
        if isinstance(trace_record, TraceRecord):
            record_dict = trace_record.model_dump()
        else:
            record_dict = dict(trace_record)

        # Redact PII before persisting to disk
        sanitized_record = sanitize_data(record_dict)

        file_path = self.output_dir / filename
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sanitized_record, ensure_ascii=False) + "\n")

def cleanup_old_traces(directory: str = "demo_evidence", max_age_days: int = 7) -> int:
    """Deletes trace files in the given directory that are older than max_age_days.
    Returns the number of deleted files.
    """
    target_dir = Path(directory)
    if not target_dir.exists() or not target_dir.is_dir():
        return 0

    deleted_count = 0
    now = time.time()
    cutoff_time = now - (max_age_days * 86400)

    for file_path in target_dir.glob("*.jsonl"):
        try:
            mtime = file_path.stat().st_mtime
            if mtime < cutoff_time:
                file_path.unlink()
                deleted_count += 1
        except OSError:
            pass

    return deleted_count
