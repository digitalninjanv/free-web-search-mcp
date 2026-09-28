#!/usr/bin/env python3
"""Production local Bing search/scrape MCP.

Based on server-gpt.py, with a deliberately small hot path for search parsing while
keeping the important security/data-integrity controls:
- public-IP validation + DNS pinning via CURLOPT_RESOLVE
- manual redirect validation
- strict URL/query/count validation
- response-size limit + streaming
- transient-only retries with Retry-After support
- persistent curl_cffi session with trust_env=False
- Bing redirect decoding, canonicalization, deduplication
- structurally valid JSON/XML truncation
- Trafilatura fast extraction with bounded balanced fallback + DOM cap
- domain filters and bounded search-and-scrape batching
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import logging
import random
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from typing_extensions import TypedDict

from curl_cffi import CurlOpt, requests as cffi_requests
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import IncompleteRead as CurlIncompleteRead
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from lxml import etree, html as lxml_html
from trafilatura import extract
from trafilatura.deduplication import LRUCache
try:
    from trafilatura.settings import DEFAULT_CONFIG as _TRAF_DEFAULT_CONFIG
except ImportError:  # pragma: no cover - compatibility with older Trafilatura
    _TRAF_DEFAULT_CONFIG = None
try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - compatibility with older MCP SDK layouts
    from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


SERVER_INSTRUCTIONS = (
    "Agent-native web research: SEARCH → SELECT/VERIFY → SCRAPE → CROSS-CHECK → ANSWER. "
    "Search results are structured discovery metadata, not evidence. Prefer primary/authoritative sources, "
    "check canonical URL, domain, date/age and result type before scraping. Scrape only selected URLs. "
    "Use search_and_scrape only as a bounded fast path for clear queries; do not treat every top result as authoritative. "
    "If evidence is insufficient or sources conflict, search again with a narrower query or different domain. "
    "A scrape error means reliable extraction was not obtained; do not silently treat it as evidence."
)

mcp = MCPServer("local-scrape", instructions=SERVER_INSTRUCTIONS)

ALLOWED_SCHEMES = {"http", "https"}
SEARCH_TIMEOUT = 12
SCRAPE_TIMEOUT = 20
MAX_RETRIES = 1
# Backoff eksponensial + "full jitter" (AWS Architecture Blog / Google SRE):
# random.uniform(0, delay) supaya beberapa panggilan yang retry tidak jatuh
# berbarengan dan memperparah beban ke origin.
RETRY_BACKOFF = 0.5
# Total wall-clock budget untuk seluruh percobaan, termasuk jitter/backoff.
# Attempt berikutnya hanya mendapat sisa waktu sehingga retry tidak menggandakan
# timeout dan tidak dapat membekukan klien MCP lebih lama dari budget ini.
RETRY_TIME_BUDGET = 1.0
MIN_RETRY_REMAINING = 0.25
MAX_REDIRECTS = 5
MAX_RESULTS = 50
MAX_QUERY_CHARS = 1000
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CONTENT_CHARS = 100_000
DEFAULT_MAX_CHARS = 25_000
MAX_DOMAIN_FILTERS = 5
MAX_BATCH_SCRAPES = 5
BATCH_MAX_WORKERS = 3
DEFAULT_BATCH_MAX_CHARS = 12_000
BATCH_SCRAPE_TIMEOUT = 15
SCRAPE_CACHE_TTL = 60.0
SCRAPE_CACHE_MAX_ENTRIES = 32
SCRAPE_CACHE_MAX_ENTRY_BYTES = 256 * 1024
EXTRACTION_MODES = {"fast", "balanced", "precision", "recall"}
MAX_TREE_SIZE = 50_000
# Lantai kecil: max_chars hanya untuk memotong output, jadi tidak perlu lantai
# tinggi. Lantai 200 yang dulu memaksa caller melakukan round trip tambahan hanya
# untuk meminta preview pendek.
MIN_MAX_CHARS = 50
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
REDIRECT_STATUS = {301, 302, 303, 307, 308}
TRACKING = {
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "vero_id",
    # Bing menempelkan param ini ke URL artikel; bukan bagian dari URL asli.
    "ocid", "cvid", "form", "sp", "ghc", "ref", "referrer",
}
# NAT64 well-known prefix (RFC 6052). Alamat di dalamnya membungkus IPv4: hash
# IPv4 yang dibungkus itu sendiri harus global, kalau tidak 64:ff9b::7f00:1
# (127.0.0.1) dan 64:ff9b::a9fe:a9fe (IMDS) bisa lolos.
NAT64 = ipaddress.ip_network("64:ff9b::/96")
# Content yang tidak bisa diekstraksi sebagai teks oleh tool ini.
BINARY_CONTENT_TYPES = {
    "application/pdf", "application/zip", "application/gzip", "application/x-gzip",
    "application/x-tar", "application/x-7z-compressed", "application/x-bzip2",
    "application/x-rar-compressed", "application/rtf",
    "application/epub+zip", "application/msword", "application/vnd.ms-",
    "application/vnd.openxmlformats-officedocument",
}
BINARY_CONTENT_PREFIXES = ("image/", "video/", "audio/", "font/")
# application/octet-stream sengaja TIDAK ada di daftar: server sering
# mengirim berkas teks dengan tipe itu. Untuk tipe yang tidak diketahui, magic
# byte yang dipakai sebagai gantinya.
BINARY_MAGIC = (
    b"%PDF", b"PK\x03\x04", b"\x1f\x8b", b"\x89PNG", b"RIFF", b"\xff\xd8\xff",
    b"7z\xbc\xaf", b"Rar!", b"\x00\x00\x01\x00", b"OggS", b"\x42\x4d",
)
# qft=interval="N" -> hasil dalam N terakhir (lihat dokumentasi Bing News).
FRESHNESS_INTERVAL = {"hour": "4", "day": "7", "week": "8", "month": "9"}
# TTL cache respons search: mengurangi hit ke Bing (risiko captcha) untuk query
# yang berulang dalam waktu dekat. Sengaja pendek supaya "berita terbaru" tetap
# segar. HANYA respons valid yang disimpan; halaman challenge/captcha tidak boleh
# di-cache atau akan mengunci query itu selama TTL even setelah Bing melepas blok.
CACHE_TTL = 120.0
CACHE_MAX_ENTRIES = 64
# Batas ukuran satu entri: menjaga total cache parsed-results tetap kecil.
# Dengan 64 entry, hard upper bound payload cache sekitar 32 MB.
CACHE_MAX_ENTRY_BYTES = 512 * 1024
BLOCK_MARKERS = (
    "unusual traffic",
    "automated query",
    "access denied",
    "verify you are human",
    "are you a robot",
)

# Reuse the connection pool; disabling proxy/environment inheritance makes
# security and latency behavior deterministic for a local agent.
# Satu Session per thread: curl_options (DNS pinning via CURLOPT_RESOLVE) adalah
# state level-Session di curl_cffi 0.16.3 (tidak ada curl_options per-request),
# sehingga session global + mutasi sebelum GET() rawan race: request A bisa
# memakai resolve milik request B. Factory ini memberi tiap thread session
# miliknya sendiri -> isolasi setara per-request, pooling tetap per thread.
_TLS = threading.local()


def _get_session():
    sess = getattr(_TLS, "session", None)
    if sess is None:
        sess = cffi_requests.Session(impersonate="chrome", trust_env=False)
        _TLS.session = sess
    return sess


_LOG = logging.getLogger("local-scrape")

# Semua tool di server ini hanya membaca web publik: tidak ada efek samping pada
# sistem lokal maupun remote.
try:
    READ_ONLY = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )
except TypeError:  # compatibility with older SDKs using protocol-style field names
    READ_ONLY = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

# Current MCP Python SDKs support structured output inferred from TypedDict return
# annotations. Keep a small compatibility shim so older MCPServer builds continue
# to register the tool if they do not expose the structured_output argument yet.
def _tool(*, annotations=READ_ONLY, structured: bool = False):
    if structured:
        try:
            return mcp.tool(annotations=annotations, structured_output=True)
        except TypeError:
            pass
    return mcp.tool(annotations=annotations)


_TRAFILATURA_CONFIG = None
if _TRAF_DEFAULT_CONFIG is not None:
    _TRAFILATURA_CONFIG = deepcopy(_TRAF_DEFAULT_CONFIG)
    _TRAFILATURA_CONFIG.setdefault("DEFAULT", {})["MAX_TREE_SIZE"] = str(MAX_TREE_SIZE)


class SearchResult(TypedDict, total=False):
    rank: int
    title: str
    url: str
    canonical_url: str
    domain: str
    snippet: str
    source: str
    age: str
    image: str
    source_type: str
    evidence_role: str


class SearchResponse(TypedDict):
    query: str
    source_type: str
    results: list[SearchResult]


class SearchAndScrapeItem(TypedDict):
    rank: int
    title: str
    url: str
    canonical_url: str
    domain: str
    snippet: str
    content: str
    source: str
    age: str
    source_type: str
    evidence_role: str
    extraction_status: str
    extraction_mode: str
    cached: bool
    final_url: str
    content_chars: int
    error: str


class SearchAndScrapeResponse(TypedDict):
    query: str
    source_type: str
    results: list[SearchAndScrapeItem]

_cache: dict[str, tuple[float, list[dict[str, str]], int]] = {}
_scrape_cache: dict[str, tuple[float, str, int]] = {}
_cache_lock = threading.Lock()
_scrape_cache_lock = threading.Lock()


def _cache_get(key: str) -> list[dict[str, str]] | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        stored_at, payload, _size = hit
        if time.monotonic() - stored_at < CACHE_TTL:
            # Return shallow copies so callers cannot mutate shared cache state.
            return [dict(item) for item in payload]
        del _cache[key]
        return None


def _cache_put(key: str, payload: list[dict[str, str]]) -> None:
    size = len(_dump_json(payload).encode("utf-8"))
    if size > CACHE_MAX_ENTRY_BYTES:
        return
    stored = [dict(item) for item in payload]
    with _cache_lock:
        if key not in _cache and len(_cache) >= CACHE_MAX_ENTRIES:
            del _cache[min(_cache, key=lambda k: _cache[k][0])]
        _cache[key] = (time.monotonic(), stored, size)


def _scrape_cache_key(
    url: str,
    output_format: str,
    include_links: bool,
    max_chars: int,
    extraction_mode: str,
) -> str:
    canonical = _canonical_url(url)
    raw = f"{canonical}\0{output_format}\0{int(include_links)}\0{max_chars}\0{extraction_mode}".encode()
    return hashlib.sha256(raw).hexdigest()


def _scrape_cache_get(key: str) -> str | None:
    with _scrape_cache_lock:
        hit = _scrape_cache.get(key)
        if hit is None:
            return None
        stored_at, payload, _size = hit
        if time.monotonic() - stored_at < SCRAPE_CACHE_TTL:
            return payload
        del _scrape_cache[key]
        return None


def _scrape_cache_put(key: str, payload: str) -> None:
    size = len(payload.encode("utf-8", "replace"))
    if size > SCRAPE_CACHE_MAX_ENTRY_BYTES:
        return
    with _scrape_cache_lock:
        if key not in _scrape_cache and len(_scrape_cache) >= SCRAPE_CACHE_MAX_ENTRIES:
            del _scrape_cache[min(_scrape_cache, key=lambda k: _scrape_cache[k][0])]
        _scrape_cache[key] = (time.monotonic(), payload, size)

# Pre-compiled XPath: menghindari compile cost tiap request (lxml.etree.XPath reuse).
_XP_NEWS_CARDS = etree.XPath('//*[contains(@class,"newsitem")]')
_XP_NEWS_CARDS_FB = etree.XPath('//div[contains(@class,"news-card")]')
_XP_NEWS_TITLE_FB = etree.XPath('.//*[contains(@class,"newscard-title") or contains(@class,"title")][1]')
_XP_A_HREF = etree.XPath('.//a[@href][1]')
_XP_SNIPPET = etree.XPath('.//*[contains(@class,"snippet")][1]')
_XP_NEWS_AGE = etree.XPath('.//div[contains(@class,"source")]//span[@tabindex="0"][1]')
_XP_NEWS_IMG = etree.XPath('.//img[@data-src-hq][1]')
_XP_WEB_ITEMS = etree.XPath('//li[contains(concat(" ", normalize-space(@class), " "), " b_algo ")]')
_XP_WEB_FB = etree.XPath('//h2/a[@href]')
_XP_H2_A = etree.XPath('.//h2/a[@href][1]')
_XP_CAPTION_P = etree.XPath('.//div[contains(@class,"b_caption")]//p[1]')


@lru_cache(maxsize=1024)
def _resolve_for(hostname: str, port: int, ips: tuple[str, ...]) -> tuple[str, ...]:
    """Format entri CURLOPT_RESOLVE; di-cache karena (host, port, ips) berulang."""
    return tuple(f"{hostname}:{port}:{('[' + ip + ']') if ':' in ip else ip}" for ip in ips)


class _HTTPStatusError(RuntimeError):
    def __init__(self, code: int, retry_after: float | None = None):
        self.status_code = code
        self.retry_after = retry_after
        super().__init__(f"HTTP {code}")


class _TooLarge(RuntimeError):
    pass


class _BinaryContent(RuntimeError):
    def __init__(self, content_type: str):
        self.content_type = content_type
        super().__init__(content_type)


def _is_binary_content_type(value: str | None) -> bool:
    if not value:
        return False
    ct = value.split(";", 1)[0].strip().lower()
    return ct.startswith(BINARY_CONTENT_PREFIXES) or any(
        ct == known or ct.startswith(known) for known in BINARY_CONTENT_TYPES
    )


def _is_binary_content_type_or_magic(content_type: str | None, raw: bytes) -> bool:
    """Deteksi konten biner dari content-type, atau dari magic byte bila tipe
    tidak diketahui (mis. 'application/octet-stream')."""
    if _is_binary_content_type(content_type):
        return True
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in {"", "application/octet-stream", "binary/octet-stream", "application/unknown"}:
        head = raw[:1024]
        return head.startswith(BINARY_MAGIC) or b"\x00" in head
    return False


@lru_cache(maxsize=2048)
def _host_ascii(host: str) -> str:
    raw = host.split("%", 1)[0]
    try:
        ipaddress.ip_address(raw)
        return raw.lower()
    except ValueError:
        try:
            return host.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            raise ToolError(f"Hostname tidak valid: {host!r}") from None


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True hanya untuk alamat yang secara global bisa di-routing.

    `is_global` mengikuti IANA Special-Purpose Address Registry, sehingga
    64:ff9b::/96 (NAT64, Globally Reachable=True) tetap Lolos sementara
    64:ff9b:1::/48, 100::/64, 2001:db8::/32, 2002::/16, fc00::/7, fe80::/10,
    CGNAT, TEST-NET, dan loopback tetap diblokir.
    """
    if ip.version == 6 and ip in NAT64:
        # De-embed IPv4 (RFC 6052) lalu validasi address aslinya juga.
        return ipaddress.IPv4Address(ip.packed[12:16]).is_global
    return ip.is_global


def _public_ips(host: str) -> list[str]:
    """Subset IP global untuk host; error hanya jika tidak ada satupun.

    Penting: host dual-stack sering juga mengembalikan alamat NAT64/6to4 atau
    alias lain. Alamat seperti itu harus DILEWATI, bukan membuat seluruh host
    ditolak, selama host itu punya minimal satu IP global yang bisa dipakai.
    """
    host = _host_ascii(host)
    if host == "localhost":
        raise ToolError("Target localhost diblokir untuk mencegah SSRF.")

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ToolError(f"DNS gagal untuk host '{host}'.") from None

    out: list[str] = []
    blocked: list[str] = []
    seen: set[str] = set()

    for info in infos:
        raw = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not _is_public_ip(ip):
            if raw not in blocked:
                blocked.append(raw)
            continue
        if raw not in seen:
            seen.add(raw)
            out.append(raw)

    if not out:
        detail = ", ".join(blocked[:4]) if blocked else "tidak ada"
        raise ToolError(
            f"Target '{host}' tidak punya alamat IP publik yang bisa dipakai "
            f"(non-publik: {detail})."
        )
    return out


def _validate_url(url: str) -> tuple[str, list[str]]:
    if not isinstance(url, str) or not url.strip():
        raise ToolError("URL wajib diisi.")

    p = urlparse(url.strip())
    scheme = p.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ToolError(f"Scheme '{p.scheme}' tidak diizinkan; hanya http/https.")
    if not p.hostname:
        raise ToolError("URL tidak valid: hostname kosong.")
    if p.username is not None or p.password is not None:
        raise ToolError("URL dengan username/password tidak didukung.")
    try:
        port = p.port
    except ValueError:
        raise ToolError("URL tidak valid: port tidak valid.") from None

    host = _host_ascii(p.hostname)
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    normalized = urlunparse((scheme, netloc, p.path, "", p.query, ""))
    return normalized, _public_ips(host)


@lru_cache(maxsize=2048)
def _bing_redirect(url: str) -> str:
    try:
        p = urlparse(url)
        host = _host_ascii(p.hostname or "")
        if not (host == "bing.com" or host.endswith(".bing.com")) or "/ck/a" not in p.path.lower():
            return url
        encoded = next(
            (v for k, v in parse_qsl(p.query, keep_blank_values=True) if k == "u"),
            "",
        )
        if not encoded.startswith("a1"):
            return url
        raw = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
        decoded = base64.urlsafe_b64decode(raw).decode("utf-8", "ignore")
        return decoded if decoded.startswith(("http://", "https://")) else url
    except (ValueError, UnicodeError):
        return url


@lru_cache(maxsize=2048)
def _canonical_url(url: str) -> str:
    p = urlparse(_bing_redirect(url.strip()))
    if p.scheme.lower() not in ALLOWED_SCHEMES or not p.hostname:
        return url
    scheme, host = p.scheme.lower(), _host_ascii(p.hostname)
    try:
        port = p.port
    except ValueError:
        port = None
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc += f":{port}"
    query = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        kl = k.lower()
        if not kl.startswith("utm_") and kl not in TRACKING:
            query.append((k, v))
    return urlunparse((scheme, netloc, p.path or "/", "", urlencode(query, doseq=True), ""))


def _usable_result_url(url: str) -> str | None:
    canonical = _canonical_url(url)
    p = urlparse(canonical)
    if p.scheme.lower() not in ALLOWED_SCHEMES or not p.hostname:
        return None
    host = _host_ascii(p.hostname)
    if host == "bing.com" or host.endswith(".bing.com"):
        return None
    return canonical


def _dedupe(results: list[dict], count: int) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in results:
        href = raw.get("url", "")
        if not isinstance(href, str) or not href:
            continue
        url = _usable_result_url(href)
        if not url or url in seen:
            continue
        seen.add(url)
        item = dict(raw)
        item["url"] = url
        out.append(item)
        if len(out) >= count:
            break
    return out


def _enrich_search_results(results: list[dict], source_type: str) -> list[SearchResult]:
    """Attach low-cost provenance metadata for model-side source selection.

    These fields are descriptive, not a source-quality score: the agent must still
    decide which sources are authoritative and cross-check them.
    """
    out: list[SearchResult] = []
    for rank, raw in enumerate(results, 1):
        url = str(raw.get("url", ""))
        canonical = _canonical_url(url) if url else ""
        host = _host_ascii(urlparse(canonical).hostname or "") if canonical else ""
        item: SearchResult = {
            "rank": rank,
            "title": str(raw.get("title", "")),
            "url": url,
            "canonical_url": canonical,
            "domain": host,
            "snippet": str(raw.get("snippet", "")),
            "source_type": source_type,
            "evidence_role": "discovery",
        }
        for key in ("source", "age", "image"):
            if raw.get(key):
                item[key] = str(raw[key])
        out.append(item)
    return out


def _retry_after(headers) -> float | None:
    value = headers.get("retry-after") if headers else None
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 5.0))
    except (TypeError, ValueError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(value))
        if dt.tzinfo is None:
            return None
        seconds = dt.timestamp() - time.time()
        return max(0.0, min(seconds, 5.0))
    except (TypeError, ValueError, OverflowError):
        return None


def _fetch_once(
    url: str, timeout: float, *, _prevalidated: tuple[str, list[str]] | None = None
) -> tuple[bytes, str]:
    # _fetch sudah validasi sekali (1x DNS); pakai ulang agar tidak getaddrinfo 2x.
    # curl_cffi 0.16.3 tidak mendukung trust_env/curl_options per-request
    # (hanya level-Session). Session diambil dari _get_session() (satu per thread)
    # sehingga mutasi curl_options + GET() terisolasi antar request konkuren.
    # trust_env=False sudah di-set saat Session dibuat.
    current, ips = _prevalidated if _prevalidated is not None else _validate_url(url)

    for _ in range(MAX_REDIRECTS + 1):
        p = urlparse(current)
        port = p.port or (443 if p.scheme == "https" else 80)
        sess = _get_session()
        sess.curl_options = {CurlOpt.RESOLVE: list(_resolve_for(p.hostname or "", port, tuple(ips)))}

        r = sess.get(
            current,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            if r.status_code in REDIRECT_STATUS:
                location = r.headers.get("location")
                if not location:
                    raise RuntimeError(f"HTTP {r.status_code} tanpa header Location")
                current, ips = _validate_url(urljoin(current, location))
                continue

            if r.status_code >= 400:
                raise _HTTPStatusError(r.status_code, _retry_after(r.headers))

            content_type = r.headers.get("content-type")
            # Reject known binary types before downloading the body. For generic
            # octet-stream, magic-byte detection still happens on the first chunk.
            if _is_binary_content_type(content_type):
                raise _BinaryContent(content_type)

            cl = r.headers.get("content-length")
            try:
                if cl and int(cl) > MAX_RESPONSE_BYTES:
                    raise _TooLarge()
            except ValueError:
                pass

            chunks: list[bytes] = []
            total = 0
            first_chunk = True
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                if first_chunk:
                    first_chunk = False
                    if _is_binary_content_type_or_magic(content_type, chunk):
                        raise _BinaryContent(content_type or "application/octet-stream")
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise _TooLarge()
                chunks.append(chunk)
            body = b"".join(chunks)

            # Tanpa guard ini PDF/gambar jadi puluhan ribu karakter mojibake
            # yang membakar budget token tanpa informasi berguna.
            if _is_binary_content_type_or_magic(content_type, body):
                raise _BinaryContent(content_type or "application/octet-stream")
            return body, current
        finally:
            try:
                r.close()
            except Exception:
                pass

    raise RuntimeError(f"Terlalu banyak redirect (>{MAX_REDIRECTS}).")


def _fetch(
    url: str,
    *,
    timeout: int,
    retries: int = MAX_RETRIES,
    prevalidated: tuple[str, list[str]] | None = None,
) -> tuple[bytes, str]:
    prevalidated = prevalidated or _validate_url(url)
    last = None
    deadline = time.monotonic() + float(timeout) * RETRY_TIME_BUDGET
    attempts = 0

    for attempt in range(retries + 1):
        retry_after = None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts = attempt + 1
        try:
            # The per-attempt timeout is capped by the remaining total retry budget.
            # This prevents a second full timeout after a slow first attempt.
            attempt_timeout = min(float(timeout), remaining)
            return _fetch_once(
                url,
                attempt_timeout,
                _prevalidated=prevalidated,
            )
        except ToolError:
            raise
        except _TooLarge as exc:
            raise ToolError(f"Response terlalu besar; batas {MAX_RESPONSE_BYTES} bytes.") from exc
        except _BinaryContent as exc:
            raise ToolError(
                f"Konten {exc.content_type} tidak bisa diekstraksi sebagai teks oleh tool ini. "
                "Untuk PDF/gambar/dokumen pakai firecrawl_scrape (parser pdf) atau firecrawl_parse."
            ) from exc
        except _HTTPStatusError as exc:
            last = exc
            if exc.status_code not in RETRYABLE_STATUS or attempt >= retries:
                raise ToolError(f"Gagal mengambil {url}: HTTP {exc.status_code}.") from exc
            delay = exc.retry_after if exc.retry_after is not None else RETRY_BACKOFF * (2**attempt)
            retry_after = exc.retry_after
        except (CurlConnectionError, CurlTimeout, CurlIncompleteRead) as exc:
            last = exc
            if attempt >= retries:
                break
            delay = RETRY_BACKOFF * (2**attempt)
        except Exception as exc:
            # Programming/parse/validation errors should not be retried blindly.
            raise ToolError(f"Gagal mengambil {url}: {exc}") from exc

        remaining = deadline - time.monotonic()
        if remaining <= MIN_RETRY_REMAINING:
            break
        if delay >= remaining:
            break
        pause = (
            min(delay, remaining - MIN_RETRY_REMAINING)
            if retry_after is not None
            else min(random.uniform(0.0, delay), remaining - MIN_RETRY_REMAINING)
        )
        if pause > 0:
            _LOG.debug("retry %d/%d for %s after %.2fs", attempt + 1, retries, url, pause)
            time.sleep(pause)

    raise ToolError(f"Gagal mengambil {url} setelah {attempts} percobaan: {last}")


def _query(value: str) -> str:
    if not isinstance(value, str):
        raise ToolError("query harus berupa string.")
    value = value.strip()
    if not value:
        raise ToolError("query tidak boleh kosong.")
    if len(value) > MAX_QUERY_CHARS:
        raise ToolError(f"query maksimum {MAX_QUERY_CHARS} karakter.")
    return value


def _count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError("count harus integer >= 1.")
    return min(MAX_RESULTS, value)


def _max_chars(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < MIN_MAX_CHARS:
        raise ToolError(f"max_chars harus integer >= {MIN_MAX_CHARS}.")
    return min(MAX_CONTENT_CHARS, value)


def _domains(value: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > MAX_DOMAIN_FILTERS:
        raise ToolError(f"domains harus list maksimal {MAX_DOMAIN_FILTERS} hostname.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ToolError("setiap domain harus berupa string non-kosong.")
        item = item.strip().lower().rstrip(".")
        if len(item) > 253 or any(ch in item for ch in "/?#@ \t"):
            raise ToolError(f"domain tidak valid: {item!r}")
        host = _host_ascii(item)
        if ":" in host and not ipaddress.ip_address(host).version == 4:
            raise ToolError("IPv6 tidak didukung sebagai domain filter.")
        if host not in out:
            out.append(host)
    return tuple(out)


def _extraction_mode(value: str) -> str:
    if not isinstance(value, str):
        raise ToolError("extraction_mode harus berupa string.")
    value = value.strip().lower()
    if value not in EXTRACTION_MODES:
        raise ToolError("extraction_mode harus fast, balanced, precision, atau recall.")
    return value


def _freshness(value: str) -> str:
    """'hour'|'day'|'week'|'month' -> nilai qft=interval milik Bing News."""
    if not isinstance(value, str):
        raise ToolError("freshness harus berupa string.")
    value = value.strip().lower()
    if not value:
        return ""
    if value not in FRESHNESS_INTERVAL:
        raise ToolError("freshness harus salah satu dari: hour, day, week, month.")
    return value


def _market(value: str) -> str:
    """Kode pasar Bing, mis. 'id-ID', 'en-US', 'id'."""
    if not isinstance(value, str):
        raise ToolError("market harus berupa string.")
    value = value.strip()
    if not value:
        return ""
    if len(value) > 10 or not all(c.isalnum() or c == "-" for c in value):
        raise ToolError("market tidak valid; contoh yang benar: 'id-ID' atau 'en-US'.")
    return value


def _blocked(html: str) -> bool:
    x = html.lower()
    if any(marker in x for marker in BLOCK_MARKERS):
        return True
    return "captcha" in x and any(term in x for term in ("challenge", "verify", "robot", "security"))


def _text(el) -> str:
    if isinstance(el, list):
        el = el[0] if el else None
    return " ".join(el.itertext()).strip() if el is not None else ""


# Hot-path parser: one direct XPath per result type, then shared canonicalization.
# Avoids extra fallback scans unless Bing changes its markup.
def _parse_news(html: str, count: int) -> list[dict]:
    if not html.strip():
        return []
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return []

    cards = _XP_NEWS_CARDS(tree)
    if not cards:
        cards = _XP_NEWS_CARDS_FB(tree)

    out: list[dict] = []
    for card in cards:
        title = (card.get("data-title") or card.get("title") or "").strip()
        if not title:
            title = _text(_XP_NEWS_TITLE_FB(card))

        href = (card.get("url") or card.get("data-url") or "").strip()
        if not href:
            a = _XP_A_HREF(card)
            href = a[0].get("href", "") if a else ""
        if not title or not href:
            continue

        href = urljoin("https://www.bing.com/", href)
        source = (card.get("data-author") or card.get("author") or "").strip()
        if not source:
            try:
                source = _host_ascii(urlparse(_canonical_url(href)).hostname or "")
            except ToolError:
                source = ""

        # Bing hanya menampilkan waktu relatif, di aria-label span tabindex="0"
        # (mis. "6 hours ago" / "6 jam yang lalu"); teksnya hanya "6h"/"6j".
        age_el = _XP_NEWS_AGE(card)
        age = ""
        if age_el:
            age = (age_el[0].get("aria-label") or _text(age_el)).strip()
        img = _XP_NEWS_IMG(card)
        image = urljoin("https://www.bing.com/", img[0].get("data-src-hq", "")) if img else ""

        out.append({
            "title": title,
            "url": href,
            "snippet": _text(_XP_SNIPPET(card)),
            "source": source,
            "age": age,
            "image": image,
        })
        if len(out) >= count:
            break
    return _dedupe(out, count)


def _parse_web(html: str, count: int) -> list[dict]:
    if not html.strip():
        return []
    try:
        tree = lxml_html.fromstring(html)
    except (etree.ParserError, ValueError):
        return []

    items = _XP_WEB_ITEMS(tree)
    if not items:
        # Small compatibility fallback for markup changes.
        items = _XP_WEB_FB(tree)

    out: list[dict] = []
    for item in items:
        # Bing menandai unit iklan dengan class b_ad pada <li>. Catatan: di 8 SERP
        # uji (termasuk query komersial high-CPC) Bing tidak menyajikan iklan
        # sama sekali ke klien ini, jadi guard ini belum pernah terpicu. Aman:
        # class item organik selalu persis "b_algo", tidak pernah "b_ad".
        if "b_ad" in item.get("class", "").split():
            continue
        if item.tag == "a":
            a = item
            title = _text(a)
            href = a.get("href", "")
            snippet = ""
        else:
            a = _XP_H2_A(item)
            if not a:
                continue
            a = a[0]
            title = _text(a)
            href = a.get("href", "")
            snippet = _text(_XP_CAPTION_P(item))

        if not title or not href:
            continue
        out.append({
            "title": title,
            "url": urljoin("https://www.bing.com/", href),
            "snippet": snippet,
        })
        if len(out) >= count:
            break
    return _dedupe(out, count)


def _dump_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _truncate_plain(value: str, limit: int = MAX_CONTENT_CHARS) -> str:
    if len(value) <= limit:
        return value
    note = f"\n\n[...dipotong, total asli {len(value)} karakter]"
    return value[: max(0, limit - len(note))] + note


def _truncate_json(value: str, limit: int = MAX_CONTENT_CHARS) -> str:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        data, text = {"truncated": True, "text": ""}, value
    else:
        out = _dump_json(data)
        if len(out) <= limit:
            return out
        text = data.get("text", "") if isinstance(data, dict) and isinstance(data.get("text"), str) else ""
        data = {k: data[k] for k in ("title", "url", "date", "author") if isinstance(data, dict) and k in data}
        data.update(truncated=True, text=text)

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        data["text"] = text[:mid]
        if len(_dump_json(data)) <= limit:
            lo = mid
        else:
            hi = mid - 1
    data["text"] = text[:lo]
    return _dump_json(data)


def _truncate_xml(value: str, limit: int = MAX_CONTENT_CHARS) -> str:
    try:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)
        root = etree.fromstring(value.encode("utf-8", "replace"), parser=parser)
        normal = etree.tostring(root, encoding="unicode")
        if len(normal) <= limit:
            return normal
    except (etree.XMLSyntaxError, UnicodeError):
        pass

    wrapper = etree.Element("document")
    text_node = etree.SubElement(wrapper, "text")
    lo, hi = 0, min(len(value), limit)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        text_node.text = value[:mid]
        if len(etree.tostring(wrapper, encoding="unicode")) <= limit:
            lo = mid
        else:
            hi = mid - 1
    text_node.text = value[:lo]
    return etree.tostring(wrapper, encoding="unicode")


def _fallback(raw: bytes, url: str, fmt: str, limit: int = MAX_CONTENT_CHARS) -> str:
    text = raw.decode("utf-8", "replace")
    note = "Ekstraksi Trafilatura gagal; data mentah dikembalikan."
    if fmt == "json":
        return _truncate_json(_dump_json({"url": url, "error": note, "text": text}), limit)
    if fmt == "xml":
        root = etree.Element("document", url=url)
        etree.SubElement(root, "error").text = note
        etree.SubElement(root, "text").text = text
        return _truncate_xml(etree.tostring(root, encoding="unicode"), limit)
    return _truncate_plain(f"[catatan: {note}]\n\n{text}", limit)


def _scrape_url_impl(
    url: str,
    *,
    output_format: str = "markdown",
    include_links: bool = True,
    max_chars: int = DEFAULT_MAX_CHARS,
    raw_html: bool = False,
    extraction_mode: Literal["fast", "balanced", "precision", "recall"] = "fast",
    timeout: int = SCRAPE_TIMEOUT,
    use_cache: bool = True,
) -> str:
    if output_format not in {"markdown", "txt", "xml", "json"}:
        raise ToolError("output_format harus markdown, txt, xml, atau json.")
    limit = _max_chars(max_chars)
    extraction_mode = _extraction_mode(extraction_mode)
    original, ips = _validate_url(url)

    cache_key = None
    if use_cache and not raw_html:
        cache_key = _scrape_cache_key(
            original, output_format, include_links, limit, extraction_mode
        )
        cached = _scrape_cache_get(cache_key)
        if cached is not None:
            return cached

    raw, final_url = _fetch(
        original,
        timeout=timeout,
        prevalidated=(original, ips),
    )
    if raw_html:
        return _truncate_plain(raw.decode("utf-8", "replace"), limit)

    kwargs = dict(
        url=final_url,
        output_format=output_format,
        include_links=include_links,
        include_formatting=output_format != "json",
        include_comments=False,
        include_tables=True,
        deduplicate=LRUCache(),
        with_metadata=(output_format == "json"),
        date_extraction_params={"extensive_search": True} if output_format == "json" else None,
    )
    if extraction_mode == "fast":
        kwargs["fast"] = True
    elif extraction_mode == "precision":
        kwargs["favor_precision"] = True
    elif extraction_mode == "recall":
        kwargs["favor_recall"] = True
    if _TRAFILATURA_CONFIG is not None:
        kwargs["config"] = _TRAFILATURA_CONFIG

    try:
        result = extract(raw, **kwargs)
    except (TypeError, ValueError):
        result = None

    # Fast is the normal hot path. Escalate only when nothing useful was extracted.
    if not result and extraction_mode == "fast":
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("fast", None)
        try:
            result = extract(raw, **fallback_kwargs)
        except (TypeError, ValueError):
            result = None

    if not result:
        raise ToolError(
            "Konten berhasil diambil tetapi ekstraksi utama gagal. "
            "Pilih URL artikel lain atau gunakan raw_html=true hanya untuk inspeksi markup."
        )

    if output_format == "json":
        output = _truncate_json(result, limit)
    elif output_format == "xml":
        output = _truncate_xml(result, limit)
    else:
        output = _truncate_plain(result, limit)

    if cache_key is not None:
        _scrape_cache_put(cache_key, output)
    return output


@_tool()
def scrape_url(
    url: str,
    output_format: str = "markdown",
    include_links: bool = True,
    max_chars: int = DEFAULT_MAX_CHARS,
    raw_html: bool = False,
    extraction_mode: Literal["fast", "balanced", "precision", "recall"] = "fast",
) -> str:
    """Langkah terakhir riset: ekstrak 1 URL yang sudah dipilih dan divalidasi. Tidak menjalankan JavaScript."""
    return _scrape_url_impl(
        url,
        output_format=output_format,
        include_links=include_links,
        max_chars=max_chars,
        raw_html=raw_html,
        extraction_mode=extraction_mode,
    )


def _search_url(
    query: str,
    count: int,
    news: bool,
    freshness: str = "",
    market: str = "",
    domains: tuple[str, ...] = (),
) -> str:
    if domains:
        domain_filter = " OR ".join(f"site:{domain}" for domain in domains)
        query = f"({query}) ({domain_filter})"
    params = {"q": query, "count": str(count)}
    if news:
        # Default news: urut dari yang paling baru, bukan "best match".
        params["qft"] = f'interval="{FRESHNESS_INTERVAL[freshness]}"' if freshness else 'sortbydate="1"'
        params["form"] = "YFNR"
    if market:
        params["setmkt"] = market
        params["setlang"] = market.split("-")[0]
    return "https://www.bing.com/" + ("news/search?" if news else "search?") + urlencode(params)


@_tool(structured=True)
def search_news(
    query: str,
    count: int = 10,
    freshness: str = "",
    market: str = "",
    domains: list[str] | None = None,
) -> SearchResponse:
    """Cari berita terbaru; hasil terstruktur untuk memilih sumber sebelum scrape_url."""
    query, count = _query(query), _count(count)
    freshness, market = _freshness(freshness), _market(market)
    domain_list = _domains(domains)
    url = _search_url(query, count, True, freshness, market, domain_list)
    results = _cache_get(url)
    html = ""
    if results is None:
        raw, _ = _fetch(url, timeout=SEARCH_TIMEOUT)
        html = raw.decode("utf-8", "replace")
        results = _parse_news(html, count)
    if not results:
        if html and _blocked(html):
            raise ToolError("Bing kemungkinan mengembalikan challenge/captcha, bukan benar-benar 0 hasil.")
        return {"query": query, "source_type": "news", "results": []}
    if html:
        _cache_put(url, results)
    return {"query": query, "source_type": "news", "results": _enrich_search_results(results, "news")}


@_tool(structured=True)
def search_web(
    query: str,
    count: int = 10,
    market: str = "",
    domains: list[str] | None = None,
) -> SearchResponse:
    """Cari sumber web; hasil terstruktur untuk memilih dan memvalidasi URL sebelum scrape_url."""
    query, count = _query(query), _count(count)
    domain_list = _domains(domains)
    url = _search_url(query, count, False, market=_market(market), domains=domain_list)
    results = _cache_get(url)
    html = ""
    if results is None:
        raw, _ = _fetch(url, timeout=SEARCH_TIMEOUT)
        html = raw.decode("utf-8", "replace")
        results = _parse_web(html, count)
    if not results:
        if html and _blocked(html):
            raise ToolError("Bing kemungkinan mengembalikan challenge/captcha, bukan benar-benar 0 hasil.")
        return {"query": query, "source_type": "web", "results": []}
    if html:
        _cache_put(url, results)
    return {"query": query, "source_type": "web", "results": _enrich_search_results(results, "web")}


@_tool(structured=True)
def search_and_scrape(
    query: str,
    count: int = 5,
    news: bool = False,
    freshness: str = "",
    market: str = "",
    domains: list[str] | None = None,
    output_format: str = "markdown",
    include_links: bool = True,
    max_chars: int = DEFAULT_BATCH_MAX_CHARS,
    extraction_mode: Literal["fast", "balanced", "precision", "recall"] = "fast",
) -> SearchAndScrapeResponse:
    """Fast path: structured search lalu scrape terbatas secara paralel; tetap verifikasi sumber sebelum menyimpulkan."""
    count = min(MAX_BATCH_SCRAPES, _count(count))
    domain_list = list(_domains(domains))
    max_chars = _max_chars(max_chars)
    extraction_mode = _extraction_mode(extraction_mode)
    if not isinstance(output_format, str):
        raise ToolError("output_format harus berupa string.")
    output_format = output_format.strip().lower()
    if output_format not in {"markdown", "txt", "xml", "json"}:
        raise ToolError("output_format harus markdown, txt, xml, atau json.")

    search_result = (
        search_news(query, count=count, freshness=freshness, market=market, domains=domain_list)
        if news
        else search_web(query, count=count, market=market, domains=domain_list)
    )
    search_results = search_result["results"]
    output: list[SearchAndScrapeItem | None] = [None] * len(search_results)

    def scrape_one(index: int, item: SearchResult) -> tuple[int, SearchAndScrapeItem]:
        base: SearchAndScrapeItem = {
            "rank": int(item.get("rank", index + 1)),
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
            "canonical_url": str(item.get("canonical_url", item.get("url", ""))),
            "domain": str(item.get("domain", "")),
            "snippet": str(item.get("snippet", "")),
            "content": "",
            "source": str(item.get("source", "")),
            "age": str(item.get("age", "")),
            "source_type": str(item.get("source_type", "news" if news else "web")),
            "evidence_role": "discovery",
            "extraction_status": "not_attempted",
            "extraction_mode": extraction_mode,
            "cached": False,
            "final_url": "",
            "content_chars": 0,
            "error": "",
        }
        try:
            canonical = base["canonical_url"]
            cache_key = _scrape_cache_key(canonical, output_format, include_links, max_chars, extraction_mode)
            cached = _scrape_cache_get(cache_key)
            if cached is not None:
                content = cached
                base["cached"] = True
                base["final_url"] = canonical
            else:
                content = _scrape_url_impl(
                    canonical,
                    output_format=output_format,
                    include_links=include_links,
                    max_chars=max_chars,
                    extraction_mode=extraction_mode,
                    timeout=BATCH_SCRAPE_TIMEOUT,
                )
                base["final_url"] = canonical
            base["content"] = content
            base["content_chars"] = len(content)
            base["extraction_status"] = "extracted"
            base["evidence_role"] = "scraped_content"
        except Exception as exc:
            base["extraction_status"] = "failed"
            base["error"] = str(exc)
        return index, base

    workers = min(BATCH_MAX_WORKERS, len(search_results))
    if workers:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
            futures = [pool.submit(scrape_one, i, item) for i, item in enumerate(search_results)]
            for future in as_completed(futures):
                index, item = future.result()
                output[index] = item

    return {
        "query": query,
        "source_type": "news" if news else "web",
        "results": [item for item in output if item is not None],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
