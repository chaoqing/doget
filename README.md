# doget

Browse and download [Ollama](https://ollama.com) model layers from the command line.

`doget` fetches a model manifest from `registry.ollama.ai` and either:
- **serves** an HTML page locally with a table of layer download links, proxying all requests to the registry so links work directly in a browser or download tool, or
- **exports** a self-contained HTML file with direct absolute registry URLs for offline use.

## Installation

Requires Python 3.12+.

**Run without installing** (recommended):
```bash
uvx doget llama3
```

**Install globally:**
```bash
pip install doget
# or
uv tool install doget
```

## Usage

```
doget [serve] <model> [--port PORT] [--host HOST]
doget export  <model> [--output FILE]
```

`serve` is the default — `doget llama3` and `doget serve llama3` are equivalent.

### Commands

| Command | Description |
|---|---|
| `serve` | Start a local HTTP server (default) |
| `export` | Write a standalone `.html` file |

### Options

| Option | Command | Default | Description |
|---|---|---|---|
| `--port PORT` | serve | `8080` (or `$PORT`) | TCP port to listen on |
| `--host HOST` | serve | `0.0.0.0` | Interface to bind to |
| `--output FILE`, `-o FILE` | export | `<model>-<tag>.html` | Output filename |

### Examples

```bash
# Serve layer links for the default (latest) tag
uvx doget llama3

# Specific tag
uvx doget llama3:8b

# Custom port, localhost only
uvx doget llama3 --port 9000 --host 127.0.0.1

# Export a standalone HTML file
uvx doget export llama3:8b               # → llama3-8b.html
uvx doget export llama3 -o index.html
```

Then open <http://localhost:8080/> in a browser, or download layers with any tool:

```bash
# Download the manifest
curl http://localhost:8080/manifest -O

# Stream a layer directly (doget proxies the request to the registry)
wget http://localhost:8080/v2/library/llama3/blobs/sha256-<digest>
```

## How it works

1. On startup, `doget` fetches the model manifest from `registry.ollama.ai`.
2. **serve**: hosts an HTML page at `/` with a numbered table of layers (index, size, name/download link). A `/manifest` endpoint serves the raw JSON. Every other path is proxied verbatim to the upstream registry.
3. **export**: renders the same HTML with full absolute URLs and embeds the manifest as a `data:` URI, producing a fully self-contained file.

## Development

```bash
git clone <repo>
cd doget
uv sync
uv run doget llama3
```

## License

MIT
