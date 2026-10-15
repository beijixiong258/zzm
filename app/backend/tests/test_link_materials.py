"""Explicitly labelled HTTP/DNS fixtures; no paid/provider/network calls.

URL validation is real. HTTP bodies are synthetic httpx.MockTransport responses;
DNS fixtures ensure tests do not depend on public DNS or fetch real websites.
"""
import socket

import httpx
import pytest
import pymupdf

from backend.aicademiya import link_materials as links


@pytest.fixture(autouse=True)
def labelled_public_dns_fixture(monkeypatch):
    def public_dns(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
    monkeypatch.setattr(links.socket, "getaddrinfo", public_dns)


@pytest.mark.parametrize(("value", "expected"), [
    ("https://example.org/article?q=education#abstract", "https://example.org/article?q=education#abstract"),
    (" http://example.org/resource ", "http://example.org/resource"),
    ("10.1234/Case-Sensitive.Identifier(7)", "https://doi.org/10.1234/Case-Sensitive.Identifier(7)"),
    ("doi:10.12345/example/a+b", "https://doi.org/10.12345/example/a+b"),
    ("https://doi.org/10.1234/ExAmPlE", "https://doi.org/10.1234/ExAmPlE"),
    ("http://dx.doi.org/10.1234/Example", "https://doi.org/10.1234/Example"),
    ("https://example.org/%E6%96%87%E7%8C%AE", "https://example.org/%E6%96%87%E7%8C%AE"),
    ("https://8.8.8.8/", "https://8.8.8.8/"),
])
def test_normalize_valid_without_identifier_repair(value, expected):
    assert links.normalize_link(value) == expected


@pytest.mark.parametrize("value", [
    "", None, "example.org/no-scheme", "ftp://example.org/file", "file:///etc/passwd",
    "http://localhost/a", "http://localhost./a", "http://loop.local/a", "http://private.internal/a", "http://host/a", "http://example.org../a",
    "http://127.0.0.1/a", "http://127.0.0.2/a", "http://10.1.2.3/a", "http://172.16.0.1/a", "http://192.168.1.1/a", "http://169.254.169.254/a", "http://100.64.1.2/a", "http://0.0.0.0/a",
    "http://[::1]/a", "http://[fc00::1]/a", "http://[::ffff:127.0.0.1]/a", "http://224.0.0.1/a",
    "http://2130706433/a", "http://0x7f000001/a", "http://127.1/a",
    "https://user:password@example.org/a", "https://example.org:8080/a", "https://example.org:bad/a",
    "https://example.org/a b", "https://example.org/a\nX", "https://example.org\\@127.0.0.1/a", "https://example.org/%ZZ", "https://%31%32%37.0.0.1/a",
    "doi:10.12/example", "doi:10.1234", "doi:10.1234/", "doi: 10.1234/example", "10.1234/example wrong",
    "https://doi.org/not-a-doi", "https://doi.org/10.1234/example?secret=1",
])
def test_invalid_or_private_targets(value):
    with pytest.raises(ValueError):
        links.normalize_link(value)


def transport(handler):
    return httpx.MockTransport(handler)


def test_useful_public_html_not_scripts_navigation_or_metadata_only():
    body = """<html><head><title>Synthetic public reading</title><meta name="description" content="Only a description"></head>
    <body><nav>NAVIGATION_NOT_EVIDENCE</nav><script>JS_SECRET_NOT_EVIDENCE</script>
    <article><h1>Public methods</h1><p>This explicitly synthetic public article describes a reproducible teaching method using classroom activities and formative feedback. It contains enough text to be a useful public excerpt.</p></article>
    <footer>FOOTER_NOT_EVIDENCE</footer></body></html>"""
    result = links.extract_link("https://example.org/paper", transport=transport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})))
    assert result["status"] == "ready" and result["warning"] is None
    assert result["title"] == "Synthetic public reading"
    assert "reproducible teaching" in result["excerpt"]
    assert "NAVIGATION" not in result["excerpt"] and "JS_SECRET" not in result["excerpt"] and "FOOTER" not in result["excerpt"]
    assert result["url"] == "https://example.org/paper"


def test_metadata_only_is_truthful():
    body = '<html><head><title>Metadata fixture</title><meta name="description" content="Synthetic abstract description only."></head><body></body></html>'
    result = links.extract_link("10.1234/metadata", transport=transport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/html"})))
    assert result["url"] == "https://doi.org/10.1234/metadata"
    assert result["status"] == "needs_review" and "not full text" in result["warning"]
    assert result["excerpt"] == "Synthetic abstract description only."


def test_paywall_warning_does_not_claim_full_text():
    body = '<html><head><title>Synthetic paywall</title></head><body><main><h1>Public abstract</h1><p>Subscribe to read the full article. This public abstract introduces a study but the methods and results are not available without a subscription.</p></main></body></html>'
    result = links.extract_link("https://example.org/paywall", transport=transport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/html"})))
    assert result["status"] == "needs_review" and "paywall" in result["warning"].lower()
    assert "public abstract" in result["excerpt"].lower()


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_failure_is_error_not_fabricated_success(status):
    result = links.extract_link("https://example.org/fail", transport=transport(lambda request: httpx.Response(status, text="Unfetched authenticated paper")))
    assert result["status"] == "error" and result["excerpt"] == ""
    assert f"HTTP {status}" in result["warning"]
    assert result["url"] == "https://example.org/fail"


def test_relative_redirect_and_doi_public_destination():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "doi.org":
            return httpx.Response(302, headers={"location": "https://example.org/start"})
        if request.url.path == "/start":
            return httpx.Response(307, headers={"location": "/public"})
        return httpx.Response(200, text="Explicitly synthetic public paper contents.", headers={"content-type": "text/plain"})
    result = links.extract_link("10.1234/example", transport=transport(handler))
    assert len(seen) == 3 and result["status"] == "ready"
    assert seen[-1] == "https://example.org/public"
    assert result["url"] == "https://doi.org/10.1234/example"


@pytest.mark.parametrize("target", ["http://127.0.0.1/secret", "http://[::1]/secret", "http://169.254.169.254/latest", "http://private.internal/secret", "file:///private"])
def test_redirect_private_target_never_requested(target):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": target})
    result = links.extract_link("https://example.org/redirect", transport=transport(handler))
    assert len(seen) == 1 and result["status"] == "error" and result["excerpt"] == ""
    assert result["warning"]


def test_public_name_resolving_private_and_mixed_dns_refused(monkeypatch):
    called = []
    for addresses in (("10.0.0.1",), ("93.184.216.34", "127.0.0.1"), ("::ffff:192.168.0.1",)):
        monkeypatch.setattr(links.socket, "getaddrinfo", lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses])
        result = links.extract_link("https://example.org/private", transport=transport(lambda request: called.append(request) or httpx.Response(200, text="Must not be fetched")))
        assert result["status"] == "error" and "non-public" in result["warning"]
    assert called == []


def test_redirect_dns_private_refused_before_second_request(monkeypatch):
    def resolve(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (("93.184.216.34" if host == "example.org" else "10.0.0.1"), port))]
    monkeypatch.setattr(links.socket, "getaddrinfo", resolve)
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://private.example.org/"})
    result = links.extract_link("https://example.org/", transport=transport(handler))
    assert len(seen) == 1 and result["status"] == "error"


def test_real_client_connection_pins_dns_host_and_tls_sni(monkeypatch):
    # Labelled recording HTTP transport injected at Client construction, not the
    # public transport argument: exercises production URL pinning branch.
    seen = []
    real_client = httpx.Client
    def handler(request):
        seen.append(request)
        return httpx.Response(200, text="Synthetic public text", headers={"content-type": "text/plain"})
    def fixture_client(**kwargs):
        kwargs["transport"] = transport(handler)
        return real_client(**kwargs)
    monkeypatch.setattr(links.httpx, "Client", fixture_client)
    result = links.extract_link("https://example.org/paper")
    assert result["status"] == "ready"
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["Host"] == "example.org"
    assert seen[0].extensions["sni_hostname"] == "example.org"


def test_redirect_limit_is_bounded():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "/again"})
    result = links.extract_link("https://example.org/", transport=transport(handler))
    assert len(seen) == links.MAX_REDIRECTS + 1
    assert result["status"] == "error" and "redirect limit" in result["warning"]


def test_missing_redirect_destination_is_error():
    result = links.extract_link("https://example.org/", transport=transport(lambda request: httpx.Response(302)))
    assert result["status"] == "error" and "destination" in result["warning"]


@pytest.mark.parametrize("declared", [True, False])
def test_response_size_bounds_not_silent_truncation(monkeypatch, declared):
    monkeypatch.setattr(links, "MAX_BYTES", 100)
    result = links.extract_link("https://example.org/", transport=transport(lambda request: httpx.Response(200, content=b"x" * 200, headers={"content-type": "text/plain", **({"content-length": "200"} if declared else {"transfer-encoding": "chunked"})})))
    assert result["status"] == "error" and result["excerpt"] == ""
    assert "size limit" in result["warning"]


def test_excerpt_bound_is_labelled(monkeypatch):
    monkeypatch.setattr(links, "MAX_EXCERPT", 20)
    result = links.extract_link("https://example.org/", transport=transport(lambda request: httpx.Response(200, text="Synthetic text longer than the configured excerpt bound", headers={"content-type": "text/plain"})))
    assert len(result["excerpt"]) == 20 and result["status"] == "needs_review"
    assert "limited to 20" in result["warning"]


def test_network_failure_does_not_echo_sensitive_details():
    def failure(request):
        raise httpx.ConnectError("Synthetic private network details", request=request)
    result = links.extract_link("https://example.org/", transport=transport(failure))
    assert result["status"] == "error" and result["excerpt"] == ""
    assert "Synthetic private" not in result["warning"]


def test_redirect_does_not_carry_site_cookies():
    seen = []
    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(302, headers={"location": "/paper", "set-cookie": "site_session=SYNTHETIC; Path=/; Secure"})
        return httpx.Response(200, text="Public response", headers={"content-type": "text/plain"})
    result = links.extract_link("https://example.org/", transport=transport(handler))
    assert result["status"] == "ready" and len(seen) == 2
    assert "cookie" not in seen[1].headers


def test_public_title_bound_is_explicit():
    body = "<html><head><title>" + "A" * 500 + "</title></head><body><p>" + "Synthetic public evidence " * 10 + "</p></body></html>"
    result = links.extract_link("https://example.org/", transport=transport(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/html"})))
    assert result["status"] == "needs_review" and len(result["title"]) == 300
    assert "title is limited" in result["warning"]


def test_actual_generated_public_pdf_body():
    document = pymupdf.open()
    document.set_metadata({"title": "Synthetic public PDF"})
    document.new_page().insert_text((40, 50), "Synthetic public article evidence from a real generated PDF.")
    data = document.tobytes()
    document.close()
    result = links.extract_link("https://example.org/paper.pdf", transport=transport(lambda request: httpx.Response(200, content=data, headers={"content-type": "application/pdf"})))
    assert result["status"] == "ready" and result["title"] == "Synthetic public PDF"
    assert "real generated PDF" in result["excerpt"]


@pytest.mark.parametrize("content_type,content", [("application/octet-stream", b"\x00\x01\x02"), ("text/plain", b""), ("application/pdf", b"%PDF-corrupt")])
def test_no_body_or_unsupported_or_unparseable_is_truthful(content_type, content):
    result = links.extract_link("https://example.org/", transport=transport(lambda request: httpx.Response(200, content=content, headers={"content-type": content_type})))
    assert result["status"] in {"needs_review", "error"} and not result["excerpt"] and result["warning"]
