"""Compact GenAI content: record each piece of content once per trace.

GenAI spans are self-contained, so a tool loop or a multi-turn conversation
re-sends the system prompt, the history and every earlier tool result on each
model call. In compact mode (the default, ``OTEL_GENAI_CONTENT_MODE=compact``)
content already recorded on an earlier span of the same trace is replaced by a
reference to where it first appeared:

* a repeated chat message becomes
  ``{"role": <role>, "parts": [{"type": "reference", "span_id": <hex>,
  "attribute": <attribute key>, "index": <message index>}]}``;
* a repeated value (a tool result, or a tool response inside a message) becomes
  ``{"type": "reference", "span_id": <hex>, "attribute": <attribute key>}``.

References always point backwards to a span of the same trace. When nothing is
known about a trace (a fresh process, an evicted entry) the full content is
recorded, so a reference is never dangling within one process lifetime.
``OTEL_GENAI_CONTENT_MODE=full`` keeps standard self-contained spans.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict

# Short values cost less inline than as a reference.
_MIN_LENGTH = 64
_MAX_TRACES = 512
_MAX_ENTRIES = 4096
_TTL_SECONDS = 3 * 60 * 60


def _canonical(value) -> str | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    return text if len(text) >= _MIN_LENGTH else None


def _key(value) -> str | None:
    text = _canonical(value)
    return hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None


def _message_shape(message):
    """A message as compared across spans: no finish reason, no empty text parts."""
    if not isinstance(message, dict):
        return message
    parts = [
        part
        for part in message.get('parts') or []
        if not (isinstance(part, dict) and part.get('type') == 'text' and not part.get('content'))
    ]
    shape = {'role': message.get('role'), 'parts': parts}
    if message.get('name'):
        shape['name'] = message['name']
    return shape


def span_ids(span):
    """(trace id, span id) as lowercase hex, or (None, None) for a non-recording span."""
    try:
        ctx = span.get_span_context()
    except Exception:
        return None, None
    if not ctx or not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, '032x'), format(ctx.span_id, '016x')


class ContentRegistry:
    """Where each piece of content first appeared, per trace (bounded, thread-safe)."""

    def __init__(self, max_traces=_MAX_TRACES, max_entries=_MAX_ENTRIES, ttl=_TTL_SECONDS):
        self._traces: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()
        self.max_traces, self.max_entries, self.ttl = max_traces, max_entries, ttl

    def _entries(self, trace_id):
        now = time.monotonic()
        stamp, entries = self._traces.pop(trace_id, (now, {}))
        if now - stamp > self.ttl:
            entries = {}
        self._traces[trace_id] = (now, entries)
        while len(self._traces) > self.max_traces:
            self._traces.popitem(last=False)
        return entries

    def lookup(self, trace_id, key):
        if trace_id is None or key is None:
            return None
        with self._lock:
            return self._entries(trace_id).get(key)

    def remember(self, trace_id, key, location):
        if trace_id is None or key is None:
            return
        with self._lock:
            entries = self._entries(trace_id)
            if key not in entries and len(entries) < self.max_entries:
                entries[key] = location

    def clear(self):
        with self._lock:
            self._traces.clear()


REGISTRY = ContentRegistry()


def _reference(location):
    return {'type': 'reference', **location}


def reference_for(span, value):
    """A reference to where the trace first recorded ``value`` (on another span), or None."""
    trace_id, span_id = span_ids(span)
    found = REGISTRY.lookup(trace_id, _key(value))
    return _reference(found) if found is not None and found['span_id'] != span_id else None


def compact_value(span, attribute, value):
    """``value`` itself, or a reference when the trace already recorded it."""
    trace_id, span_id = span_ids(span)
    key = _key(value)
    if key is None or trace_id is None:
        return value
    found = REGISTRY.lookup(trace_id, key)
    if found is not None and found['span_id'] != span_id:
        return _reference(found)
    REGISTRY.remember(trace_id, key, {'span_id': span_id, 'attribute': attribute})
    return value


def remember_value(span, attribute, value):
    """Record where ``value`` appears without replacing it."""
    trace_id, span_id = span_ids(span)
    REGISTRY.remember(trace_id, _key(value), {'span_id': span_id, 'attribute': attribute})


def remember_messages(span, attribute, messages):
    """Record each message of an attribute (e.g. generated output messages)."""
    trace_id, span_id = span_ids(span)
    for index, message in enumerate(messages or []):
        REGISTRY.remember(
            trace_id,
            _key(_message_shape(message)),
            {'span_id': span_id, 'attribute': attribute, 'index': index},
        )


def compact_messages(span, attribute, messages):
    """Messages with every one recorded earlier in the trace replaced by a reference.

    A tool response whose content was recorded earlier (the tool span's result)
    becomes a reference too, even when the message around it is new.
    """
    trace_id, span_id = span_ids(span)
    if trace_id is None or not isinstance(messages, list):
        return messages
    compacted = []
    for index, message in enumerate(messages):
        key = _key(_message_shape(message))
        found = REGISTRY.lookup(trace_id, key)
        if found is not None and found['span_id'] != span_id:
            role = message.get('role') if isinstance(message, dict) else None
            compacted.append({'role': role, 'parts': [_reference(found)]})
            continue
        REGISTRY.remember(trace_id, key, {'span_id': span_id, 'attribute': attribute, 'index': index})
        if isinstance(message, dict) and message.get('role') == 'tool':
            parts = []
            for part in message.get('parts') or []:
                if isinstance(part, dict) and part.get('type') == 'tool_call_response':
                    response = REGISTRY.lookup(trace_id, _key(part.get('response')))
                    if response is not None and response['span_id'] != span_id:
                        part = {**part, 'response': _reference(response)}
                parts.append(part)
            message = {**message, 'parts': parts}
        compacted.append(message)
    return compacted
