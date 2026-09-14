import json
import queue
import time
import uuid
from datetime import date

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.mcp.auth import check_mcp_auth
from apps.mcp.errors import MCPToolError
from apps.mcp.registry import list_tools
from apps.mcp.tools import call_tool
from apps.mcp.utils.presenters import tool_text_payload

_SSE_SESSIONS = {}
_SSE_SESSION_TIMEOUT_SECONDS = 30 * 60
_SSE_HEARTBEAT_SECONDS = 15
_SERVICE_CUTOFF_DATE = date(2026, 10, 30)


def _service_expired():
    return timezone.localdate() > _SERVICE_CUTOFF_DATE


def _service_expired_response():
    return JsonResponse(
        {
            'error': '服务已到期，暂不可用',
            'code': 'service_expired',
        },
        status=503,
        json_dumps_params={'ensure_ascii': False},
    )


def _format_sse(event=None, data=None):
    lines = []
    if event:
        lines.append(f'event: {event}')
    lines.append(f'data: {json.dumps(data, ensure_ascii=False)}')
    return ('\n'.join(lines) + '\n\n').encode('utf-8')


def _cleanup_sse_sessions():
    now = time.time()
    expired_ids = [
        session_id for session_id, session in _SSE_SESSIONS.items()
        if now - session['created_at'] > _SSE_SESSION_TIMEOUT_SECONDS
    ]
    for session_id in expired_ids:
        _SSE_SESSIONS.pop(session_id, None)


@method_decorator(csrf_exempt, name='dispatch')
class MCPServerView(View):
    supported_protocol_versions = ('2025-06-18', '2025-03-26', '2024-11-05')
    protocol_version = supported_protocol_versions[0]
    server_name = 'ai-story-native-mcp'
    server_version = '0.1.0'

    def dispatch(self, request, *args, **kwargs):
        if _service_expired():
            return _service_expired_response()
        return super().dispatch(request, *args, **kwargs)

    def _jsonrpc_result(self, request_id, result):
        return {'jsonrpc': '2.0', 'id': request_id, 'result': result}

    def _jsonrpc_error(self, request_id, code, message, data=None):
        payload = {
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {'code': code, 'message': message},
        }
        if data is not None:
            payload['error']['data'] = data
        return payload

    def _initialize_result(self, params=None):
        protocol_version = self._negotiate_protocol_version(params or {})
        return {
            'protocolVersion': protocol_version,
            'capabilities': {
                'tools': {'listChanged': False},
            },
            'serverInfo': {
                'name': self.server_name,
                'version': self.server_version,
            },
            'instructions': 'AI Story 原生 MCP 服务。当前提供项目、提示词、变量、模型与日志的首批只读工具。',
        }

    def _negotiate_protocol_version(self, params):
        requested_version = params.get('protocolVersion')
        if requested_version in self.supported_protocol_versions:
            return requested_version
        return self.protocol_version

    def get(self, request, *args, **kwargs):
        auth_error = check_mcp_auth(request)
        if auth_error is not None:
            return auth_error
        if self._wants_sse(request):
            return self._sse_response(request)
        return JsonResponse(
            {
                'name': self.server_name,
                'version': self.server_version,
                'protocolVersion': self.protocol_version,
                'status': 'ok',
                'methods': ['initialize', 'ping', 'tools/list', 'tools/call'],
                'tools_count': len(list_tools()),
            },
            json_dumps_params={'ensure_ascii': False},
        )

    def post(self, request, *args, **kwargs):
        auth_error = check_mcp_auth(request)
        if auth_error is not None:
            return auth_error

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse(
                self._jsonrpc_error(None, -32700, 'Parse error'),
                status=400,
                json_dumps_params={'ensure_ascii': False},
            )

        response = self._handle_request(payload)
        if response is None:
            return HttpResponse(status=202)
        status_code = 200 if 'result' in response else 400
        return JsonResponse(response, status=status_code, json_dumps_params={'ensure_ascii': False})

    def _wants_sse(self, request):
        return 'text/event-stream' in request.headers.get('Accept', '')

    def _sse_response(self, request):
        _cleanup_sse_sessions()
        session_id = uuid.uuid4().hex
        session_queue = queue.Queue()
        _SSE_SESSIONS[session_id] = {
            'queue': session_queue,
            'created_at': time.time(),
        }
        endpoint = request.build_absolute_uri(f'/mcp/messages/?session_id={session_id}')

        def event_stream():
            try:
                yield f'event: endpoint\ndata: {endpoint}\n\n'.encode('utf-8')
                while True:
                    try:
                        event = session_queue.get(timeout=_SSE_HEARTBEAT_SECONDS)
                    except queue.Empty:
                        yield b': keep-alive\n\n'
                        continue
                    if event is None:
                        break
                    yield _format_sse(data=event)
            finally:
                _SSE_SESSIONS.pop(session_id, None)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    def _handle_request(self, payload):
        if not isinstance(payload, dict):
            return self._jsonrpc_error(None, -32600, 'Invalid Request')

        request_id = payload.get('id')
        method = payload.get('method')
        params = payload.get('params') or {}
        if not method:
            return self._jsonrpc_error(request_id, -32600, 'Invalid Request')

        if method == 'notifications/initialized':
            return None
        if method == 'initialize':
            return self._jsonrpc_result(request_id, self._initialize_result(params))
        if method == 'ping':
            return self._jsonrpc_result(request_id, {})
        if method == 'tools/list':
            return self._jsonrpc_result(request_id, {'tools': list_tools()})
        if method == 'tools/call':
            tool_name = params.get('name')
            arguments = params.get('arguments') or {}
            if not tool_name:
                return self._jsonrpc_error(request_id, -32602, 'Invalid params', {'reason': '缺少工具名称'})
            try:
                tool_result = call_tool(tool_name, arguments)
            except MCPToolError as exc:
                return self._jsonrpc_result(request_id, tool_text_payload({'error': str(exc)}, is_error=True))
            except Exception as exc:
                return self._jsonrpc_result(request_id, tool_text_payload({'error': str(exc)}, is_error=True))
            return self._jsonrpc_result(request_id, tool_text_payload(tool_result))

        return self._jsonrpc_error(request_id, -32601, 'Method not found', {'method': method})


@method_decorator(csrf_exempt, name='dispatch')
class MCPSSEMessageView(MCPServerView):
    def get(self, request, *args, **kwargs):
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    def post(self, request, *args, **kwargs):
        auth_error = check_mcp_auth(request)
        if auth_error is not None:
            return auth_error

        session_id = request.GET.get('session_id', '').strip()
        session = _SSE_SESSIONS.get(session_id)
        if not session:
            return JsonResponse({'detail': 'Invalid or expired MCP SSE session'}, status=404)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            session['queue'].put(self._jsonrpc_error(None, -32700, 'Parse error'))
            return HttpResponse(status=202)

        response = self._handle_request(payload)
        if response is not None:
            session['queue'].put(response)
        return HttpResponse(status=202)
