#!/usr/bin/env python3
"""doget - browse and download Ollama model layers.

Commands:
    serve   (default) Start a local HTTP server with download links
    export  Write a standalone HTML file with direct download links

Examples:
    uvx doget llama3                         # serve at http://localhost:8080/
    uvx doget serve llama3 --port 9000
    uvx doget export llama3:8b               # writes llama3-8b.html
    uvx doget export llama3 --output out.html
"""

import argparse
import base64
import io
import json
import os
import sys

import requests
from flask import Flask, Response, render_template_string, request, send_file
from jinja2 import Template

from doget import DEFAULT_REGISTRY, format_size, get_model_info, parse_model_name

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ model_name }}</title>
  <style>
    body { font-family: sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: .4rem .8rem; text-align: left; }
    th { background: #f0f0f0; }
    tr:nth-child(even) { background: #fafafa; }
    td:first-child { text-align: right; width: 3em; }
    td:nth-child(2) { white-space: nowrap; width: 7em; }
  </style>
</head>
<body>
<h1>Model: {{ model_name }}</h1>

<h2>Manifest</h2>
<p><a href="{{ manifest_href }}" download="manifest.json">&#x2B07; Download manifest.json</a></p>

<h2>Layers</h2>
<table>
  <thead>
    <tr><th>#</th><th>Size</th><th>Name / Download</th></tr>
  </thead>
  <tbody>
  {% for layer_name, layer_url, layer_size in layers %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ format_size(layer_size) }}</td>
      <td><a href="{{ layer_url }}" download="{{ layer_name }}">{{ layer_name }}</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</body>
</html>"""

app = Flask(__name__)

# Populated in cmd_serve() before app.run()
_model_name: str = ""
_manifest: dict = {}
_processed_layers: list = []


@app.route("/", methods=["GET", "HEAD"])
def index():
    return render_template_string(
        HTML_TEMPLATE,
        model_name=_model_name,
        layers=_processed_layers,
        manifest_href="/manifest",
        format_size=format_size,
    )


@app.route("/manifest", methods=["GET"])
def download_manifest():
    manifest_bytes = json.dumps(_manifest, indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(manifest_bytes),
        mimetype="application/json",
        as_attachment=True,
        download_name="manifest.json",
    )


@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
def proxy(path):
    dest = f"https://{DEFAULT_REGISTRY}/{path}"
    if request.query_string:
        dest += "?" + request.query_string.decode("utf-8")

    headers = {
        k: v
        for k, v in request.headers
        if k.lower() not in {"host", "connection", "keep-alive", "transfer-encoding", "content-length"}
    }
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

    try:
        resp = requests.request(
            method=request.method,
            url=dest,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=True,
            stream=True,
            verify=True,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        return Response(f"Proxy error: {e}", status=502)

    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive", "server"}
    response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded]
    return Response(resp.raw, status=resp.status_code, headers=response_headers)


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_serve(args):
    global _model_name, _manifest, _processed_layers

    _model_name = args.model
    _manifest, layers = get_model_info(_model_name)
    _processed_layers = [
        (name, url.replace(f"https://{DEFAULT_REGISTRY}", "") if args.proxy else url, size)
        for name, url, size in layers
    ]

    print(f"Serving {_model_name} at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port)


def cmd_export(args):
    manifest, layers = get_model_info(args.model)

    # Embed manifest as a data URI so the HTML file is fully self-contained
    manifest_json = json.dumps(manifest, indent=2)
    manifest_b64 = base64.b64encode(manifest_json.encode()).decode()
    manifest_href = f"data:application/json;base64,{manifest_b64}"

    html = Template(HTML_TEMPLATE).render(
        model_name=args.model,
        layers=[
            (name, url.replace(f"https://{DEFAULT_REGISTRY}", "") if args.proxy else url, size)
            for name, url, size in layers
        ],
        manifest_href=manifest_href,
        format_size=format_size,
    )

    output = args.output or _default_output(args.model)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {len(layers)} layers → {output}")


def _default_output(model_input: str) -> str:
    """Return a filename like 'llama3-8b.html' derived from the model name."""
    namespace, model, tag = parse_model_name(model_input)
    parts = [] if namespace == "library" else [namespace]
    parts += [model, tag]
    return "-".join(parts) + ".html"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {"serve", "export"}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doget",
        description="Browse and download Ollama model layers. Default command: serve.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # serve
    serve_p = subparsers.add_parser(
        "serve",
        help="Start a local HTTP server with download links (default)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    serve_p.add_argument(
        "model",
        help="Model name, e.g. 'llama3', 'llama3:8b', 'library/llama3:latest'",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8080)),
        help="TCP port to listen on (overrides $PORT)",
    )
    serve_p.add_argument(
        "--host",
        default="0.0.0.0",
        help="Interface to bind to",
    )
    serve_p.add_argument(
        "--proxy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rewrite layer URLs to relative paths so the local server proxies downloads",
    )

    # export
    export_p = subparsers.add_parser(
        "export",
        help="Write a standalone HTML file with direct download links",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    export_p.add_argument(
        "model",
        help="Model name, e.g. 'llama3', 'llama3:8b'",
    )
    export_p.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help="Output filename (default: <model>-<tag>.html)",
    )
    export_p.add_argument(
        "--proxy",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Rewrite layer URLs to relative paths (for serving the file through a local proxy)",
    )

    return parser


def main():
    # Allow bare `doget <model>` without an explicit subcommand (defaults to serve)
    if len(sys.argv) > 1 and sys.argv[1] not in _SUBCOMMANDS and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "serve")

    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
