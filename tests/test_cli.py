from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_cli(args: list[str], stdin: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(PROJECT_ROOT) if pythonpath is None else f"{PROJECT_ROOT}{os.pathsep}{pythonpath}"
    return subprocess.run(
        [sys.executable, "-m", "jinjitsu", *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd or PROJECT_ROOT,
        env=env,
    )


def test_file_template_merges_context_sources(tmp_path: Path) -> None:
    module_path = tmp_path / "extras.py"
    module_path.write_text(
        """
module_value = "from-module"
_private = "secret"
from_module_only = 42
""".strip()
    )

    vars_path = tmp_path / "vars.json"
    vars_path.write_text('{"module_value": "from-file", "from_file": "file"}')

    includes_dir = tmp_path / "includes"
    includes_dir.mkdir()
    (includes_dir / "partial.txt").write_text("partial={{ extra }}")

    template_path = tmp_path / "template.txt"
    template_path.write_text(
        """
module={{ module_value }}
file={{ from_file }}
private={{ _private }}
from_module_only={{ from_module_only }}
{% include 'partial.txt' %}
""".strip()
    )

    result = run_cli(
        [
            str(template_path),
            "--module",
            str(module_path),
            "--vars",
            str(vars_path),
            "-D",
            "module_value=from-cli",
            "-D",
            "extra=EX",
            "--searchpath",
            str(includes_dir),
        ]
    )

    assert result.returncode == 0, result.stderr
    expected = (
        "module=from-cli\n"
        "file=file\n"
        "private=secret\n"
        "from_module_only=42\n"
        "partial=EX"
    )
    assert result.stdout.strip() == expected


def test_stdin_smart_autoescape_infers_from_output_extension(tmp_path: Path) -> None:
    output_path = tmp_path / "out.html"
    result = run_cli(
        ["--stdin", "-D", "name=<World>", "-o", str(output_path)],
        stdin="{{ name }}",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    rendered = output_path.read_text(encoding="utf-8").strip()
    assert rendered == "&lt;World&gt;"


def test_stdin_smart_autoescape_disables_without_hint(tmp_path: Path) -> None:
    result = run_cli(
        ["--stdin", "-D", "name=<World>"],
        stdin="{{ name }}",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "<World>"


def test_newline_sequence_crlf(tmp_path: Path) -> None:
    output_path = tmp_path / "out.txt"
    result = run_cli(
        [
            "--stdin",
            "--newline-sequence",
            "\\r\\n",
            "--keep-trailing-newline",
            "-o",
            str(output_path),
        ],
        stdin="line1\nline2\n",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.read_bytes() == b"line1\r\nline2\r\n"
