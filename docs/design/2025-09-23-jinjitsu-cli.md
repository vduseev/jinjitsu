# Jinjitsu CLI — Minimal Template Renderer (Design)

Date: 2025-09-23

## Problem Statement

Design a minimal, robust CLI that renders Jinja templates. It must:

- Load additional Python modules from specified paths and inject their variables (including private names) into the Jinja environment.
- Provide clear, concise error reporting with non-zero exit codes on failure.
- Support reading template content from stdin when `--stdin` is passed (a flag to read from STDIN; it is not a path). Otherwise require a template path and fail if missing.
- Expose core, commonly used Jinja2 Environment configuration options as flags (start minimal; extend on request).
- Offer short, useful examples in `--help`.

Out of scope (v0): packaging/publishing, templating security hardening for untrusted templates, filters/tests/extensions beyond what Jinja provides out of the box.

## Scope (v0)

- Single command binary: `jinjitsu`
- Inputs: template path or `--stdin`; variables from `-D/--var`, from `--vars FILE` (json|yaml|ini|toml), and from `-m/--module` files.
- Output: rendered template to stdout or to `--output` file when provided.
- No network or external stores.

## Architecture

- CLI entry (argparse): parses flags and validates invariants (either `--stdin` or `TEMPLATE`, not both; at least one present; modules paths exist).
- Module loader: imports each `--module` file via `importlib.util.spec_from_file_location()` and returns a `dict` of variables.
  - Export rule: export ALL names (including those starting with `_`). This works with the standard `Environment`; underscores are only restricted under `SandboxedEnvironment` (out of scope for v0).
  - Value rule: export any Python object as-is (callables are allowed; Jinja will call as needed).
- Vars file loader: for each `--vars FILE`, parse based on extension:
  - `.json` → `json.loads`
  - `.yaml`/`.yml` → `yaml.safe_load` if `PyYAML` is installed, else `ruamel.yaml.YAML(typ='safe').load` if `ruamel.yaml` is installed; otherwise error with guidance to install one.
  - `.toml` → `tomllib.loads` (Python 3.11+). If unavailable, try `tomli`/`toml` if present; else error.
  - `.ini` → `configparser`. Convert to a nested mapping of sections to dict; include the `[DEFAULT]` section under the key `DEFAULT`.
  - In all cases, the parsed root must be a mapping/dict; otherwise error.
- Context assembly: merge dicts in precedence order (lowest → highest):
  1) module variables (in given order),
  2) `--vars` files (in given order),
  3) `-D/--var` pairs (last wins).
- Jinja environment factory: builds `jinja2.Environment` with selected flags (below). Loader choice and autoescape behavior:
  - Autoescape default: smart (extension-based) to reduce user hassle.
  - File input: `FileSystemLoader(searchpath=[template_dir, *--searchpath])` and `autoescape=select_autoescape(DEFAULT_HTML_EXTS)`.
  - Stdin input: use `ChoiceLoader([DictLoader, FileSystemLoader])` where the stdin template is injected via `DictLoader` under a synthetic name. If `--output` has an extension in `DEFAULT_HTML_EXTS`, use that extension for the synthetic name (e.g., `__stdin__.html`) so smart autoescape applies; otherwise use `.txt`.
- Render step:
  - File input: `env.get_template(template_name).render(context)`.
  - Stdin input: inject source as `__stdin__<ext>` into `DictLoader` and call `env.get_template("__stdin__<ext>").render(context)`.
- Output: write to stdout by default; if `--output PATH` is provided, write the rendered bytes to that file (create parent directories if missing).

## Data Flow

Args → validate → load modules → load vars files → merge context → build Environment (smart autoescape) → load template → render → stdout|file

## CLI Flags (v0)

- Template source
  - `TEMPLATE` (positional): path to a template file. Required unless `--stdin` is set.
  - `--stdin`: read template from stdin/heredoc. Mutually exclusive with `TEMPLATE`.
  - `--searchpath PATH` (repeatable): extra directories for includes/imports.

- Variables / modules
  - `-D`, `--var KEY=VALUE` (repeatable): inject simple key/value pairs (strings). Duplicate keys override earlier values.
  - `-m`, `--module PATH` (repeatable): import a Python module by file path and inject its exported variables.
  - `--vars FILE` (repeatable): load variables from FILE. Supported by extension: `.json`, `.yaml`/`.yml`, `.ini`, `.toml`.

- Jinja2 environment (minimal, commonly used subset)
  - Whitespace: `--trim-blocks` (bool), `--lstrip-blocks` (bool), `--keep-trailing-newline` (bool), `--newline-sequence {\n,\r\n,\r}` (default `\n`).
  - Autoescape: `--autoescape {smart,on,off}` (default `smart`).
    - `smart`: use `select_autoescape(DEFAULT_HTML_EXTS)`; for stdin, infer from `--output` extension if present, else no autoescape.
    - `on`: force autoescape.
    - `off`: disable autoescape.
    - `--autoescape-exts EXT,EXT` (optional): override `DEFAULT_HTML_EXTS` (default: `html,htm,xml,xhtml`).
  - Undefined handling: `--undefined {strict,default,debug,chain}` (default `strict`).
  - Reload/cache: `--auto-reload` (bool), `--cache-size N` (int; `0` disables caching, `-1` unlimited).
  - Async: `--enable-async` (bool; default `false`).

- Output
  - `-o, --output PATH`: write rendered output to PATH. Use `-` (dash) for stdout (default). Will overwrite if exists.

Notes
- Defaults align with Jinja’s defaults unless specified. Notable deviations for CLI usability: `--autoescape` defaults to `smart`; `--undefined` defaults to `strict`.
- Advanced knobs (custom delimiters, extensions list, bytecode cache, finalize, loader variants) can be added later to keep v0 lean.

## Error Handling

- Exit codes: `0` success; `2` CLI usage/validation; `3` import/module errors; `4` template loading; `5` rendering; `6` vars file parsing; `7` output write failures.
- Reporting: concise single-line summary on stderr; for render/import errors add the exception type and message.
- Tracebacks: hidden by default; show full stack when `--traceback` is passed. Where available, include filename and line numbers from Jinja exceptions.
- Input validation examples:
  - Missing source: if neither `TEMPLATE` nor `--stdin` → error `2`: "template path required; or pass --stdin".
  - Both provided: error `2`: "use either TEMPLATE or --stdin, not both".
  - Module path not found or import error: error `3` with path and underlying exception message.
  - Vars file parse error or unsupported format: error `6` with file path and hint (e.g., install `pyyaml`/`ruamel.yaml`).
  - Output file write error (permissions or other IO issues): error `7` with OS error message.

## `--help` Examples (concise)

```
# Render a file with a variable
jinjitsu template.j2 -D name=World

# Read from heredoc (stdin) and render
jinjitsu --stdin -D who=Universe << 'EOF'
Hello {{ who }}!
EOF

# Load variables from a Python module
jinjitsu template.j2 -m ./vars.py

# Load variables from JSON/YAML/TOML/INI files
jinjitsu template.j2 --vars data.json --vars settings.yaml

# Fail on undefined variables and trim whitespace
jinjitsu template.j2 --undefined strict --trim-blocks --lstrip-blocks

# Autoescape is smart by default for HTML/XML-like templates
jinjitsu page.html.j2 -D title=Hi

# Force autoescape off (e.g., when rendering raw text)
jinjitsu notes.txt.j2 --autoescape off -D body=Hello

# Use stdin with includes by adding a search path
jinjitsu --stdin --searchpath templates <<'J2'
{% include 'partial.j2' %}
J2

# Write output to a file
jinjitsu template.j2 -D name=World --output out.txt
```

## Implementation Notes

- Library: `jinja2>=3.1`.
- Arg parsing: `argparse` for zero-dependency CLI, with a mutually exclusive group for `TEMPLATE` vs `--stdin`.
- Module import: `importlib.util` with per-file module names derived from absolute paths; never added to `sys.modules` under a common name.
- Logging: minimal; write user-facing errors to stderr, not stdout.
 - Smart autoescape implementation:
   - File templates: `Environment(autoescape=select_autoescape(DEFAULT_HTML_EXTS))`.
   - Stdin templates: `ChoiceLoader([DictLoader({'__stdin__<ext>': source}), FileSystemLoader([...])])` where `<ext>` is derived from `--output` extension if present; otherwise `.txt`.
   - `DEFAULT_HTML_EXTS = ('html','htm','xml','xhtml')`.

## CLI Help Texts

Goal: keep help concise and friendly to users with little or no Jinja knowledge. Explain options plainly and group common flags first.

Proposed `--help` structure

```
Usage: jinjitsu [OPTIONS] [TEMPLATE]

Render a Jinja template to stdout (or a file).

Source (choose one)
  TEMPLATE                  Path to a template file.
  --stdin                   Read template from STDIN (heredoc/pipe).

Variables
  -D, --var KEY=VALUE       Set a string variable (can repeat). Highest precedence.
  --vars FILE               Load variables from FILE (json|yaml|toml|ini). Top-level must be a mapping.
                            YAML needs PyYAML or ruamel.yaml installed.
  -m, --module PATH         Import Python file; its top-level names become available as variables.

Template search paths
  --searchpath PATH         Add a directory to look for included/imported templates (can repeat).

Jinja behavior
  --autoescape {smart,on,off}
                            HTML/XML escaping. smart (default) chooses by file extension; on always;
                            off never. For --stdin, smart uses the --output extension when set.
  --autoescape-exts EXT,EXT Override extensions used by smart autoescape (default: html,htm,xml,xhtml).
  --undefined {strict,default,debug,chain}
                            How to handle missing variables. strict (default) errors; default renders
                            empty string; debug shows a debug placeholder; chain allows advanced chaining.
  --trim-blocks             Strip the first newline after a block.
  --lstrip-blocks           Strip leading spaces and tabs from the start of a line to a block.
  --keep-trailing-newline   Keep a single trailing newline at the end of the output.
  --newline-sequence {\n,\r\n,\r}
                            Newline characters to use in output (default: \n).
  --auto-reload             Reload templates when files change (useful during development).
  --cache-size N            Template cache size (0 disables, -1 unlimited).
  --enable-async            Enable async templates/filters.

Output and diagnostics
  -o, --output PATH         Write output to PATH (use - for stdout). Overwrites if exists.
  --traceback               Show full Python tracebacks on errors.

Notes
  Precedence: --var > --vars files > --module.
  Examples: see below or docs.
```

## Future Extensions (post‑v0)

- `--extensions` to enable Jinja extensions; `--finalize` as dotted path.
- Custom delimiters flags (block/variable/comment start/end).
- Bytecode cache (`--bytecode-cache DIR`).
- `--fail-missing-includes`.

## Unknowns / Questions

1. Include search path defaults for `--stdin`: current design uses `cwd` plus any `--searchpath`. OK?

Please review and I will iterate.
