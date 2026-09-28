# Agent-Native Web Research MCP

A lightweight, security-focused MCP server for AI agents to research the public web with a disciplined workflow:

**SEARCH → SELECT/VERIFY → SCRAPE → CROSS-CHECK → ANSWER**

Built for agent-native usage rather than dumping raw search results into the model context.

## Why this project

Many web-search tools stop at search results. This server separates **discovery** from **evidence**:

- Search results are marked as `discovery`.
- Selected pages are scraped into bounded text.
- URLs are canonicalized and deduplicated.
- Redirects are revalidated.
- Public-IP checks and DNS pinning reduce SSRF risk.
- Responses and extracted content are size-bounded.
- Short-lived caches reduce repeated upstream requests.
- Scraping can run in bounded parallel batches.
- Structured MCP output gives agents metadata they can use for source selection.

The server intentionally avoids pretending that the first search result is automatically authoritative.

## Features

- **Bing Web Search** through the public Bing web interface.
- **Bing News Search** with freshness filtering: `hour`, `day`, `week`, `month`.
- **Single-URL scraping** with Trafilatura.
- **Bounded search + scrape** for up to 5 selected results in parallel.
- **Structured output** for search and search+scrape tools.
- **Canonical URL normalization** and tracking-parameter removal.
- **Bing redirect decoding**.
- **URL deduplication**.
- **Domain filtering**.
- **SSRF-oriented URL validation**:
  - only `http` / `https`
  - public/global IP validation
  - localhost blocking
  - redirect-by-redirect revalidation
  - DNS pinning through `CURLOPT_RESOLVE`
- **Deterministic HTTP behavior** with `trust_env=False`.
- **Retry handling** for transient HTTP/network failures.
- **Response limits** to control memory and token usage.
- **Binary-content protection** so PDFs/images/archives are not blindly turned into garbage text.
- **Short TTL caches** for search and scrape results.
- **Multiple extraction modes**: `fast`, `balanced`, `precision`, `recall`.

## MCP Tools

| Tool | Purpose |
|---|---|
| `search_web` | Discover relevant web sources |
| `search_news` | Discover recent news sources |
| `scrape_url` | Extract content from one selected URL |
| `search_and_scrape` | Search, then scrape a bounded set of results |

### Agent workflow

Use the tools in this order for evidence-heavy research:

```text
1. search_web / search_news
2. Inspect title, URL, domain, snippet, age, canonical_url
3. Select authoritative or relevant sources
4. scrape_url on selected URLs
5. Cross-check important claims across independent sources
6. Answer with citations/links from the agent
```

`search_and_scrape` is available as a faster path for clear queries, but its output is still not a guarantee that every returned source is authoritative.

## Project structure

Recommended repository layout:

```text
agent-native-web-research-mcp/
├── server.py
├── requirements.txt
├── README.md
└── LICENSE
```

Rename the current script to `server.py` before publishing:

```bash
mv 'local-scrape-mcp-server(2).py' server.py
```

## Requirements

- Python 3.10+
- Internet access
- An MCP-compatible client/agent
- Linux, macOS, or Windows

Runtime dependencies:

```text
mcp
curl-cffi
lxml
trafilatura
typing-extensions
```

## Installation

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/agent-native-web-research-mcp.git
cd agent-native-web-research-mcp
```

### 2. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install mcp curl-cffi lxml trafilatura typing-extensions
```

### 4. Validate the Python file

```bash
python -m py_compile server.py
```

If this command returns no output, the Python source passes the syntax compiler.

### 5. Start the MCP server

The server uses MCP **stdio** transport:

```bash
python server.py
```

Keep stdout reserved for MCP traffic. Application logging is sent through the Python logger.

---

# OpenCode

OpenCode supports local MCP servers over stdio. Current OpenCode V2 configuration uses:

```text
mcp.servers.<name>
```

### Option A — add from the CLI

From the project that should use the server:

```bash
opencode mcp add web-research -- python3 /ABS/PATH/agent-native-web-research-mcp/server.py
```

Then verify:

```bash
opencode mcp list
```

### Option B — configure `opencode.jsonc`

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "web-research": {
        "type": "local",
        "command": [
          "/ABS/PATH/agent-native-web-research-mcp/.venv/bin/python",
          "/ABS/PATH/agent-native-web-research-mcp/server.py"
        ]
      }
    }
  }
}
```

Using the virtual-environment Python is recommended because it guarantees that OpenCode starts the server with the project's intended dependencies.

After OpenCode connects, the tools are exposed under the server name, such as:

```text
web-research_search_web
web-research_search_news
web-research_scrape_url
web-research_search_and_scrape
```

OpenCode also supports Code Mode; keep the server name short and unique.

---

# Pi Coding Agent

Pi currently supports MCP through its MCP integration/extension ecosystem. The exact setup depends on the Pi MCP adapter/version you use.

A common configuration shape is a project `.mcp.json`:

```json
{
  "mcpServers": {
    "web-research": {
      "command": "/ABS/PATH/agent-native-web-research-mcp/.venv/bin/python",
      "args": [
        "/ABS/PATH/agent-native-web-research-mcp/server.py"
      ]
    }
  }
}
```

For installations using the Pi MCP adapter, user-global MCP configuration is commonly placed under:

```text
~/.pi/agent/mcp.json
```

or shared MCP configuration such as:

```text
~/.config/mcp/mcp.json
```

Then expose the server with the same stdio command:

```json
{
  "mcpServers": {
    "web-research": {
      "command": "/ABS/PATH/agent-native-web-research-mcp/.venv/bin/python",
      "args": [
        "/ABS/PATH/agent-native-web-research-mcp/server.py"
      ]
    }
  }
}
```

If your Pi installation uses a different MCP adapter, follow that adapter's current file precedence and server schema.

---

# Claude Desktop

For a standard local MCP/stdio configuration:

```json
{
  "mcpServers": {
    "web-research": {
      "command": "/ABS/PATH/agent-native-web-research-mcp/.venv/bin/python",
      "args": [
        "/ABS/PATH/agent-native-web-research-mcp/server.py"
      ]
    }
  }
}
```

Restart the client after changing the MCP configuration.

---

# Usage examples

## Web search

```text
search_web(
  query="Python 3.14 release changes",
  count=5
)
```

Returns structured discovery data such as:

```json
{
  "query": "Python 3.14 release changes",
  "source_type": "web",
  "results": [
    {
      "rank": 1,
      "title": "...",
      "url": "...",
      "canonical_url": "...",
      "domain": "python.org",
      "snippet": "...",
      "source_type": "web",
      "evidence_role": "discovery"
    }
  ]
}
```

## News search

```text
search_news(
  query="OpenAI",
  count=5,
  freshness="day",
  market="en-US"
)
```

Supported freshness values:

```text
hour
day
week
month
```

## Scrape one source

```text
scrape_url(
  url="https://example.com/article",
  output_format="markdown",
  max_chars=25000,
  extraction_mode="fast"
)
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

```text
search_and_scrape(
  query="latest Linux kernel security changes",
  count=5,
  news=false,
  max_chars=12000,
  extraction_mode="fast"
)
```

The implementation caps this fast path at 5 scraped results and uses bounded parallelism.

---

# Security model

This server performs network access on behalf of an AI agent, so network-boundary checks are treated as a first-class feature.

### URL validation

Only:

```text
http://
https://
```

are accepted.

Userinfo credentials in URLs are rejected.

Hostnames are normalized to ASCII/IDNA form before validation.

### SSRF protection

The server resolves hostnames and accepts only globally routable/public addresses. Localhost and non-public targets are blocked.

Redirect targets are validated again instead of being blindly followed.

### DNS pinning

Resolved public IPs are pinned to the request through libcurl's `CURLOPT_RESOLVE` support. Each thread owns its own `curl_cffi` session so per-session DNS state is not shared unsafely between concurrent requests.

### Response limits

Current hard limits in the implementation include:

```text
Maximum redirects:       5
Maximum results:         50
Maximum query length:    1000 characters
Maximum response body:   4 MiB
Maximum extracted text:  100,000 characters
Maximum domain filters:  5
Maximum batch scrapes:   5
Batch workers:           3
```

These bounds reduce memory pressure, runaway downloads, and unnecessary context growth.

### Retry policy

Only transient HTTP/network conditions are retried. The implementation supports `Retry-After` and uses bounded exponential backoff with jitter.

### Binary-content protection

Known binary content types and common binary magic bytes are rejected before they can become huge, unusable text payloads.

The current server is intended for text-oriented web pages; it does not render JavaScript.

---

# Performance and token-efficiency design

The implementation is deliberately conservative about context size:

- Search output contains structured metadata instead of full page bodies.
- Scraping is explicit rather than automatic for every result.
- `max_chars` is enforced.
- Search responses use a short TTL cache.
- Scraped pages use a separate short TTL cache.
- Canonical URLs improve cache hits and deduplication.
- The batch path uses bounded concurrency instead of unlimited parallel requests.
- Fast extraction is the normal hot path; slower extraction is used only when needed.

This makes the server suitable for agents that need fresh web evidence without filling the context window with irrelevant pages.

## Cache behavior

Current defaults:

```text
Search cache TTL:   120 seconds
Scrape cache TTL:    60 seconds
Search cache size:   64 entries
Scrape cache size:   32 entries
```

Caches are process-local and are not persistent across restarts.

---

# Source quality guidance

The MCP server deliberately returns:

```text
evidence_role = discovery
```

for search results.

After scraping a selected source, the role becomes:

```text
evidence_role = scraped_content
```

Agents should still evaluate:

- primary vs secondary source
- domain authority
- date/freshness
- canonical URL
- whether the page actually supports the claim
- whether another independent source agrees
- whether the site is relevant to the question

A scrape success means text was extracted; it does **not** mean the source is correct.

---

# Important limitations

### Bing HTML is not a stable public API

This project parses the Bing web/news HTML interface. Markup changes can break the search parser without any code change in this repository.

For production systems that require a contractual API, consider using an official search API or another maintained search provider.

### JavaScript-heavy websites

The server does not execute JavaScript. Pages that require client-side rendering may return incomplete or unusable extraction.

### Binary documents

PDFs, images, archives, audio, video, and other binary content are intentionally not treated as ordinary text pages.

### Anti-bot / challenge pages

If Bing returns a challenge or CAPTCHA page, the server raises an error instead of treating the page as a valid empty search result.

### Terms and acceptable use

Use this software responsibly and in accordance with the terms, policies, rate limits, and applicable law of the sites you access.

---

# Development

Install the runtime dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install mcp curl-cffi lxml trafilatura typing-extensions
```

Syntax check:

```bash
python -m py_compile server.py
```

Run locally:

```bash
python server.py
```

For MCP debugging, connect it through an MCP client and inspect tool registration/call errors from the client logs.

## Suggested repository files

For a polished public release, add:

```text
README.md
LICENSE
.gitignore
requirements.txt
server.py
CHANGELOG.md
```

A CI workflow is also recommended once tests are added.

---

# Why "agent-native"

The server does not attempt to decide the final answer.

Its job is to give an agent a clean research substrate:

```text
Discovery
   ↓
Candidate sources
   ↓
URL validation
   ↓
Selected source
   ↓
Content extraction
   ↓
Independent cross-check
   ↓
Agent answer
```

This keeps retrieval and judgment separate.

---

# Roadmap

Possible future additions:

- optional non-Bing search backends
- richer source-type classification
- robots/policy-aware fetching
- HTML extraction fixtures and regression tests
- integration tests against mocked HTTP servers
- package/distribution support
- optional Streamable HTTP transport
- observability metrics
- configurable cache budgets
- more precise article/date extraction
- search-provider failover

---

# Contributing

Issues and pull requests are welcome.

Useful contributions include:

- parser compatibility fixes
- security hardening
- test coverage
- performance improvements
- MCP compatibility
- documentation improvements
- new search backends

Before submitting a pull request:

```bash
python -m py_compile server.py
```

Add regression coverage for parser or security changes where practical.

---

# License

No license is declared by the current source file.

Before making the repository public, choose and add an explicit open-source license (for example, MIT) that you are legally entitled to use.

---

## Repository metadata recommendation

### Recommended repository name

```text
agent-native-web-research-mcp
```

Why this name:

- `agent` targets the AI-agent use case.
- `web-research` captures the core capability.
- `mcp` makes the integration format immediately discoverable.
- The name is more differentiated than generic names such as `mcp-web-search`.

### Recommended GitHub description

```text
Agent-native MCP server for web research: Bing Web/News search, secure URL fetching, SSRF protection, canonicalization, scraping, caching, and bounded parallel extraction.
```

### Recommended topics

```text
mcp
model-context-protocol
mcp-server
ai-agents
ai-agent
web-research
web-search
web-scraping
python
bing-search
bing-news
trafilatura
curl-cffi
ssrf
llm-tools
```

Avoid claiming "viral", "best", "most accurate", or "production-ready" unless you have public benchmark/test evidence supporting those claims.

---

## Documentation references

- OpenCode MCP servers: https://opencode.ai/v2/docs/mcp-servers
- OpenCode configuration: https://dev.opencode.ai/docs/config/
- Pi coding-agent repository: https://github.com/SuperCodeAgents/pi-code
- GitHub repository best practices: https://docs.github.com/en/repositories/creating-and-managing-repositories/best-practices-for-repositories
