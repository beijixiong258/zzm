"""Early ASGI Host/CSRF/body checks and response security headers.

No network calls and no trust in X-Forwarded-* headers. Uvicorn is responsible
for an explicit narrow forwarded-allow-ips policy before it changes ASGI scope.
"""
import re
from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from .config import origin_value

AUTH_LIMIT = 16 * 1024
JSON_LIMIT = 4 * 1024 * 1024
UPLOAD_LIMIT = 27 * 1024 * 1024  # existing 25 MiB files plus multipart framing
MATERIAL_UPLOAD_LIMIT = 66 * 1024 * 1024  # full sources64MiB plus framing; other uploads unchanged
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
IP_LIMITS = {
    '/api/auth/login': ('login-ip', 30, 60),
    '/api/auth/register': ('register-ip', 30, 300),
    '/api/auth/demo': ('demo-ip', 60, 60),
    '/api/auth/change-password': ('password-ip', 30, 300),
}


class HttpSecurityMiddleware:
    def __init__(self, app, *, config, limiter):
        self.app = app
        self.config = config
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope.get('path', ''), scope['method']
        headers = Headers(scope=scope)
        api = path == '/api' or path.startswith('/api/')

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                updated = MutableHeaders(scope=message)
                updated.setdefault('X-Content-Type-Options', 'nosniff')
                updated.setdefault('X-Frame-Options', 'SAMEORIGIN')
                # No script/sandbox restriction that would break native PDFs or
                # historical self-contained exports; framing alone is enforced.
                updated.setdefault('Content-Security-Policy', "frame-ancestors 'self'")
                updated.setdefault('Referrer-Policy', 'same-origin')
                updated.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
                if api:
                    if '/avatar' in path and method in ('GET', 'HEAD') and message['status'] == 200:
                        updated.setdefault('Cache-Control', 'private, no-cache')
                    else:
                        updated['Cache-Control'] = 'private, no-store'
                elif not api and updated.get('content-type', '').startswith('text/html'):
                    updated.setdefault('Cache-Control', 'no-cache')
            await send(message)

        async def reject(code, detail, extra=None):
            await JSONResponse({'detail': detail}, status_code=code, headers=extra)(scope, receive, protected_send)

        if len(headers.getlist('host')) != 1 or not self.config.allows_host(headers.get('host')):
            return await reject(400, 'Host is not allowed')
        if api and method not in SAFE_METHODS:
            if len(headers.getlist('origin')) > 1:
                return await reject(403, 'Cross-origin write rejected')
            origin = headers.get('origin')
            current_origin = origin_value(scope.get('scheme', 'http') + '://' + headers['host'])
            allowed = self.config.allowed_origins | {current_origin}
            if origin is not None:
                if origin_value(origin) not in allowed:
                    return await reject(403, 'Cross-origin write rejected')
            else:
                # Requests without browser signals remain API-compatible. Browser
                # metadata/Referer cannot turn omission of Origin into a bypass.
                if headers.get('sec-fetch-site', '').lower() in ('cross-site', 'same-site'):
                    return await reject(403, 'Cross-origin write rejected')
                referer = headers.get('referer')
                if referer and origin_value(referer, referer=True) not in allowed:
                    return await reject(403, 'Cross-origin write rejected')
            policy = IP_LIMITS.get(path)
            if policy:
                peer = scope.get('client')
                try:
                    self.limiter.check(policy[0], peer[0] if peer else 'unknown-peer', policy[1], policy[2])
                except HTTPException as exc:
                    return await reject(exc.status_code, exc.detail, exc.headers)
            content_type = headers.get('content-type', '').split(';', 1)[0].strip().lower()
            json_type = content_type == 'application/json' or content_type.startswith('application/') and content_type.endswith('+json')
            limit = AUTH_LIMIT if path in IP_LIMITS or path == '/api/admin/access-settings' else JSON_LIMIT if json_type else UPLOAD_LIMIT
            if content_type == 'multipart/form-data' and method == 'POST' and re.fullmatch(r'/api/sessions/[^/]+/materials', path):
                limit = MATERIAL_UPLOAD_LIMIT
            lengths = headers.getlist('content-length')
            if len(lengths) > 1 or lengths and (len(lengths[0]) > 20 or not lengths[0].isascii() or not lengths[0].isdigit()):
                return await reject(400, 'Invalid request length')
            if lengths and int(lengths[0]) > limit:
                return await reject(413, 'Request body is too large')
            chunks, total = [], 0
            while True:
                chunk = await receive()
                if chunk['type'] == 'http.disconnect':
                    return
                if chunk['type'] != 'http.request':
                    continue
                total += len(chunk.get('body', b''))
                if total > limit:
                    return await reject(413, 'Request body is too large')
                chunks.append(chunk)
                if not chunk.get('more_body', False):
                    break
            if total and not (json_type or content_type == 'multipart/form-data'):
                return await reject(415, 'Use application/json or multipart/form-data')
            iterator = iter(chunks)
            async def replay():
                try:
                    return next(iterator)
                except StopIteration:
                    return await receive()
            return await self.app(scope, replay, protected_send)
        return await self.app(scope, receive, protected_send)
