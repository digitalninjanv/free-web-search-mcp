# Free Web Search MCP

A lightweight MCP server for AI agents that provides **web search, news search, and web scraping** without a search API key.

It is designed for research workflows where an agent should:

**SEARCH → SELECT / VERIFY → SCRAPE → CROSS-CHECK → ANSWER**

## Features

- Web search with Bing
- News search with freshness filters
- Single-page web scraping
- Search + bounded parallel scraping
- Structured MCP output
- URL canonicalization and deduplication
- Redirect validation
- SSRF-oriented public-IP checks
- DNS pinning with `CURLOPT_RESOLVE`
- Response and output size limits
- Short-lived search and scrape caches
- Retry handling for transient failures
- Binary-content protection
- Trafilatura extraction
- Extraction modes: `fast`, `balanced`, `precision`, `recall`
- Local **stdio** MCP transport
- No search API key required

## MCP tools

| Tool | What it does |
|---|---|
| `search_web` | Find web sources |
| `search_news` | Find recent news |
| `scrape_url` | Extract one selected web page |
| `search_and_scrape` | Search, then scrape up to 5 results |

### Recommended agent workflow

For research that needs reliable evidence:

```text
1. Search
2. Inspect title, URL, domain, date/age and snippet
3. Select relevant / authoritative sources
4. Scrape selected URLs
5. Cross-check important claims
6. Answer with the verified sources
```

Search results are **discovery data**, not automatic proof. A scraped page is evidence from that page, not a guarantee that the source itself is correct.

---

# Installation

## Requirements

- Python 3.10+
- Internet access
- An MCP-compatible client

## 1. Clone the repository

```bash
git clone https://github.com/digitalninjanv/free-web-search-mcp.git
cd free-web-search-mcp
```

## 2. Create a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
```

## 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The server imports:

```text
mcp
curl-cffi
lxml
trafilatura
typing-extensions
```

## 4. Check the source

The current repository entry point is:

```text
local-scrape-mcp-server.py
```

Run:

```bash
python -m py_compile local-scrape-mcp-server.py
```

No output means the Python source passed the syntax check.

## 5. Run the server manually

```bash
python local-scrape-mcp-server.py
```

The server uses **MCP stdio**, so it is normally started by the MCP client rather than kept open manually.

---

# OpenCode V2

OpenCode V2 uses:

```text
mcp.servers.<server-name>
```

Local servers use `type: "local"` and a command array. OpenCode V2 uses `disabled`, not `enabled`. citeturn696106search0turn696106search2

## Recommended configuration

Create or edit:

```text
~/.config/opencode/opencode.jsonc
```

or use a project-local OpenCode config. citeturn696106search2

Example:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "free-web-search": {
        "type": "local",
        "command": [
          "/ABS/PATH/free-web-search-mcp/.venv/bin/python",
          "/ABS/PATH/free-web-search-mcp/local-scrape-mcp-server.py"
        ],
        "cwd": "/ABS/PATH/free-web-search-mcp",
        "environment": {
          "PYTHONUNBUFFERED": "1"
        },
        "disabled": false
      }
    }
  }
}
```

### Example using a real Linux venv

Replace the paths with your actual paths:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "free-web-search": {
        "type": "local",
        "command": [
          "/home/USER/.venvs/free-web-search-mcp/bin/python3",
          "/home/USER/free-web-search-mcp/local-scrape-mcp-server.py"
        ],
        "cwd": "/home/USER/free-web-search-mcp",
        "environment": {
          "PATH": "/home/USER/.venvs/free-web-search-mcp/bin:/usr/local/bin:/usr/bin:/bin",
          "PYTHONUNBUFFERED": "1"
        },
        "disabled": false
      }
    }
  }
}
```

Use the Python executable from the same environment where the MCP dependencies were installed.

Find it with:

```bash
which python
```

or, after activating the venv:

```bash
which python3
```

### OpenCode CLI

OpenCode V2 can also add a local MCP server from the CLI:

```bash
opencode mcp add free-web-search -- \
  /ABS/PATH/free-web-search-mcp/.venv/bin/python \
  /ABS/PATH/free-web-search-mcp/local-scrape-mcp-server.py
```

Then check the connection:

```bash
opencode mcp list
```

OpenCode documents local MCP servers and the `opencode mcp add ... -- command args` syntax. citeturn696106search0turn696106search3

### Tool names in OpenCode

OpenCode prefixes MCP tools with the server name:

```text
free-web-search_search_web
free-web-search_search_news
free-web-search_scrape_url
free-web-search_search_and_scrape
```

OpenCode documents this naming behavior for MCP tools. citeturn696106search0

---

# Pi Coding Agent

Pi's core intentionally keeps MCP out of the minimal core, so **do not copy the OpenCode `mcp.servers` configuration into Pi**. Use an MCP adapter/extension. citeturn759839search6turn759839search1

One current option is **pi-mcp-adapter**.

## 1. Install the adapter

```bash
pi install npm:pi-mcp-adapter
```

Pi's package registry lists `pi-mcp-adapter` as an MCP adapter extension, and the package documents this installation command. citeturn622034search7turn622034search8

## 2. Configure the server

For a project-local setup, create:

```text
.mcp.json
```

Example:

```json
{
  "mcpServers": {
    "free-web-search": {
      "command": "/ABS/PATH/free-web-search-mcp/.venv/bin/python",
      "args": [
        "/ABS/PATH/free-web-search-mcp/local-scrape-mcp-server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

The Pi MCP adapter documents `.mcp.json` as a standard project configuration format. citeturn622034search3turn622034search6

### Linux example

```json
{
  "mcpServers": {
    "free-web-search": {
      "command": "/home/USER/.venvs/free-web-search-mcp/bin/python3",
      "args": [
        "/home/USER/free-web-search-mcp/local-scrape-mcp-server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

Then start Pi in the project:

```bash
pi
```

Open the MCP adapter interface with:

```text
/mcp
```

The current adapter documentation also supports shared global MCP configuration such as `~/.config/mcp/mcp.json`. citeturn622034search3turn622034search6

> Pi MCP support changes over time. Keep the adapter version and its documentation in mind when upgrading Pi. The server itself is a standard stdio MCP server, so only the client-side configuration changes.

---

# Generic MCP client

This server is a local **stdio MCP server**.

The client only needs to start:

```bash
/ABS/PATH/free-web-search-mcp/.venv/bin/python \
  /ABS/PATH/free-web-search-mcp/local-scrape-mcp-server.py
```

The important part is that the command points to the Python environment where the dependencies are installed.

---

# Usage

## Web search

Call:

```text
search_web
```

Example parameters:

```json
{
  "query": "Python 3.14 release changes",
  "count": 5
}
```

The response includes structured fields such as:

```text
rank
title
url
canonical_url
domain
snippet
source_type
evidence_role
```

Search results use:

```text
evidence_role = discovery
```

## News search

Example:

```json
{
  "query": "OpenAI",
  "count": 5,
  "freshness": "day",
  "market": "en-US"
}
```

Supported freshness values:

```text
hour
day
week
month
```

## Scrape a selected page

Example:

```json
{
  "url": "https://example.com/article",
  "output_format": "markdown",
  "max_chars": 25000,
  "extraction_mode": "fast"
}
```

Supported output formats:

```text
markdown
txt
xml
json
```

Supported extraction modes:

```text
fast
balanced
precision
recall
```

## Search + scrape

Example:

```json
{
  "query": "latest Linux kernel security changes",
  "count": 5,
  "news": false,
  "max_chars": 12000,
  "extraction_mode": "fast"
}
```

The server bounds this operation to a maximum of 5 scraped results and at most 3 concurrent workers.

---

# Security

This project performs outbound HTTP requests, so URL and network validation are important.

## SSRF-oriented protection

The server:

- accepts only `http` and `https`
- rejects URLs containing username/password credentials
- resolves hostnames before connecting
- allows only globally routable/public IP addresses
- blocks localhost and other non-public destinations
- validates every redirect target again
- pins resolved addresses with libcurl `CURLOPT_RESOLVE`

## Response limits

Current implementation limits include:

```text
Max redirects:       5
Max search results:   50
Max query length:     1000 characters
Max HTTP response:   4 MiB
Max extracted text:  100,000 characters
Max domain filters:  5
Max batch scrapes:   5
Batch workers:        3
```

## Binary content

The server intentionally rejects common binary content such as PDFs, images, archives, audio, and video instead of blindly decoding them as text.

The current scraper does not execute JavaScript.

## Retries

Only transient failures are retried. The implementation also supports `Retry-After` and bounded backoff with jitter.

---

# Performance and token efficiency

The server is designed to avoid unnecessary context growth:

- Search returns compact structured metadata.
- Pages are scraped only when needed.
- `max_chars` bounds extracted content.
- Search results are cached briefly.
- Scraped pages are cached briefly.
- Canonical URLs improve deduplication and cache reuse.
- Batch scraping has bounded concurrency.
- `fast` extraction is the normal path.

Current cache defaults:

```text
Search cache TTL:   120 seconds
Scrape cache TTL:    60 seconds
Search cache size:   64 entries
Scrape cache size:   32 entries
```

Caches are in-memory and disappear when the process exits.

---

# Source quality

This server does not decide whether a source is true.

Agents should consider:

- primary vs secondary source
- source authority
- publication date
- canonical URL
- whether the page directly supports the claim
- independent confirmation
- relevance to the question

Use search for discovery and scraping for evidence.

---

# Limitations

### Bing HTML parsing

Search parsing is based on Bing's public HTML pages rather than a contractual search API. Changes to Bing markup can require parser updates.

### JavaScript-heavy pages

Pages that depend on browser-side JavaScript may not extract correctly.

### Binary documents

Binary documents are intentionally out of scope for the normal text scraper.

### Anti-bot pages

If Bing returns a challenge/CAPTCHA page, the server reports an error instead of treating it as a legitimate zero-result search.

### No search API key

The project does not require a Bing Search API key because it uses the public Bing web/news HTML endpoints. Availability and acceptable use can change, so users should follow the applicable provider terms and limits.

---

# Development

Activate the environment:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Syntax check:

```bash
python -m py_compile local-scrape-mcp-server.py
```

Run:

```bash
python local-scrape-mcp-server.py
```

For MCP debugging, inspect the MCP client's connection and tool-registration logs.

---

# Repository structure

Current entry point:

```text
free-web-search-mcp/
├── local-scrape-mcp-server.py
├── requirements.txt
└── README.md
```

Recommended future additions:

```text
LICENSE
.gitignore
CHANGELOG.md
tests/
.github/workflows/
```

---

# Why this MCP server?

Most search tools stop at discovery.

This project is intentionally structured so an agent can separate:

```text
Discovery
   ↓
Source selection
   ↓
URL validation
   ↓
Content extraction
   ↓
Cross-check
   ↓
Answer
```

That makes it useful for research-heavy coding agents and AI workflows that need fresh web evidence without sending entire search pages into the context window.

---

# License

No open-source license is currently declared in this repository.

Add an explicit `LICENSE` file before presenting the project as a reusable open-source package.

---

## Links

- OpenCode MCP servers: https://opencode.ai/v2/docs/mcp-servers
- OpenCode config: https://opencode.ai/v2/docs/config
- OpenCode CLI: https://opencode.ai/v2/docs/cli/commands
- Pi MCP adapter: https://pi.dev/packages/pi-mcp-adapter
