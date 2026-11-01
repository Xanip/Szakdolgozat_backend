"""JSON reading and atomic writing for the result documents."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PREDICTIONS_FILENAME = "AllPredictionTestsData.json"
SUMMARY_FILENAME = "SummaryTestsData.json"
BEST_MODEL_FILENAME = "BestModelData.json"
NOT_IN_TESTS_FILENAME = "NotInTests.json"
REPORT_FILENAME = "PredictionAnalysisReport.md"


class JsonDocumentError(ValueError):
	"""Raised for unreadable or structurally invalid result documents."""


def _require_document(document: Any, name: str) -> dict[str, Any]:
	if not isinstance(document, dict):
		raise JsonDocumentError(f"{name} must contain a JSON object")
	for key in ("metadata", "results"):
		if not isinstance(document.get(key, {}), dict):
			raise JsonDocumentError(f"{name}.{key} must be an object")
	return document


def load_json(path: Path, required: bool = False) -> dict[str, Any]:
	"""Load a result document.

	A missing file yields an empty document, unless ``required`` is set.
	"""
	if not path.exists():
		if required:
			raise JsonDocumentError(f"Input file does not exist: {path}")
		return {"metadata": {}, "results": {}}
	try:
		with path.open("r", encoding="utf-8") as file:
			document = json.load(file)
	except json.JSONDecodeError as exc:
		raise JsonDocumentError(f"Invalid JSON in {path}: {exc}") from exc
	return _require_document(document, path.name)


def write_json_atomic(path: Path, document: Mapping[str, Any]) -> None:
	"""Write to a temp file in the same folder, then replace the target."""
	path.parent.mkdir(parents=True, exist_ok=True)
	serialized = json.dumps(
		_require_document(dict(document), path.name),
		ensure_ascii=False,
		indent=2,
		allow_nan=False,
	)
	temporary_path: str | None = None
	try:
		with tempfile.NamedTemporaryFile(
			mode="w",
			encoding="utf-8",
			dir=path.parent,
			prefix=f".{path.name}.",
			suffix=".tmp",
			delete=False,
		) as temporary_file:
			temporary_path = temporary_file.name
			temporary_file.write(serialized)
			temporary_file.flush()
			os.fsync(temporary_file.fileno())
		os.replace(temporary_path, path)
	finally:
		if temporary_path is not None and os.path.exists(temporary_path):
			os.unlink(temporary_path)
