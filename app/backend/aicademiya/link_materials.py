"""Public, bounded Link extraction. No credentials, cookies or provider calls.

An injected httpx transport is for explicitly labelled network fixtures. Real
fetches pin each validated DNS result to the connection, retaining Host and TLS
SNI, so a second DNS lookup cannot redirect a request to a private address.
"""
from html.parser import HTMLParser
import ipaddress
import re
import socket
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_EXCERPT = 50000
MAX_REDIRECTS = 5
FETCH_SECONDS = 25
_DOI = re.compile(r"10\.\d{4,9}/[^\s<>\"#?]+", re.IGNORECASE)


def _public_ip(value):
    address = ipaddress.ip_address(value)
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def normalize_link(value: str) -> str:
    """Validate HTTP(S) URLs or exact DOI identifiers; never repair identifiers.

    Whitespace surrounding a form value is ignored, but whitespace, malformed
    escapes, credentials and local targets inside the value are rejected.
    DNS resolution occurs at fetch time, not while authoring a link.
    """
    if not isinstance(value, str):
        raise ValueError("Link must be a URL or DOI string")
    value = value.strip()
    if not value or len(value) > 4000 or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ValueError("Invalid URL or DOI")
    if value.lower().startswith("doi:"):
        value = value[4:]
        if not _DOI.fullmatch(value):
            raise ValueError("Invalid DOI")
        return "https://doi.org/" + value
    if value.startswith("10."):
        if not _DOI.fullmatch(value):
            raise ValueError("Invalid DOI")
        return "https://doi.org/" + value
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("Malformed URL escape")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parts.scheme.lower() not in {"http", "https"} or not host or parts.username is not None or parts.password is not None:
        raise ValueError("Use a public HTTP(S) URL without credentials")
    if port not in (None, 80, 443):
        raise ValueError("Only public HTTP(S) ports 80 and 443 are supported")
    if host.endswith(".."):
        raise ValueError("Invalid DNS name")
    host = host.lower().rstrip(".")
    if "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")):
        raise ValueError("Private/local URL targets are not allowed")
    try:
        if not _public_ip(host):
            raise ValueError("Private/local URL targets are not allowed")
    except ValueError as exc:
        # Non-IP hosts must be real DNS names, not legacy numeric IP spellings.
        if ":" in host or re.fullmatch(r"[0-9.]+|0x[0-9a-f]+", host, re.I):
            raise ValueError("Invalid or non-public IP target") from exc
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as err:
            raise ValueError("Invalid host") from err
        if "." not in ascii_host or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in ascii_host.split(".")):
            raise ValueError("Use a public DNS name") from exc
    if host in {"doi.org", "dx.doi.org"}:
        identifier = unquote(parts.path.lstrip("/"))
        if not _DOI.fullmatch(identifier) or parts.query or parts.fragment:
            raise ValueError("Invalid DOI URL")
        # Preserve DOI case and punctuation, rather than guessing a repaired DOI.
        return "https://doi.org/" + parts.path.lstrip("/")
    return value


def _resolve_public(url):
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Public target could not be resolved") from exc
    addresses = list(dict.fromkeys(result[4][0] for result in results))
    if not addresses or any(not _public_ip(address) for address in addresses):
        raise ValueError("Target resolves to a non-public address; fetch refused")
    return addresses[0]


class _HTMLText(HTMLParser):
    _ignored = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "template"}
    _breaks = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "li", "br", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.primary = []
        self.title = []
        self.description = ""
        self.paywall = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in {"description", "og:description", "dc.description", "citation_abstract"} and not self.description:
                self.description = attrs.get("content", "")
            if name in {"citation_title", "og:title"} and not self.title:
                self.title.append(attrs.get("content", ""))
        if tag not in {"meta", "link", "img", "input", "hr", "br", "source", "wbr", "area", "base", "embed", "param"}:
            self.stack.append(tag)
        if tag in self._breaks:
            self.text.append("\n")
            self.primary.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
        if tag in self._breaks:
            self.text.append("\n")
            self.primary.append("\n")

    def handle_data(self, data):
        if "title" in self.stack:
            self.title.append(data)
        elif not any(tag in self._ignored | {"head"} for tag in self.stack):
            self.text.append(data)
            if "article" in self.stack or "main" in self.stack:
                self.primary.append(data)


def _clean(text):
    return "\n".join(line for line in (re.sub(r"\s+", " ", line).strip() for line in text.splitlines()) if line)


def _extract_body(body, content_type, encoding):
    if "pdf" in content_type or body.startswith(b"%PDF-"):
        import pymupdf
        with pymupdf.open(stream=body, filetype="pdf") as document:
            if len(document) > 200:
                raise ValueError("Public PDF exceeds the 200-page extraction limit")
            title = document.metadata.get("title") or ""
            pieces = [page.get_text(sort=True) for page in document]
            empty = sum(not piece.strip() for piece in pieces)
        return title, _clean("\n".join(pieces)), "PDF has image-only pages; no OCR was performed." if empty else None
    text = body.decode(encoding or "utf-8", errors="replace")
    if "html" in content_type or re.match(r"\s*(?:<!doctype\s+html|<html|<head)", text, re.I):
        parser = _HTMLText()
        parser.feed(text)
        primary = _clean("".join(parser.primary))
        excerpt = primary if len(primary) >= 100 else _clean("".join(parser.text))
        warning = None
        if re.search(r"purchase (?:this |the )?article|subscribe to (?:read|access)|sign in to (?:read|access)|access (?:this |the )?(?:article|full.text).{0,30}(?:purchase|subscription)|paywall|institutional (?:login|access)", text, re.I):
            warning = "Possible paywall/login restriction; only the returned public content was extracted, not authenticated full text."
        if len(excerpt) < 100:
            if parser.description:
                excerpt = _clean(parser.description + ("\n" + excerpt if excerpt else ""))
            warning = (warning + " " if warning else "") + "Only metadata or a short public body was available; this is not full text."
        return _clean("".join(parser.title)), excerpt, warning
    if content_type.startswith("text/") or content_type in {"", "application/json", "application/xml", "application/xhtml+xml"}:
        return "", _clean(text), None
    return "", "", "Unsupported public content type; no text was extracted."


def extract_link(url: str, *, transport=None) -> dict:
    """Best effort public extraction with truthful ready/needs_review/error status.

    Invalid or blocked links raise ValueError during normalization. DNS, HTTP,
    size, redirect and parse failures return an error material with its original
    normalized external URL intact. Nothing is downloaded to disk.
    """
    original = normalize_link(url)
    result = {"title": urlsplit(original).hostname, "url": original, "excerpt": "", "status": "error", "warning": None}
    current = original
    deadline = time.monotonic() + FETCH_SECONDS
    try:
        with httpx.Client(transport=transport, timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False, headers={"User-Agent": "AIcademiya-Public-Material/1.0", "Accept": "text/html, text/plain, application/pdf;q=0.9, */*;q=0.1", "Accept-Encoding": "identity"}) as client:
            for hop in range(MAX_REDIRECTS + 1):
                if time.monotonic() >= deadline:
                    raise ValueError("Public fetch exceeded the time limit")
                address = _resolve_public(current)
                request_url = httpx.URL(current)
                headers = {}
                extensions = {}
                if transport is None:
                    headers["Host"] = request_url.netloc.decode("ascii")
                    extensions["sni_hostname"] = request_url.host
                    request_url = request_url.copy_with(host=address)
                client.cookies.clear()
                with client.stream("GET", request_url, headers=headers, extensions=extensions) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect had no public destination")
                        if hop == MAX_REDIRECTS:
                            raise ValueError("Public fetch exceeded the redirect limit")
                        current = normalize_link(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        result["warning"] = f"Public fetch returned HTTP {response.status_code}; no authenticated or paywalled content was fetched."
                        return result
                    # httpx expands an encoded chunk before iter_bytes yields it.
                    # Refuse unsolicited compression BEFORE the decoder allocates;
                    # identity was requested, so limits apply to received bytes.
                    if response.headers.get("content-encoding", "identity").strip().lower() not in {"", "identity"}:
                        raise ValueError("Public content encoding is not supported; an uncompressed response is required")
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > MAX_BYTES:
                        raise ValueError("Public content exceeds the download size limit")
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        if time.monotonic() >= deadline:
                            raise ValueError("Public fetch exceeded the time limit")
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise ValueError("Public content exceeds the download size limit")
                    title, excerpt, warning = _extract_body(bytes(body), response.headers.get("content-type", "").split(";")[0].strip().lower(), response.encoding)
                    if len(title) > 300:
                        title = title[:300]
                        warning = (warning + " " if warning else "") + "Public title is limited to 300 characters."
                    if len(excerpt) > MAX_EXCERPT:
                        warning = (warning + " " if warning else "") + f"Extracted excerpt is limited to {MAX_EXCERPT} characters."
                        excerpt = excerpt[:MAX_EXCERPT]
                    if not excerpt:
                        warning = warning or "No useful public text was available; the external link remains usable."
                    result.update(title=title or result["title"], excerpt=excerpt, status="needs_review" if warning else "ready", warning=warning)
                    return result
    except (ValueError, httpx.HTTPError, OSError) as exc:
        # Never echo document bodies, credential-like URLs or private paths.
        result["warning"] = str(exc) if isinstance(exc, ValueError) else "Public fetch failed (network, TLS or timeout); no full text was retrieved."
    except Exception:
        result["warning"] = "Public content could not be parsed; the external link remains usable."
    return result
