from __future__ import annotations

import argparse
import configparser
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping, Sequence

from jinja2 import (
    ChainableUndefined,
    ChoiceLoader,
    DebugUndefined,
    DictLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Undefined,
    select_autoescape,
)

DEFAULT_AUTOESCAPE_EXTS: tuple[str, ...] = ("html", "htm", "xml", "xhtml")
STDIN_TEMPLATE_BASENAME = "__stdin__"
_NEWLINE_TOKENS: dict[str, str] = {
    "\\n": "\n",
    "\\r\\n": "\r\n",
    "\\r": "\r",
    "LF": "\n",
    "CRLF": "\r\n",
    "CR": "\r",
    "lf": "\n",
    "crlf": "\r\n",
    "cr": "\r",
    "\n": "\n",
    "\r\n": "\r\n",
    "\r": "\r",
}


class CLIError(Exception):
    """Raised when CLI invariants are violated."""


__all__ = ["main", "run", "execute"]


def build_parser() -> argparse.ArgumentParser:
    description = "Render a Jinja template."
    examples = """\
Examples:
  jinjitsu template.j2 -D name=World
  jinjitsu --stdin -D user=alice < template.j2
  cat ../template.j2 | jinjitsu --stdin -s ../includes
  jinjitsu emails/welcome.html --vars vars.yaml -m extras.py -o out.html
"""
    parser = argparse.ArgumentParser(
        prog="jinjitsu",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=examples,
    )

    source_group = parser.add_argument_group("Source (choose one)")
    source_group.add_argument(
        "template",
        nargs="?",
        help="Path to a template file.",
    )
    source_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read template from STDIN (heredoc/pipe).",
    )

    vars_group = parser.add_argument_group("Variables")
    vars_group.add_argument(
        "-D",
        "--var",
        dest="cli_vars",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set a string variable (can repeat). Highest precedence.",
    )
    vars_group.add_argument(
        "--vars",
        dest="vars_files",
        action="append",
        default=[],
        metavar="FILE",
        help="Load variables from FILE [json|yaml|toml|ini] (can repeat). Top-level must be a mapping.",
    )
    vars_group.add_argument(
        "-m",
        "--module",
        dest="modules",
        action="append",
        default=[],
        metavar="PATH",
        help="Import Python file; its top-level names become available as variables (can repeat).",
    )

    parser.add_argument(
        "-s",
        "--searchpath",
        action="append",
        default=[],
        metavar="PATH",
        help="Add a directory to look for included/imported templates (can repeat). Always includes template's directory. Defaults to cwd when --stdin is used.",
    )

    behavior_group = parser.add_argument_group("Jinja behavior")
    behavior_group.add_argument(
        "--autoescape",
        choices=("smart", "on", "off"),
        default="smart",
        help="HTML/XML escaping policy. smart (default) chooses by extension; on always; off never.",
    )
    behavior_group.add_argument(
        "--autoescape-exts",
        metavar="EXT,EXT",
        help="Override extensions used by smart autoescape (default: html,htm,xml,xhtml).",
    )
    behavior_group.add_argument(
        "--undefined",
        choices=("strict", "default", "debug", "chain"),
        default="strict",
        help="How to handle missing variables.",
    )
    behavior_group.add_argument(
        "--trim-blocks",
        action="store_true",
        help="Strip the first newline after a block.",
    )
    behavior_group.add_argument(
        "--lstrip-blocks",
        action="store_true",
        help="Strip leading spaces/tabs from the start of a line to a block.",
    )
    behavior_group.add_argument(
        "--keep-trailing-newline",
        action="store_true",
        help="Keep a single trailing newline at the end of the output.",
    )
    behavior_group.add_argument(
        "--newline-sequence",
        default="\\n",
        metavar="{\\n,\\r\\n,\\r}",
        help=(
            "Newline characters to use in output (default: \\n). Pass escaped strings such as"
            " --newline-sequence '\\n' or --newline-sequence '\\r\\n'. On POSIX shells you can also"
            " use $'\\r\\n' to avoid literal backslashes."
        ),
    )

    output_group = parser.add_argument_group("Output and diagnostics")
    output_group.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Write output to PATH. Existing files will be overwritten.",
    )
    output_group.add_argument(
        "--traceback",
        action="store_true",
        help="Show full Python tracebacks on errors.",
    )

    return parser


def parse_key_value(pair: str) -> tuple[str, str]:
    key, sep, value = pair.partition("=")
    if not sep:
        raise CLIError(f"Expected KEY=VALUE for --var, got: {pair!r}")
    if not key:
        raise CLIError("Variable key cannot be empty.")
    return key, value


def parse_autoescape_exts(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_AUTOESCAPE_EXTS
    parts = [segment.strip().lower() for segment in raw.split(",") if segment.strip()]
    if not parts:
        raise CLIError("--autoescape-exts requires at least one extension.")
    return tuple(parts)


def parse_newline_sequence(value: str) -> str:
    if value in _NEWLINE_TOKENS:
        return _NEWLINE_TOKENS[value]
    raise CLIError("--newline-sequence accepts one of \\n, \\r\\n, or \\r (also CR/LF/CRLF).")


def ensure_existing_file(path: Path, kind: str) -> None:
    if not path.exists():
        raise CLIError(f"{kind} not found: {path}")
    if path.is_dir():
        raise CLIError(f"{kind} must be a file: {path}")


def ensure_existing_directory(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise CLIError(f"Search path must be an existing directory: {path}")


def load_module_variables(paths: Sequence[str]) -> list[Dict[str, Any]]:
    variables: list[Dict[str, Any]] = []
    for index, raw_path in enumerate(paths):
        module_path = Path(raw_path).expanduser()
        ensure_existing_file(module_path, "Module")
        module_name = f"_jinjitsu_module_{index}_{module_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise CLIError(f"Unable to import module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            raise CLIError(f"Failed to load module {module_path}: {exc}") from exc
        variables.append(dict(module.__dict__))
    return variables


def _load_yaml(text: str, path: Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover
        yaml = None

    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        try:
            from ruamel.yaml import YAML  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise CLIError(
                f"YAML support requires PyYAML or ruamel.yaml (needed for {path})."
            ) from exc
        loader = YAML(typ="safe")
        data = loader.load(text)
    return data


def _load_toml(text: str, path: Path) -> Mapping[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None

    if tomllib is not None:
        return tomllib.loads(text)

    for module_name in ("tomli", "toml"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        try:
            return module.loads(text)
        except AttributeError as exc:  # pragma: no cover
            raise CLIError(
                f"{module_name} does not expose loads(); cannot parse toml file {path}."
            ) from exc

    raise CLIError(
        f"TOML support requires Python 3.11+'s tomllib or tomli/toml packages (needed for {path})."
    )


def _load_ini(text: str) -> Mapping[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read_string(text)
    data: dict[str, dict[str, str]] = {"DEFAULT": dict(parser.defaults())}
    for section in parser.sections():
        data[section] = dict(parser.items(section))
    return data


def load_vars_file(path: str) -> Dict[str, Any]:
    file_path = Path(path).expanduser()
    ensure_existing_file(file_path, "Vars file")
    text = file_path.read_text(encoding="utf-8")
    ext = file_path.suffix.lower()
    if ext == ".json":
        data = json.loads(text)
    elif ext in {".yaml", ".yml"}:
        data = _load_yaml(text, file_path)
    elif ext == ".toml":
        data = _load_toml(text, file_path)
    elif ext == ".ini":
        data = _load_ini(text)
    else:
        raise CLIError(f"Unsupported vars file type for {file_path}.")

    if data is None:
        raise CLIError(f"Variables file {file_path} is empty; expected a mapping.")
    if not isinstance(data, Mapping):
        raise CLIError(f"Variables file {file_path} must contain a mapping at the root.")
    return dict(data)


def assemble_context(
    module_vars: Iterable[Dict[str, Any]],
    vars_files: Iterable[Dict[str, Any]],
    cli_vars: Iterable[tuple[str, str]],
) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    for payload in module_vars:
        context.update(payload)
    for payload in vars_files:
        context.update(payload)
    for key, value in cli_vars:
        context[key] = value
    return context


def resolve_search_paths(template_dir: Path | None, extra_paths: Sequence[str]) -> list[str]:
    resolved: list[str] = []
    if template_dir is not None:
        resolved.append(str(template_dir.resolve()))
    for raw in extra_paths:
        path = Path(raw).expanduser()
        ensure_existing_directory(path)
        resolved.append(str(path.resolve()))
    if not resolved:
        resolved.append(str(Path.cwd()))
    return resolved


def determine_stdin_template_name(output: str | None, autoescape_exts: Sequence[str]) -> str:
    ext = "txt"
    if output and output != "-":
        candidate = Path(output).suffix.lstrip(".").lower()
        if candidate and candidate in set(autoescape_exts):
            ext = candidate
    return f"{STDIN_TEMPLATE_BASENAME}.{ext}"


def select_undefined(name: str):
    mapping = {
        "strict": StrictUndefined,
        "default": Undefined,
        "debug": DebugUndefined,
        "chain": ChainableUndefined,
    }
    return mapping[name]


def build_environment(
    loader,
    args,
    autoescape_exts: Sequence[str],
) -> Environment:
    if args.autoescape == "smart":
        autoescape = select_autoescape(autoescape_exts)
    elif args.autoescape == "on":
        autoescape = True
    else:
        autoescape = False

    env_kwargs = dict(
        loader=loader,
        autoescape=autoescape,
        undefined=select_undefined(args.undefined),
        trim_blocks=args.trim_blocks,
        lstrip_blocks=args.lstrip_blocks,
        keep_trailing_newline=args.keep_trailing_newline,
        newline_sequence=args.newline_sequence,
    )
    return Environment(**env_kwargs)


def render_template(env: Environment, template_name: str, context: Mapping[str, Any]) -> str:
    template = env.get_template(template_name)
    return template.render(context)


def write_output(output: str | None, rendered: str) -> None:
    if output is None or output == "-":
        sys.stdout.write(rendered)
        return
    output_path = Path(output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def execute(args: argparse.Namespace) -> int:
    if args.stdin and args.template:
        raise CLIError("TEMPLATE positional argument and --stdin are mutually exclusive.")
    if not args.stdin and not args.template:
        raise CLIError("Provide a TEMPLATE path or use --stdin.")

    autoescape_exts = parse_autoescape_exts(args.autoescape_exts)

    module_payloads = load_module_variables(args.modules)
    vars_payloads = [load_vars_file(path) for path in args.vars_files]
    cli_payloads = [parse_key_value(pair) for pair in args.cli_vars]
    context = assemble_context(module_payloads, vars_payloads, cli_payloads)
    args.newline_sequence = parse_newline_sequence(args.newline_sequence)

    if args.stdin:
        template_source = sys.stdin.read()
        template_name = determine_stdin_template_name(args.output, autoescape_exts)
        searchpaths = resolve_search_paths(None, args.searchpath)
        dict_loader = DictLoader({template_name: template_source})
        fs_loader = FileSystemLoader(searchpaths)
        loader = ChoiceLoader([dict_loader, fs_loader])
    else:
        template_path = Path(args.template).expanduser()
        ensure_existing_file(template_path, "Template")
        template_dir = template_path.parent
        searchpaths = resolve_search_paths(template_dir, args.searchpath)
        loader = FileSystemLoader(searchpaths)
        template_name = template_path.name

    env = build_environment(loader, args, autoescape_exts)
    rendered = render_template(env, template_name, context)
    write_output(args.output, rendered)
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except CLIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        if args.traceback:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
