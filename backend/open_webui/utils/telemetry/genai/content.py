"""Schema-aware OpenTelemetry GenAI content conversion.

Based on open-telemetry/semantic-conventions-genai model/gen-ai JSON schemas.
OTel Python span attributes cannot hold nested maps, so serialize structured
payloads to valid JSON strings. Never truncate an already serialized document.
"""

import json


# Schema discriminators, identifiers and external references must not be
# truncated: doing so can invalidate otherwise valid role/parts messages.
_STRUCTURAL_FIELDS = frozenset(
    {
        'role',
        'type',
        'name',
        'id',
        'file_id',
        'tool_call_id',
        'modality',
        'mime_type',
        'finish_reason',
        'uri',
        'filename',
    }
)


def clipped(value, limit, *, field=None):
    """Bound free-form strings while preserving structural schema properties."""
    if isinstance(value, str):
        return value if field in _STRUCTURAL_FIELDS else value[:limit]
    if isinstance(value, list):
        return [clipped(item, limit) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key): clipped(item, limit, field=str(key)) for key, item in list(value.items())[:100]}
    return value


def as_object(value, *, result=False):
    """Tool call arguments/results are JSON *objects* in the GenAI schema."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            value = parsed
        except (ValueError, TypeError):
            pass
    return {'content' if result else 'raw': value}


def json_attribute(value, limit):
    """Serialize a bounded structured value, preserving syntactically valid JSON."""
    return json.dumps(clipped(value, limit), ensure_ascii=False, default=str)


def _text_parts(content, limit):
    if isinstance(content, str):
        return [{'type': 'text', 'content': content[:limit]}]
    if not isinstance(content, list):
        return []
    parts = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get('type')
        if ptype in ('text', 'input_text', 'output_text'):
            text = part.get('text', part.get('content'))
            if isinstance(text, str):
                parts.append({'type': 'text', 'content': text[:limit]})
        elif ptype == 'image_url':
            image = part.get('image_url')
            url = image.get('url') if isinstance(image, dict) else image
            # Data URLs must be represented as base64 blob parts. Do not export
            # large inline images or potentially credential-bearing URLs here.
            if isinstance(url, str) and url.startswith(('https://', 'http://')):
                parts.append({'type': 'uri', 'uri': url[:limit], 'modality': 'image'})
        elif ptype == 'file' and isinstance(part.get('file_id'), str):
            parts.append({'type': 'file', 'file_id': part['file_id'], 'modality': 'document'})
    return parts


def _tool_request_parts(tool_calls, limit):
    parts = []
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        fn = call.get('function') or {}
        if not isinstance(fn, dict) or not isinstance(fn.get('name'), str):
            continue
        part = {'type': 'tool_call', 'name': fn['name']}
        if isinstance(call.get('id'), str):
            part['id'] = call['id']
        if fn.get('arguments') is not None:
            part['arguments'] = clipped(_parse_json(fn['arguments']), limit)
        parts.append(part)
    return parts


def _parse_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def input_messages(messages, limit):
    """Map full chat history to gen_ai.input.messages (ordered role/parts)."""
    if not isinstance(messages, list):
        return None
    converted = []
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get('role'), str):
            continue
        role = message['role']
        parts = _text_parts(message.get('content'), limit)
        if role == 'tool':
            part = {
                'type': 'tool_call_response',
                'response': clipped(_parse_json(message.get('content')), limit),
            }
            if isinstance(message.get('tool_call_id'), str):
                part['id'] = message['tool_call_id']
            parts = [part]
        parts.extend(_tool_request_parts(message.get('tool_calls'), limit))
        result = {'role': role, 'parts': parts}
        if isinstance(message.get('name'), str):
            result['name'] = message['name']
        converted.append(result)
    return converted or None


def output_messages(response, limit):
    """One output message per generated choice; never merge multiple choices."""
    if not isinstance(response, dict):
        return None
    choices = response.get('choices')
    if isinstance(choices, list):
        messages = [c.get('message') if isinstance(c, dict) else None for c in choices]
    else:
        messages = [response.get('message')] if isinstance(response.get('message'), dict) else []
        if not messages and isinstance(response.get('response'), str):
            messages = [{'role': 'assistant', 'content': response['response']}]
    converted = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts = _text_parts(message.get('content'), limit)
        if isinstance(message.get('reasoning'), str):
            parts.append({'type': 'reasoning', 'content': message['reasoning'][:limit]})
        parts.extend(_tool_request_parts(message.get('tool_calls'), limit))
        output = {'role': message.get('role') or 'assistant', 'parts': parts}
        if isinstance(message.get('name'), str):
            output['name'] = message['name']
        converted.append(output)
    return converted or None


def system_instructions(instructions, limit):
    """Separate provider system instructions, not system messages in chat history."""
    if isinstance(instructions, str):
        return [{'type': 'text', 'content': instructions[:limit]}]
    if isinstance(instructions, list):
        return _text_parts(instructions, limit) or None
    return None


def normalized_finish_reasons(response):
    reasons = []
    for choice in response.get('choices') or []:
        if not isinstance(choice, dict) or not choice.get('finish_reason'):
            continue
        reason = choice['finish_reason']
        reasons.append('tool_call' if reason in ('tool_calls', 'function_call') else reason)
    if not reasons and response.get('done_reason'):
        reasons.append(response['done_reason'])
    return reasons or None


class StreamCapture:
    """Accumulate SSE/OpenAI deltas or native Ollama NDJSON across chunk splits."""

    def __init__(self, config):
        self.limit = config.content_max_length
        self.capture_outputs = config.capture_outputs
        self.pending = ''
        self.choices = {}
        self.metadata = {}

    def feed(self, item):
        if isinstance(item, bytes):
            item = item.decode('utf-8', errors='replace')
        elif not isinstance(item, str):
            return
        self.pending += item
        # SSE/NDJSON event boundaries can split across transport chunks.
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self._line(line.strip())
        if len(self.pending) > max(65536, self.limit * 4):
            self.pending = ''

    def _line(self, line):
        if line.startswith('data:'):
            line = line[5:].strip()
        if not line or line == '[DONE]' or line.startswith(':'):
            return
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            return
        if not isinstance(value, dict):
            return
        for key in ('id', 'model'):
            if value.get(key):
                self.metadata[key] = value[key]
        usage = value.get('usage')
        if isinstance(usage, dict):
            self.metadata['usage'] = usage
        if value.get('prompt_eval_count') is not None:
            self.metadata['prompt_eval_count'] = value['prompt_eval_count']
        if value.get('eval_count') is not None:
            self.metadata['eval_count'] = value['eval_count']
        if value.get('done_reason'):
            self.metadata['done_reason'] = value['done_reason']
        choices = value.get('choices')
        if not isinstance(choices, list):
            choices = [{'index': 0, 'delta': value['message']}] if isinstance(value.get('message'), dict) else []
        for idx, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            index = choice.get('index', idx)
            state = self.choices.setdefault(index, {'text': '', 'reasoning': '', 'tools': {}, 'finish_reason': None})
            reason = choice.get('finish_reason')
            if reason:
                state['finish_reason'] = reason
            if not self.capture_outputs:
                continue
            delta = choice.get('delta') or choice.get('message') or {}
            if not isinstance(delta, dict):
                continue
            for key, target in (('content', 'text'), ('reasoning', 'reasoning')):
                chunk = delta.get(key)
                if isinstance(chunk, str):
                    state[target] += chunk[: max(0, self.limit - len(state[target]))]
            for position, call in enumerate(delta.get('tool_calls') or []):
                if not isinstance(call, dict):
                    continue
                number = call.get('index', position)
                tool = state['tools'].setdefault(number, {'id': '', 'name': '', 'arguments': ''})
                if isinstance(call.get('id'), str):
                    tool['id'] += call['id'][: max(0, self.limit - len(tool['id']))]
                function = call.get('function') or {}
                for key in ('name', 'arguments'):
                    if isinstance(function.get(key), str):
                        tool[key] += function[key][: max(0, self.limit - len(tool[key]))]

    def finish(self):
        if self.pending:
            self._line(self.pending.strip())
            self.pending = ''
        self.metadata['choices'] = []
        for index in sorted(self.choices):
            state = self.choices[index]
            message = {'role': 'assistant', 'content': state['text']}
            if state['reasoning']:
                message['reasoning'] = state['reasoning']
            tool_calls = []
            for tool in state['tools'].values():
                if tool['name']:
                    tool_calls.append(
                        {'id': tool['id'], 'function': {'name': tool['name'], 'arguments': tool['arguments']}}
                    )
            if tool_calls:
                message['tool_calls'] = tool_calls
            self.metadata['choices'].append({'message': message, 'finish_reason': state['finish_reason']})
        return self.metadata
