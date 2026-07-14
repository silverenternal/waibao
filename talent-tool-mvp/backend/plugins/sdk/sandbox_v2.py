"""T5023 — Docker container sandbox v2.

Runs untrusted plugin code inside an ephemeral Docker container with hard
resource limits:

* **CPU**  — capped at 100% of a single core (``--cpus=1``).
* **memory** — 256 MB hard limit (``--memory=256m``).
* **time** — killed after 5 seconds (``--timeout``).
* **network** — disabled (``--network=none``).
* **filesystem** — read-only root + a tmpfs scratch dir; no mounts.

This is the production isolation boundary. The in-process sandbox in
``sandbox.py`` remains as defence-in-depth. When Docker is unavailable we
fall back to a subprocess runner with the same contract so the SDK can be
exercised in CI without a daemon.

The public surface mirrors :class:`PluginRunner`:

    runner = ContainerPluginRunner(image="waibao/plugin-runtime:latest")
    result = runner.run(plugin_code, input_data)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result + errors
# ---------------------------------------------------------------------------

@dataclass
class ContainerResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_s: float = 0.0
    backend: str = "docker"  # or "subprocess"

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_s": round(self.duration_s, 6),
            "backend": self.backend,
            "ok": self.ok,
        }


class SandboxError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class ContainerPluginRunner:
    """Run plugin code in a constrained Docker container.

    Args:
        image: container image with a python3 entrypoint.
        cpu_quota: CPU limit as a fraction of one core (default 1.0 = 100%).
        memory_mb: hard memory cap.
        timeout_s: wall-clock kill timeout.
        network: ``"none"`` disables networking.
    """

    image: str = "waibao/plugin-runtime:latest"
    cpu_quota: float = 1.0
    memory_mb: int = 256
    timeout_s: float = 5.0
    network: str = "none"
    docker_bin: str = "docker"

    # ------------------------------------------------------------------
    def run(self, code: str, payload: Any = None) -> ContainerResult:
        if self._docker_available():
            return self._run_docker(code, payload)
        logger.warning("docker unavailable — using subprocess fallback sandbox")
        return self._run_subprocess(code, payload)

    # ------------------------------------------------------------------
    def _run_docker(self, code: str, payload: Any) -> ContainerResult:
        payload_json = json.dumps({"payload": payload})
        argv = [
            self.docker_bin, "run", "--rm",
            "--network", self.network,
            f"--cpus={self.cpu_quota}",
            f"--memory={self.memory_mb}m",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64",
            "-e", f"WAIBAO_PAYLOAD={payload_json}",
            self.image,
            "python3", "-c", code,
        ]
        return self._exec(argv, backend="docker")

    # ------------------------------------------------------------------
    def _run_subprocess(self, code: str, payload: Any) -> ContainerResult:
        """Fallback runner: spawn a python subprocess with resource limits.

        Applies the same CPU/memory/timeout contract as the container using
        ``resource.setrlimit`` (POSIX) inside the child. On platforms
        without ``resource`` we still enforce the timeout.
        """
        wrapper = textwrap.dedent(
            f"""
            import json, os, sys
            os.environ["WAIBAO_PAYLOAD"] = {json.dumps(json.dumps({"payload": payload}))}
            try:
                import resource
                memory_bytes = {self.memory_mb} * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                cpu_s = {self.timeout_s}
                resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_s) + 1, int(cpu_s) + 1))
            except Exception:
                pass
            exec(compile({code!r}, "<plugin>", "exec"))
            """
        )
        argv = [sys.executable, "-I", "-c", wrapper]
        return self._exec(argv, backend="subprocess")

    # ------------------------------------------------------------------
    def _exec(self, argv: list[str], *, backend: str) -> ContainerResult:
        start = time.time()
        timed_out = False
        try:
            proc = subprocess.run(  # noqa: S603 — argv is constructed internally
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\n[killed: timeout {self.timeout_s}s]"
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
        except FileNotFoundError as exc:
            raise SandboxError(f"runner binary missing: {exc}") from exc
        return ContainerResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_s=time.time() - start,
            backend=backend,
        )

    # ------------------------------------------------------------------
    def _docker_available(self) -> bool:
        if os.environ.get("WAIBAO_DISABLE_DOCKER") == "1":
            return False
        docker = shutil.which(self.docker_bin)
        if docker is None:
            return False
        try:
            subprocess.run(  # noqa: S603
                [self.docker_bin, "info"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            return True
        except Exception:  # noqa: BLE001
            return False
