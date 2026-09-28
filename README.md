# Free Web Search MCP

A lightweight **MCP server for AI agents** that provides web search, news search, and web scraping through Bing's public web interface.

Designed for research workflows:

```text
SEARCH → SELECT / VERIFY → SCRAPE → CROSS-CHECK → ANSWER
```

## What this project does

This MCP server gives an AI agent four tools:

| Tool | Purpose |
|---|---|
| `search_web` | Search the web and return structured source metadata |
| `search_news` | Search recent news with freshness filters |
| `scrape_url` | Extract text from one selected web page |
| `search_and_scrape` | Search, then scrape a bounded number of results |

Search results are treated as **discovery**, not automatic evidence. The agent should select relevant sources, scrape them, and cross-check important claims.

## Features

- Bing Web Search
- Bing News Search
- Freshness filters: `hour`, `day`, `week`, `month`
- Web-page extraction with Trafilatura
- Structured MCP output
- URL canonicalization
- Bing redirect decoding
- URL deduplication
- Domain filters
- SSRF-oriented public-IP validation
- Redirect-by-redirect URL validation
- DNS pinning with `CURLOPT_RESOLVE`
- `curl_cffi` session reuse with `trust_env=False`
- Retry handling for transient failures
- `Retry-After` support
- Response-size limits
- Binary-content protection
- Short-lived search and scrape caches
- Bounded parallel scraping
- Extraction modes: `fast`, `balanced`, `precision`, `recall`
- Local MCP stdio transport
- No Bing Search API key required

---

# 1. Requirements

You need:

- Python 3.10+
- Git
- Internet access
- An MCP-compatible client such as OpenCode or Pi

Runtime packages:

```text
mcp
curl-cffi
lxml
trafilatura
typing-extensions
```

---

# 2. Get the source

Clone the repository somewhere convenient. For example:

```bash
mkdir -p ~/.local/src
git clone https://github.com/digitalninjanv/free-web-search-mcp.git ~/.local/src/free-web-search-mcp
cd ~/.local/src/free-web-search-mcp
```

Check the files:

```bash
ls -la
```

The MCP entry point in this repository is:

```text
local-scrape-mcp-server.py
```

---

# 3. Install dependencies in a dedicated Python environment

Using a dedicated virtual environment avoids conflicts with the system Python.

Create it:

```bash
python3 -m venv ~/.venvs/mcp-local-scrape
```

Upgrade pip:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -m pip install --upgrade pip
```

Install the project dependencies:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -m pip install -r ~/.local/src/free-web-search-mcp/requirements.txt
```

Verify that the packages are available:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -c "import mcp, curl_cffi, lxml, trafilatura; print('dependencies: OK')"
```

---

# 4. Install the MCP server into OpenCode's local server directory

This step is optional as a filesystem convention, but it is the layout used by the OpenCode example below.

Create the directory:

```bash
mkdir -p ~/.config/opencode/mcp-servers/local-scrape
```

Copy the server file and rename it to the conventional `server.py` name:

```bash
cp ~/.local/src/free-web-search-mcp/local-scrape-mcp-server.py \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

You should now have:

```text
~/.config/opencode/
└── mcp-servers/
    └── local-scrape/
        └── server.py
```

Check it:

```bash
ls -l ~/.config/opencode/mcp-servers/local-scrape/server.py
```

## Why copy the file?

The Git repository remains your source code, while OpenCode gets a stable local path for the MCP server.

You can update the installed server later with:

```bash
cp ~/.local/src/free-web-search-mcp/local-scrape-mcp-server.py \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

---

# 5. Validate the installed server

First run a syntax check:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -m py_compile \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

No output means the file passed Python's syntax compiler.

You can also verify the interpreter path:

```bash
readlink -f ~/.venvs/mcp-local-scrape/bin/python3
```

Keep the resulting absolute path. You will use it in the MCP configuration.

---

# 6. Configure OpenCode V2

OpenCode V2 uses `mcp.servers.<name>` for MCP servers. A local MCP server uses `type: "local"` and a command array containing the executable plus its arguments. The process can also define `cwd`, `environment`, and `disabled`; `disabled: false` is the normal enabled state. [OpenCode MCP server documentation](https://opencode.ai/v2/docs/mcp-servers)

The global OpenCode configuration is normally:

```text
~/.config/opencode/opencode.json
```

or:

```text
~/.config/opencode/opencode.jsonc
```

OpenCode supports JSON and JSONC. [OpenCode configuration documentation](https://opencode.ai/v2/docs/config)

## Recommended configuration

Open:

```bash
nano ~/.config/opencode/opencode.jsonc
```

Add this inside the top-level configuration:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "local-scrape": {
        "type": "local",
        "command": [
          "/home/USER/.venvs/mcp-local-scrape/bin/python3",
          "/home/USER/.config/opencode/mcp-servers/local-scrape/server.py"
        ],
        "cwd": "/home/USER/.config/opencode/mcp-servers/local-scrape",
        "environment": {
          "PATH": "/home/USER/.venvs/mcp-local-scrape/bin:/usr/local/bin:/usr/bin:/bin",
          "PYTHONUNBUFFERED": "1"
        },
        "disabled": false
      }
    }
  }
}
```

### Important: replace `/home/USER`

Do not copy `/home/USER` literally.

Find your real home directory:

```bash
printf '%s\\n' "$HOME"
```

For example, if it prints:

```text
/home/najib
```

the configuration becomes:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "local-scrape": {
        "type": "local",
        "command": [
          "/home/najib/.venvs/mcp-local-scrape/bin/python3",
          "/home/najib/.config/opencode/mcp-servers/local-scrape/server.py"
        ],
        "cwd": "/home/najib/.config/opencode/mcp-servers/local-scrape",
        "environment": {
          "PATH": "/home/najib/.venvs/mcp-local-scrape/bin:/usr/local/bin:/usr/bin:/bin",
          "PYTHONUNBUFFERED": "1"
        },
        "disabled": false
      }
    }
  }
}
```

This matches the common layout:

```text
Python environment
~/.venvs/mcp-local-scrape/bin/python3

MCP server
~/.config/opencode/mcp-servers/local-scrape/server.py
```

### Why use the absolute Python path?

Do not depend on an arbitrary `python3` from `PATH`.

Using the venv interpreter guarantees that the MCP server starts with the environment where `mcp`, `curl_cffi`, `lxml`, and `trafilatura` were installed.

### Why use `cwd`?

`cwd` gives the server a stable working directory. It is optional, but useful when diagnosing file/path issues.

### Why `PYTHONUNBUFFERED=1`?

It makes Python I/O unbuffered, which is useful for stdio-based MCP communication and troubleshooting.

### Why `PATH`?

It is optional when `command` already uses an absolute Python path. Keeping it explicit makes the launched environment predictable.

### Why `disabled: false`?

OpenCode V2 uses the `disabled` field. Do not use `enabled: true` in this configuration. urlOpenCode MCP server documentationhttps://opencode.ai/v2/docs/mcp-servers

---

# 7. Start OpenCode and verify the MCP server

Start or restart OpenCode after changing the configuration.

Then check MCP servers:

```bash
opencode mcp list
```

The local server should appear as:

```text
local-scrape
```

OpenCode prefixes tools with the server name, so the tools are exposed like:

```text
local-scrape_search_web
local-scrape_search_news
local-scrape_scrape_url
local-scrape_search_and_scrape
```

If the server does not connect, verify these three things first:

```bash
test -x ~/.venvs/mcp-local-scrape/bin/python3 && echo "python: OK"
test -f ~/.config/opencode/mcp-servers/local-scrape/server.py && echo "server.py: OK"
~/.venvs/mcp-local-scrape/bin/python3 -c "import mcp, curl_cffi, lxml, trafilatura; print('dependencies: OK')"
```

---

# 8. OpenCode CLI alternative

Instead of editing the JSON configuration manually, OpenCode also supports adding a local MCP server from the CLI:

```bash
opencode mcp add local-scrape -- \
  ~/.venvs/mcp-local-scrape/bin/python3 \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

Then inspect the registered server:

```bash
opencode mcp list
```

The manual JSON configuration remains useful when you need `cwd`, environment variables, or other process options. urlOpenCode MCP server documentationhttps://opencode.ai/v2/docs/mcp-servers

---

# 9. Pi Coding Agent

Pi and OpenCode use different configuration systems.

For Pi, the current `pi-mcp-adapter` documentation recommends the shared MCP format:

```text
.mcp.json
```

for a project, or:

```text
~/.config/mcp/mcp.json
```

for a user-global shared configuration. [Pi MCP Adapter documentation](https://github.com/nicobailon/pi-mcp-adapter)

## Install the Pi MCP adapter

```bash
pi install npm:pi-mcp-adapter
```

The current package is published for Pi's MCP integration. Review third-party package source before installation. [Pi MCP Adapter package](https://pi.dev/packages/pi-mcp-adapter)

## Project-local Pi setup

Inside the project where you run Pi:

```text
.mcp.json
```

put:

```json
{
  "mcpServers": {
    "local-scrape": {
      "command": "/home/USER/.venvs/mcp-local-scrape/bin/python3",
      "args": [
        "/home/USER/.config/opencode/mcp-servers/local-scrape/server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      },
      "cwd": "/home/USER/.config/opencode/mcp-servers/local-scrape"
    }
  }
}
```

Replace `/home/USER` with the same absolute home path you used for OpenCode.

The same installed server can therefore be shared:

```text
OpenCode
  └── ~/.config/opencode/mcp-servers/local-scrape/server.py

Pi
  └── points to the same server.py
```

## User-global Pi setup

For the adapter's shared global configuration, create:

```bash
mkdir -p ~/.config/mcp
nano ~/.config/mcp/mcp.json
```

Then use:

```json
{
  "mcpServers": {
    "local-scrape": {
      "command": "/home/USER/.venvs/mcp-local-scrape/bin/python3",
      "args": [
        "/home/USER/.config/opencode/mcp-servers/local-scrape/server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      },
      "cwd": "/home/USER/.config/opencode/mcp-servers/local-scrape"
    }
  }
}
```

The current adapter documentation specifically identifies `~/.config/mcp/mcp.json` and `.mcp.json` as the preferred shared configuration locations. urlPi MCP Adapter documentationhttps://github.com/nicobailon/pi-mcp-adapter

> Do not copy an OpenCode `mcp.servers` block into Pi. Pi's MCP adapter uses the `mcpServers` schema above.

---

# 10. Generic MCP clients

This project is a local stdio MCP server.

The essential command is:

```bash
~/.venvs/mcp-local-scrape/bin/python3 \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

Other MCP clients can launch the same command, but their configuration file and JSON schema may differ.

---

# 11. How the tools should be used

## Web search

Use `search_web` to discover candidate sources.

Example:

```json
{
  "query": "Linux kernel latest security changes",
  "count": 5
}
```

The server returns metadata such as:

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

## Scrape a selected URL

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

## Search and scrape

Use the fast path for clear queries:

```json
{
  "query": "latest Linux kernel security changes",
  "count": 5,
  "news": false,
  "max_chars": 12000,
  "extraction_mode": "fast"
}
```

The implementation bounds this operation to a maximum of 5 scraped results and at most 3 concurrent workers.

---

# 12. Security

This server makes outbound HTTP requests on behalf of an AI agent.

## URL validation

The server:

- accepts only `http` and `https`
- rejects URLs containing username/password credentials
- normalizes hostnames
- resolves the hostname before fetching
- allows only globally routable/public addresses
- blocks localhost and non-public targets
- validates redirect targets again

## DNS pinning

Resolved public IPs are pinned with libcurl `CURLOPT_RESOLVE`.

Each worker thread uses its own `curl_cffi` session so per-session DNS state is not shared unsafely between concurrent requests.

## Response limits

Current implementation limits:

```text
Max redirects:       5
Max search results:  50
Max query length:     1000 characters
Max HTTP response:   4 MiB
Max extracted text:  100,000 characters
Max domain filters:  5
Max batch scrapes:   5
Batch workers:        3
```

## Binary content

Known binary content types and common binary magic bytes are rejected instead of being blindly decoded into large text payloads.

The scraper does not execute JavaScript.

## Retries

Only transient HTTP/network failures are retried. The implementation supports `Retry-After` and bounded backoff with jitter.

---

# 13. Performance and token efficiency

The server is designed to keep agent context under control:

- Search returns compact metadata.
- Full pages are fetched only when needed.
- `max_chars` bounds extracted content.
- Search results use a short cache.
- Scraped pages use a short cache.
- Canonicalization improves deduplication and cache reuse.
- Batch scraping uses bounded concurrency.
- `fast` extraction is the normal path.

Current defaults:

```text
Search cache TTL:   120 seconds
Scrape cache TTL:    60 seconds
Search cache size:   64 entries
Scrape cache size:   32 entries
```

Caches are memory-only and reset when the MCP process exits.

---

# 14. Troubleshooting

## "ModuleNotFoundError: No module named mcp"

The MCP client is using the wrong Python executable.

Check:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -c "import mcp; print(mcp.__file__)"
```

Then make sure the same executable is used in the MCP configuration.

## "server.py not found"

Check:

```bash
ls -l ~/.config/opencode/mcp-servers/local-scrape/server.py
```

If it does not exist:

```bash
mkdir -p ~/.config/opencode/mcp-servers/local-scrape
cp ~/.local/src/free-web-search-mcp/local-scrape-mcp-server.py \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

## OpenCode shows the server but the tools fail

Run the installed server manually with the exact Python executable:

```bash
~/.venvs/mcp-local-scrape/bin/python3 \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

If the process reports an import or runtime error, fix that before debugging the MCP client.

## Bing returns no usable results

The project detects common challenge/CAPTCHA markers and reports a failure rather than silently treating a challenge page as zero results.

## A JavaScript-heavy website does not extract correctly

The scraper does not execute JavaScript. A server-rendered page or another source may be required.

---

# 15. Updating the installation

Pull the newest source:

```bash
cd ~/.local/src/free-web-search-mcp
git pull
```

Update dependencies:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -m pip install -r requirements.txt --upgrade
```

Copy the updated server:

```bash
cp ~/.local/src/free-web-search-mcp/local-scrape-mcp-server.py \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

Run the syntax check again:

```bash
~/.venvs/mcp-local-scrape/bin/python3 -m py_compile \
  ~/.config/opencode/mcp-servers/local-scrape/server.py
```

Restart the MCP client.

---

# 16. Recommended directory layout

After installation, a clean Linux setup looks like:

```text
~/
├── .local/
│   └── src/
│       └── free-web-search-mcp/
│           ├── local-scrape-mcp-server.py
│           ├── requirements.txt
│           └── README.md
│
├── .venvs/
│   └── mcp-local-scrape/
│       └── bin/
│           └── python3
│
└── .config/
    └── opencode/
        ├── opencode.jsonc
        └── mcp-servers/
            └── local-scrape/
                └── server.py
```

This separation makes updates and troubleshooting easier:

```text
Git repository  →  source code
Python venv     →  dependencies
OpenCode path   →  MCP runtime entry point
OpenCode config →  MCP registration
```

---

# 17. Agent research workflow

For high-confidence research:

```text
SEARCH
  ↓
Inspect title / URL / domain / date
  ↓
SELECT relevant sources
  ↓
SCRAPE selected URLs
  ↓
CROSS-CHECK important claims
  ↓
ANSWER with the supporting sources
```

Do not assume that the first search result is authoritative.

A successful scrape means the page was extracted. It does not independently prove that the page's claims are true.

---

# 18. Limitations

### Bing HTML parsing

Search results are parsed from Bing's public HTML interface, not from a contractual search API. Changes to Bing's markup can require parser updates.

### No JavaScript execution

Client-side rendered pages may not extract correctly.

### Binary documents

PDFs, images, archives, audio, and video are intentionally outside the normal text extraction path.

### Provider availability

The project uses Bing's public web/news interface and therefore depends on that interface remaining accessible and compatible with the parser.

### Acceptable use

Use the software responsibly and in accordance with applicable provider terms, site policies, rate limits, and law.

---

# 19. Development

From the cloned repository:

```bash
cd ~/.local/src/free-web-search-mcp
source ~/.venvs/mcp-local-scrape/bin/activate
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

The server uses MCP stdio transport and is normally started by the MCP client.

---

# 20. Repository metadata

## Repository name

```text
free-web-search-mcp
```

## GitHub description

```text
Free MCP web search and scraping server for AI agents. Bing Web & News search, no API key required, secure URL fetching, SSRF protection, canonicalization, caching, and bounded extraction.
```

## Suggested topics

```text
mcp
model-context-protocol
mcp-server
web-search
web-scraping
web-research
ai-agents
ai-agent
llm-tools
bing-search
bing-news
python
trafilatura
curl-cffi
ssrf
```

Use only topics that accurately describe the project.

---

# 21. License

No open-source license is currently declared in this repository.

Add an explicit `LICENSE` file before presenting the project as an open-source package for reuse.

---

## Documentation

- OpenCode MCP servers: https://opencode.ai/v2/docs/mcp-servers
- OpenCode configuration: https://opencode.ai/v2/docs/config
- OpenCode CLI: https://opencode.ai/v2/docs/cli/commands
- Pi MCP Adapter: https://github.com/nicobailon/pi-mcp-adapter
- Pi MCP Adapter package: https://pi.dev/packages/pi-mcp-adapter
