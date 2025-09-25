# jinjitsu

Minimal Jinja CLI for rendering templates from files or stdin with variables from CLI flags, config files, and Python modules. Built for people who want a fast, predictable way to render Jinja2 templates from the terminal.

Installation • Quick Start • Examples • Docs • Troubleshooting • Contributing • License

## Why jinjitsu?

- Render Jinja from the CLI: point at a file or use `--stdin`.
- Combine variables from multiple sources with clear precedence: `--module` → `--vars` → `-D` (last wins).
- “Smart” autoescape by extension for HTML/XML; off for plain text unless hinted.
- Includes/imports that just work via `--searchpath` directories.
- Control whitespace and newlines (`--trim-blocks`, `--lstrip-blocks`, `--newline-sequence`).
- Helpful errors and non‑zero exit codes; show `--traceback` when you need it.

## Compatibility

- Runtime: Python `>=3.13`.
- OS: Linux, macOS, Windows (anywhere Python runs).
- Dependencies: `jinja2>=3.1.6`.
- Optional: YAML (`PyYAML` or `ruamel.yaml`), TOML (`tomllib` on 3.11+, else `tomli`/`toml`).

## Installation

One‑liner (local clone or checkout):

```bash
pipx install .
```

Notes
- If you prefer a virtualenv: `python -m venv .venv && . .venv/bin/activate && pip install -e .`.
- When published to a registry, use: `pipx install jinjitsu` or `pip install -U jinjitsu`.

## Quick Start

Hello world from stdin:

```bash
echo "Hello {{ name }}" | jinjitsu --stdin -D name=World
```

Expected output:

```
Hello World
```

Autoescape by output extension (HTML):

```bash
echo "{{ name }}" | jinjitsu --stdin -D name='<World>' -o out.html && cat out.html
```

Expected output:

```
&lt;World&gt;
```

## Examples

Render a file with variables from a Python module, a vars file, and the CLI; also set an include path:

```bash
# extras.py exports variables (functions/values); all top‑level names are exposed
cat > extras.py <<'PY'
def greet(who):
    return f"hi, {who}!"
_private = "visible"
PY

# vars.json provides additional context
echo '{"from_file": "file"}' > vars.json

# includes/partial.txt will be used via {% include %}
mkdir -p includes && echo 'partial={{ extra }}' > includes/partial.txt

cat > template.txt <<'J2'
module={{ greet('world') }}
file={{ from_file }}
private={{ _private }}
{% include 'partial.txt' %}
J2

jinjitsu template.txt \
  --module extras.py \
  --vars vars.json \
  -D extra=EX \
  --searchpath includes
```

Expected output:

```
module=hi, world!
file=file
private=visible
partial=EX
```

More real‑world scenarios live in tests and design docs:
- tests: `tests/test_cli.py`
- docs: `docs/design/2025-09-23-jinjitsu-cli.md`

## CLI Overview

```text
Usage: jinjitsu [OPTIONS] [TEMPLATE]

Render a Jinja template.

Source (choose one)
  TEMPLATE                  Path to a template file.
  --stdin                   Read template from STDIN (heredoc/pipe).

Variables
  -D, --var KEY=VALUE       Set a string variable (repeatable). Highest precedence.
  --vars FILE               Load variables from FILE [json|yaml|toml|ini] (repeatable).
  -m, --module PATH         Import Python file; its top‑level names become variables (repeatable).

Template search paths
  --searchpath PATH         Add a directory for includes/imports (repeatable).

Jinja behavior
  --autoescape {smart,on,off}   Default smart (by extension).
  --autoescape-exts EXT,EXT     Override smart extensions (default: html,htm,xml,xhtml).
  --undefined {strict,default,debug,chain}   Missing variables policy (default: strict).
  --trim-blocks, --lstrip-blocks, --keep-trailing-newline
  --newline-sequence {\n,\r\n,\r}

Output and diagnostics
  -o, --output PATH         Write output to PATH (use - for stdout).
  --traceback               Show full Python tracebacks on errors.
```

## Configuration & Notes

- Precedence: later sources override earlier ones → modules < `--vars` files < `-D/--var`.
- `--stdin` infers autoescape from `--output` extension when provided; otherwise renders as plain text.
- Include/import search order: template’s directory (for file templates) followed by each `--searchpath` in order; for `--stdin`, falls back to the current working directory if no paths given.

## Troubleshooting / FAQ

- “YAML file not supported” or similar
  - Install a YAML parser: `pip install PyYAML` (or `ruamel.yaml`).

- “Unsupported vars file type …”
  - Only `.json`, `.yaml`/`.yml`, `.toml`, `.ini` are supported.

- “Template not found” or includes fail
  - Check the path and add directories with `--searchpath PATH`.

- “UndefinedError” or missing variables
  - Default mode is strict. Provide values via `-D/--var`, `--vars FILE`, or `--module`; or use `--undefined default`.

- Newline/whitespace looks wrong
  - Try `--trim-blocks`, `--lstrip-blocks`, and set `--newline-sequence`. Use `--keep-trailing-newline` to preserve a single trailing newline.

- I need a Python traceback
  - Add `--traceback` for full tracebacks on errors.

## Roadmap / Status

- Version: `0.1.0` (early stage, minimal scope). Future ideas include Jinja extensions toggles and additional CLI switches as demand emerges.

## Contributing

Pull requests and issues are welcome.

Developer setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e . pytest ruff ty
pytest -q
ruff check .
```

## Security

- jinjitsu does not sandbox templates. Do not render untrusted templates or modules.
- Report security issues privately to the maintainer: `vagiz@duseev.com`.

## License

Apache 2.0. See `LICENSE`.
