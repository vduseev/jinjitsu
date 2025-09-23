import argparse
import json
import sys
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)


def main():
    ap = argparse.ArgumentParser(
        description="Minimal Jinja CLI ",
    )
    ap.add_argument(
        "template",
        help="Path to template file. Use - for stdin",
        type=argparse.FileType("r", encoding="utf-8"),
    )
    ap.add_argument(
        "-d",
        "--data",
        help="Path to data files with variables",
        action="extend",
        default=[],
        type=argparse.FileType("r", encoding="utf-8"),
    )
    ap.add_argument(
        "-s",
        "--searchpath",
        help="Extra paths for {% include %} / {% extends %}",
        action="extend",
        default=[],
        type=argparse.FileType("r", encoding="utf-8"),
    )
    ap.add_argument(
        "-m",
        "--module",
        help="Python module to load variables from",
        action="extend",
        default=[],
        type=argparse.FileType("r", encoding="utf-8"),
    )
    ap.add_argument(
        "-o",
        "--output",
        help="Output file path. Use - for stdout",
        default="-",
        type=argparse.FileType("w", encoding="utf-8"),
    )
    args = ap.parse_args()

    template_path = Path(args.template)
    search_paths = [template_path]
    for path in args.searchpath:
        search_paths.append(path)

    searchpaths = [str(path.resolve()) for path in search_paths]
    env = Environment(
        loader=FileSystemLoader(searchpaths),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )

    template = env.get_template(template_path.name)

    if args.data == "-":
        ctx = json.load(sys.stdin)
    else:
        with open(args.data, "r", encoding="utf-8") as f:
            ctx = json.load(f)
    if not isinstance(ctx, dict):
        ctx = {"data": ctx}

    rendered = template.render(**ctx)

    if args.output == "-":
        sys.stdout.write(rendered)
    else:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered)

if __name__ == "__main__":
    main()
