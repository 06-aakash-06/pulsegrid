"""Non-executing parser for synthetic insurer policy pages."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

from .contracts import InsuranceValidationError, PolicyRule, validate, validate_source_id

MAX_HTML_BYTES = 256 * 1024
POLICY_MARKER = "data-pulsegrid-insurance-policy"


class ExtractionError(ValueError):
    def __init__(self, code: str, message: str = "Synthetic policy page could not be parsed.") -> None:
        super().__init__(message)
        self.code = code


class _PolicyDocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.documents: list[str] = []
        self.links: list[str] = []
        self._capture_policy = False
        self._capture_link = False
        self._policy_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        script_type = values.get("type")
        if tag.lower() == "script" and isinstance(script_type, str) and script_type.lower() == "application/json" and POLICY_MARKER in values:
            if self._capture_policy:
                raise ExtractionError("malformed_policy_markup")
            self._capture_policy = True
            self._policy_chunks = []
        if tag.lower() == "a" and values.get("href") is not None:
            self.links.append(values["href"] or "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Empty policy elements cannot carry a complete JSON document.
        if tag.lower() == "script" and any(name == POLICY_MARKER for name, _ in attrs):
            raise ExtractionError("malformed_policy_markup")
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._capture_policy:
            self._policy_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture_policy:
            self.documents.append("".join(self._policy_chunks))
            self._capture_policy = False
            self._policy_chunks = []

    def close(self) -> None:
        super().close()
        if self._capture_policy:
            raise ExtractionError("malformed_policy_markup")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExtractionError("duplicate_json_field")
        result[key] = value
    return result


def _decode_policy_json(document: str) -> Any:
    try:
        return json.loads(document, object_pairs_hook=_reject_duplicate_json_keys)
    except ExtractionError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ExtractionError("malformed_policy_json") from exc


def extract(html: bytes, source_id: str) -> tuple[PolicyRule, ...]:
    """Extract marked JSON data from HTML without evaluating scripts or markup."""
    if not isinstance(html, bytes) or len(html) > MAX_HTML_BYTES:
        raise ExtractionError("response_too_large")
    if not isinstance(source_id, str) or not source_id:
        raise ExtractionError("invalid_source_id")
    try:
        validate_source_id(source_id)
    except InsuranceValidationError as exc:
        raise ExtractionError("invalid_source_id") from exc
    try:
        document = html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExtractionError("invalid_html_encoding") from exc
    parser = _PolicyDocumentParser()
    try:
        parser.feed(document)
        parser.close()
    except ExtractionError:
        raise
    except Exception as exc:
        # HTMLParser exceptions can contain untrusted snippets; keep only the code.
        raise ExtractionError("malformed_html") from exc

    rules: list[PolicyRule] = []
    for raw_json in parser.documents:
        payload = _decode_policy_json(raw_json)
        candidates = payload if isinstance(payload, list) else [payload]
        if not candidates or len(candidates) > 100:
            raise ExtractionError("empty_policy_document")
        for candidate in candidates:
            try:
                rules.append(validate(candidate))
            except InsuranceValidationError as exc:
                raise ExtractionError(exc.code) from exc
    return tuple(rules)


def extract_links(html: bytes) -> tuple[str, ...]:
    """Return anchor href values for the caller to validate before scheduling."""
    if not isinstance(html, bytes) or len(html) > MAX_HTML_BYTES:
        raise ExtractionError("response_too_large")
    try:
        document = html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ExtractionError("invalid_html_encoding") from exc
    parser = _PolicyDocumentParser()
    try:
        parser.feed(document)
        parser.close()
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("malformed_html") from exc
    return tuple(parser.links)
