"""T2801 — dbt runner (subprocess wrapper)."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("waibao.warehouse.dbt")


@dataclass
class DbtConfig:
    project_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("DBT_PROJECT_DIR", "/app/services/warehouse/dbt")
        )
    )
    profiles_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("DBT_PROFILES_DIR", "/app/services/warehouse/dbt")
        )
    )
    target: str = field(default_factory=lambda: os.getenv("DBT_TARGET", "prod"))
    binary: str = field(default_factory=lambda: os.getenv("DBT_BINARY", "dbt"))
    timeout_s: int = 1800  # 30 min

    def cmd_prefix(self) -> list[str]:
        return [self.binary, "--profiles-dir", str(self.profiles_dir), "--target", self.target]


class DbtRunner:
    """dbt CLI wrapper.  同步阻塞, 由 scheduler 在线程里调."""

    def __init__(self, config: Optional[DbtConfig] = None) -> None:
        self.config = config or DbtConfig()
        self._lock = threading.Lock()

    def run(self, select: Optional[str] = None, full_refresh: bool = False) -> dict[str, object]:
        cmd = self.config.cmd_prefix() + ["run", "--project-dir", str(self.config.project_dir)]
        if select:
            cmd += ["--select", select]
        if full_refresh:
            cmd += ["--full-refresh"]
        return self._exec(cmd)

    def test(self, select: Optional[str] = None) -> dict[str, object]:
        cmd = self.config.cmd_prefix() + ["test", "--project-dir", str(self.config.project_dir)]
        if select:
            cmd += ["--select", select]
        return self._exec(cmd)

    def build(self, select: Optional[str] = None) -> dict[str, object]:
        cmd = self.config.cmd_prefix() + ["build", "--project-dir", str(self.config.project_dir)]
        if select:
            cmd += ["--select", select]
        return self._exec(cmd)

    def deps(self) -> dict[str, object]:
        cmd = self.config.cmd_prefix() + ["deps", "--project-dir", str(self.config.project_dir)]
        return self._exec(cmd)

    def _exec(self, cmd: list[str]) -> dict[str, object]:
        with self._lock:
            logger.info("Running: %s", " ".join(cmd))
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=self.config.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_s,
                )
            except subprocess.TimeoutExpired as e:
                return {"ok": False, "error": "timeout", "stdout": e.stdout or ""}
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
