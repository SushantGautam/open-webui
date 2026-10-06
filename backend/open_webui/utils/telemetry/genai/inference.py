from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai.purpose import purpose_for_task
from open_webui.utils.telemetry.genai.streaming import wrap_stream


async def traced_inference(
    tracer,
    *,
    provider: str,
    request_payload: dict,
    call: Callable[[], Awaitable],
):
    metadata = request_payload.get('metadata') or {}
    with tracer.inference(
        'chat_completion',
        provider=provider,
        request_model=request_payload.get('model'),
        inputs=request_payload.get('messages'),
        temperature=request_payload.get('temperature'),
        top_p=request_payload.get('top_p'),
        max_tokens=request_payload.get('max_tokens', request_payload.get('max_completion_tokens')),
        seed=request_payload.get('seed'),
        purpose=purpose_for_task(metadata.get('task')),
        _defer_end=True,
    ) as span:
        response = await call()
        body_iterator = getattr(response, 'body_iterator', None)
        if body_iterator is not None:
            chunks = []
            captured_length = 0

            def collect(item):
                nonlocal captured_length
                if tracer.config.capture_outputs and captured_length < tracer.config.content_max_length:
                    if isinstance(item, bytes):
                        item = item.decode('utf-8', errors='replace')
                    elif not isinstance(item, str):
                        item = str(item)
                    remaining = tracer.config.content_max_length - captured_length
                    chunk = item[:remaining]
                    chunks.append(chunk)
                    captured_length += len(chunk)

            response.body_iterator = wrap_stream(
                span,
                body_iterator,
                on_finish=lambda: tracer.finish_stream(span, chunks),
                on_item=collect,
            )
        else:
            tracer.finish_inference(span, response)
        return response
