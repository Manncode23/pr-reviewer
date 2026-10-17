"""Run external command-line tools safely (no shell, with a timeout)."""

import subprocess


class ToolRunError(Exception):
    """Raised when an external tool can't be run or times out."""


def run_cli(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a command and capture its output.

    The return code is NOT checked: linters exit non-zero when they find
    issues, which is normal for us.
    """
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolRunError(f"Tool timed out after {timeout}s: {args[:4]}") from exc
    except FileNotFoundError as exc:
        raise ToolRunError(f"Executable not found: {args[0]}") from exc