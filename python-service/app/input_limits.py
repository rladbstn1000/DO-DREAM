"""Bound the body before JSON/multipart parsing, including chunked requests."""
import asyncio
from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, max_bytes, json_max_bytes=65536, timeout_seconds=15):
        self.app, self.max_bytes = app, max_bytes
        self.json_max_bytes, self.timeout_seconds = json_max_bytes, timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = scope.get('headers', [])
        content_type = next((v for k, v in headers if k == b'content-type'), b'')
        limit = self.max_bytes if content_type.startswith(b'multipart/form-data;') else self.json_max_bytes
        lengths = [v for k, v in headers if k == b'content-length']
        status = None
        if (scope.get('path') == '/api/pdf/parse-pdf-gemini-upload'
                and scope.get('method') == 'POST' and not content_type.startswith(b'multipart/form-data;')):
            status = 415
        elif len(lengths) > 1 or (lengths and (not lengths[0].isdigit() or len(lengths[0]) > 10)):
            status = 400
        elif lengths and int(lengths[0]) > limit:
            status = 413
        elif any(k == b'content-encoding' and v.lower() != b'identity' for k, v in headers):
            status = 415
        chunks, size = [], 0

        async def collect():
            nonlocal size
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return 400
                body = message.get('body', b'')
                size += len(body)
                if size > limit:
                    return 413
                if body:
                    chunks.append(body)
                if not message.get('more_body', False):
                    if lengths and size != int(lengths[0]):
                        return 400
                    return None

        if status is None:
            try:
                status = await asyncio.wait_for(collect(), self.timeout_seconds)
            except asyncio.TimeoutError:
                status = 408
        if status is not None:
            return await JSONResponse({'detail': 'Request body rejected'}, status_code=status)(scope, receive, send)
        body = b''.join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()

        await self.app(scope, bounded_receive, send)
