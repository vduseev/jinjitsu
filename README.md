<h1><code>jinjitsu</code></h1>

Minimal Jinja CLI for rendering templates from files or stdin with variables, config files, and Python modules.
Fast, predictable way to render Jinja2 templates from the terminal.

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/jinjitsu)
![PyPI - Status](https://img.shields.io/pypi/status/jinjitsu)
![PyPI - License](https://img.shields.io/pypi/l/jinjitsu)

[Installation](#installation) • [Quick Start](#quick-start) • [CLI](#cli) • [Examples](#examples) • [Troubleshooting](#troubleshooting) • [Contributing](#contributing) • [License](#license)

## Quick Start

* Hello world:

  ```shell
  $ echo "Hello {{ name }}" | jinjitsu --stdin -D name=World
  Hello World
  ```

* Render a template with includes from a different directory

  `docs/README.j2.md`:

  ````markdown
  # Dynamically rendered README

  ```ts
  {% include 'code.ts' %}
  ```
   ````

  `examples/code.ts`:

  ```ts
  export const greeting = "Hello, User";
  ```

  Now, **rendering it** with `jinjitsu` and adding `examples` as
  a `--searchpath` will produce the following **result**:

  ````
  $ jinjitsu docs/README.j2.md -s examples/
  # Dynamically rendered README

  ```ts
  export const greeting = "Hello, User";
  ```
  ````

  Or render it directly to a file by redirecting `>` the output or using the `-o` option:

  ```shell
  # Like so
  $ jinjitsu docs/README.j2.md -s examples/ -o README.md

  # Or like so
  $ jinjitsu docs/README.j2.md -s examples/ > README.md
  ```

* Autoescape HTML and feed template as a Heredoc (`<<EOF`)

  ```shell
  $ jinjitsu --stdin -D name='<World>' --autoescape on <<EOF        
  Hello {{ name }}
  EOF
  Hello &lt;World&gt;
  ```

## CLI

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

## Installation

Run using `uv` without needing to install anything:

```shell
uvx jinjitsu
```

Or install as a system-wide tool:

```shell
# Using uv
uv tool install jinjitsu

# Using pipx
pipx install jinjitsu
```

Of course, you can also install as a package in the current virtual environment:

```shell
./.venv/bin/activate && pip install jinjitsu
```

## Examples

Let's consider an example with dynamically generated release notes.
We want to render a template that uses a function from a Python module,
includes a reusable sub-template, and uses variables from a vars file and the CLI.

```bash
# First, let's create a Python module with a two functions and a private variable
$ cat > extras.py <<'PY'
from datetime import datetime

def greet(name: str) -> str:
    """Greet someone."""
    return f"Greetings, {name}!"

def today() -> str:
    """Return today's date."""
    return datetime.now().strftime('%Y-%m-%d')

_private_variable = "visible"
PY

# Then, we create a vars.json file with additional variables
$ echo '{ "changelog": "CHANGELOG.md" }' > vars.json

# Let's also create a reusable template in the "shared" directory
$ mkdir -p shared && echo 'Release type: {{ type }}' > shared/type.j2

# Finally, let's define the main template
$ cat > deployment_summary.j2 <<'J2'
Deployment summary {{ today() }}

* {% include 'type.j2' %}
* Changelog: {{ changelog }}
* Status: {{ _private_variable }}
J2

# Now, render the template with jinjitsu
$ jinjitsu deployment_summary.j2 \
  --module extras.py \
  --vars vars.json \
  -D type=PROD \
  --searchpath shared
```

Expected output:

```
Deployment summary 2023-04-10

* Release type: PROD
* Changelog: CHANGELOG.md
* Status: visible
```

## Configuration & Notes

* Variable precedence:
  * Later sources override earlier ones
  * `-D/--var` flags override `--vars` files, which override `-m/--modules`.
* Include/import search order:
  * template’s directory;
  * for `--stdin`, falls back to the current working directory;
  * always adds all provided `-s/--searchpath` directories to the above.

## Troubleshooting

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

## Contributing

Pull requests and issues are welcome.

## License

Apache 2.0. See `LICENSE`.
