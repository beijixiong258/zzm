"""Explicit HTTP trust configuration; no forwarded header is interpreted here."""
from dataclasses import dataclass
import ipaddress
import os
from urllib.parse import urlsplit


def origin_value(value, *, referer=False):
    """Return a canonical HTTP origin, rejecting credentials and malformed ports."""
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None or parts.password is not None:
            return None
        if not referer and (parts.path not in ('', '/') or parts.query or parts.fragment):
            return None
        host = parts.hostname.lower()
        port = parts.port
        if any(c.isspace() for c in value) or '\\' in value or '*' in host:
            return None
        host = '[' + host + ']' if ':' in host else host
        suffix = '' if port is None or (parts.scheme == 'http' and port == 80) or (parts.scheme == 'https' and port == 443) else ':' + str(port)
        return parts.scheme + '://' + host + suffix
    except (ValueError, TypeError):
        return None


def host_name(value):
    if not value or any(c.isspace() for c in value) or any(c in value for c in '/\\@?#'):
        return None
    try:
        parts = urlsplit('http://' + value)
        _ = parts.port
        return parts.hostname.lower() if parts.hostname else None
    except ValueError:
        return None


@dataclass(frozen=True)
class SecurityConfig:
    allowed_origins: frozenset
    allowed_hosts: frozenset
    cookie_secure: bool

    @classmethod
    def from_environment(cls):
        origins = set()
        for item in os.getenv('AICADEMIYA_ALLOWED_ORIGINS', '').split(','):
            if item.strip():
                origin = origin_value(item.strip())
                if not origin:
                    raise ValueError('AICADEMIYA_ALLOWED_ORIGINS requires exact HTTP(S) origins')
                origins.add(origin)
        hosts = {'localhost', '127.0.0.1', '::1', 'testserver'}
        hosts.update(urlsplit(origin).hostname for origin in origins)
        for item in os.getenv('AICADEMIYA_ALLOWED_HOSTS', '').split(','):
            if item.strip():
                host = host_name(item.strip())
                if not host or '*' in host:
                    raise ValueError('AICADEMIYA_ALLOWED_HOSTS requires exact host names, not wildcards')
                hosts.add(host)
        return cls(frozenset(origins), frozenset(hosts),
                   os.getenv('AICADEMIYA_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes'))

    def allows_host(self, value):
        host = host_name(value)
        if host in self.allowed_hosts:
            return True
        # Preserve direct LAN HTTP without trusting arbitrary DNS/Host values.
        try:
            address = ipaddress.ip_address(host or '')
            networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
            return address.is_loopback or any(address in ipaddress.ip_network(net) for net in networks)
        except ValueError:
            return False

    def secure_cookie(self, request):
        # ASGI scheme is set by the server; X-Forwarded-Proto is never read here.
        return self.cookie_secure or request.url.scheme == 'https'
