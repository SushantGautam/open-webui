import json
import re
from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai.purpose import purpose_for_task
from open_webui.utils.telemetry.genai.streaming import wrap_stream


def _extract_user_text(content):
    """Extract user's actual query from potentially injected content."""
    markers = []
    text = (
        content
        if isinstance(content, str)
        else ' '.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
        if isinstance(content, list)
        else ''
    )

    if not text:
        return None, markers

    # Detect attached files
    if '<attached_files>' in text:
        file_section = text.split('</attached_files>')[0]
        file_names = re.findall(r'name="([^"]*)"', file_section)
        markers.append(f'[attached files: {", ".join(file_names)}]' if file_names else '[attached files]')
        text = text.split('</attached_files>')[-1].strip()

    # Detect attached knowledge
    if '<attached_knowledge>' in text:
        markers.append('[knowledge context attached]')
        text = text.split('</attached_knowledge>')[-1].strip()

    return text or None, markers


def _recent_context(messages):
    """Extract what drove this LLM call: from last user message onwards."""
    if not messages or not isinstance(messages, list):
        return None

    # Find system prompt content
    system_content = None
    for m in messages:
        if isinstance(m, dict) and m.get('role') == 'system' and m.get('content'):
            system_content = m['content']
            break

    # Build a map of tool_call_id -> function name
    tool_name_map = {}
    has_assistant = False
    for msg in messages:
        if isinstance(msg, dict) and msg.get('role') == 'assistant':
            has_assistant = True
            for tc in msg.get('tool_calls') or []:
                tc_id = tc.get('id')
                fn_name = (tc.get('function') or {}).get('name')
                if tc_id and fn_name:
                    tool_name_map[tc_id] = fn_name

    # Find the index of the last user message
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) and msg.get('role') == 'user':
            last_user_idx = i
            break

    # Count prior conversation turns
    prior_turns = 0
    if last_user_idx > 0:
        for m in messages[:last_user_idx]:
            if isinstance(m, dict) and m.get('role') == 'user':
                prior_turns += 1

    # Collect from the last user message onwards
    recent = messages[last_user_idx:] if last_user_idx >= 0 else messages

    if not recent:
        return None

    parts = []

    # System prompt
    if system_content:
        stripped = system_content.strip()
        if not has_assistant:
            parts.append(f'[system prompt: {stripped[:500]}]')
        else:
            parts.append('[system prompt]')

    # Prior conversation context marker
    if prior_turns > 0:
        parts.append(f'[+{prior_turns} prior turns in history]')

    for msg in recent:
        if not isinstance(msg, dict):
            continue
        role = msg.get('role', '')
        content = msg.get('content')

        if role == 'user':
            text, markers = _extract_user_text(content)
            parts.extend(markers)
            if text:
                parts.append(text)
        elif role == 'assistant':
            tcs = msg.get('tool_calls') or []
            if tcs:
                names = ', '.join((tc.get('function') or {}).get('name', '?') for tc in tcs[:3])
                parts.append(f'[called: {names}]')
        elif role == 'tool':
            name = msg.get('name') or tool_name_map.get(msg.get('tool_call_id'), 'tool')
            parts.append(f'[results from tool: {name}]')

    return '\n'.join(parts) if parts else None


async def traced_inference(
    tracer,
    *,
    provider: str,
    request_payload: dict,
    call: Callable[[], Awaitable],
):
    metadata = request_payload.get('metadata') or {}
    purpose = purpose_for_task(metadata.get('task'))
    model = request_payload.get('model') or 'unknown'
    span_name = 'chat' if purpose == 'primary' else purpose
    with tracer.inference(
        span_name,
        operation_name='chat',
        provider=provider,
        request_model=model,
        inputs=_recent_context(request_payload.get('messages')),
        temperature=request_payload.get('temperature'),
        top_p=request_payload.get('top_p'),
        max_tokens=request_payload.get('max_tokens', request_payload.get('max_completion_tokens')),
        seed=request_payload.get('seed'),
        purpose=purpose,
        _defer_end=True,
    ) as span:
        response = await call()
        body_iterator = getattr(response, 'body_iterator', None)
        if body_iterator is not None:
            chunks = []
            captured_length = 0
            had_tool_calls = False

            def collect(item):
                nonlocal captured_length, had_tool_calls
                if tracer.config.capture_outputs and captured_length < tracer.config.content_max_length:
                    if isinstance(item, bytes):
                        item = item.decode('utf-8', errors='replace')
                    elif not isinstance(item, str):
                        item = str(item)
                    for line in item.split('\n'):
                        line = line.strip()
                        if not line.startswith('data: '):
                            continue
                        payload = line[6:]
                        if payload == '[DONE]':
                            continue
                        try:
                            data = json.loads(payload)
                            choices = data.get('choices') or []
                            for choice in choices:
                                delta = choice.get('delta') or {}
                                content = delta.get('content')
                                if content:
                                    remaining = tracer.config.content_max_length - captured_length
                                    chunk = content[:remaining]
                                    chunks.append(chunk)
                                    captured_length += len(chunk)
                                tool_calls = delta.get('tool_calls') or []
                                for tc in tool_calls:
                                    had_tool_calls = True
                                    fn = tc.get('function') or {}
                                    name = fn.get('name')
                                    args = fn.get('arguments')
                                    if name:
                                        remaining = tracer.config.content_max_length - captured_length
                                        label = f'[tool_call: {name}]'
                                        chunks.append(label[:remaining])
                                        captured_length += len(label[:remaining])
                                    if args:
                                        remaining = tracer.config.content_max_length - captured_length
                                        chunks.append(args[:remaining])
                                        captured_length += len(args[:remaining])
                        except (ValueError, KeyError):
                            pass

            response.body_iterator = wrap_stream(
                span,
                body_iterator,
                on_finish=lambda: tracer.finish_stream(span, chunks, agent_step=had_tool_calls),
                on_item=collect,
            )
        else:
            tracer.finish_inference(span, response)
        return response
