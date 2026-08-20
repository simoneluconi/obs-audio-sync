"""Local JSON persistence for AppConfig."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from pydantic import ValidationError

from obs_audio_sync.config.schema import AppConfig

DEFAULT_CONFIG_PATH = Path.home() / ".obs-audio-sync" / "config.json"


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        if not self._path.exists():
            return AppConfig()
        try:
            return AppConfig.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError):
            self._backup_corrupt_file()
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".json.tmp")
        tmp_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp_path, self._path)  # atomic on both POSIX and Windows

    def _backup_corrupt_file(self) -> None:
        backup_path = self._path.with_suffix(".json.corrupt")
        try:
            shutil.copy(self._path, backup_path)
        except OSError:
            pass  # best-effort: don't fail startup just because the backup couldn't be written
