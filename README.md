# Free Web Search MCP

Free **MCP web search and scraping server for AI agents**. Uses Bing Web/News search and Trafilatura extraction with URL validation, SSRF protection, caching, retries, and bounded scraping.

## Tools

- `search_web` — web search
- `search_news` — recent news search
- `scrape_url` — scrape one URL
- `search_and_scrape` — search + scrape up to 5 results

## Install on OpenCode

The simplest setup is to keep the repository and MCP server in **one folder**:

```text
~/.config/opencode/mcp-servers/local-scrape/
├── server.py
├── requirements.txt
├── README.md
└── .venv/
```

### 1. Clone directly into the OpenCode MCP folder

```bash
mkdir -p ~/.config/opencode/mcp-servers
git clone https://github.com/digitalninjanv/free-web-search-mcp.git \
  ~/.config/opencode/mcp-servers/local-scrape
```

### 2. Create the Python environment

```bash
cd ~/.config/opencode/mcp-servers/local-scrape

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

### 3. Test the server

```bash
./.venv/bin/python -m py_compile server.py
```

No output means the syntax check passed.

### 4. Configure OpenCode

Open:

```text
~/.config/opencode/opencode.jsonc
```

Add this under `mcp.servers`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "local-scrape": {
        "type": "local",
        "command": [
          "/home/YOUR_USER/.config/opencode/mcp-servers/local-scrape/.venv/bin/python",
          "/home/YOUR_USER/.config/opencode/mcp-servers/local-scrape/server.py"
        ],
        "cwd": "/home/YOUR_USER/.config/opencode/mcp-servers/local-scrape",
        "environment": {
          "PYTHONUNBUFFERED": "1"
        },
        "disabled": false
      }
    }
  }
}
```

Replace `YOUR_USER` with your Linux username.

For example, if your home directory is `/home/najib`:

```jsonc
"command": [
  "/home/najib/.config/opencode/mcp-servers/local-scrape/.venv/bin/python",
  "/home/najib/.config/opencode/mcp-servers/local-scrape/server.py"
]
```

OpenCode V2 uses `mcp.servers.<name>` for MCP servers. Local servers use `type: "local"` and a command array; `cwd` and `environment` are optional process settings. Use `disabled`, not `enabled`. See the [OpenCode MCP documentation](https://opencode.ai/v2/docs/mcp-servers).

### 5. Restart or reload OpenCode

After saving the configuration:

```bash
opencode reload
```

Then check:

```bash
opencode mcp list
```

The server name should be:

```text
local-scrape
```

Its tools are available as:

```text
local-scrape_search_web
local-scrape_search_news
local-scrape_scrape_url
local-scrape_search_and_scrape
```

OpenCode prefixes MCP tool names with the server name. See the [OpenCode MCP documentation](https://opencode.ai/v2/docs/mcp-servers).

## Update

Because the repository lives directly in the OpenCode MCP folder:

```bash
cd ~/.config/opencode/mcp-servers/local-scrape
git pull
./.venv/bin/python -m pip install -r requirements.txt --upgrade
opencode reload
```

## Usage

Recommended research flow:

```text
SEARCH → SELECT / VERIFY → SCRAPE → CROSS-CHECK → ANSWER
```

Search results are discovery data. Agents should select relevant sources, scrape them, and cross-check important claims.

## Security

The server includes:

- public-IP validation
- redirect revalidation
- DNS pinning with `CURLOPT_RESOLVE`
- localhost/non-public target blocking
- response-size limits
- binary-content detection
- bounded retries
- bounded parallel scraping
- short-lived caches

## Notes

- No Bing Search API key is required.
- The scraper does not execute JavaScript.
- Bing HTML markup can change, which may require parser updates.
- Use the service responsibly and follow provider/site terms and rate limits.
