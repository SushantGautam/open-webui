from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai.streaming import wrap_stream


async def traced_inference(
    tracer,
    *,
    provider: str,
    request_payload: dict,
    call: Callable[[], Awaitable],
):
    with tracer.inference(
        'chat_completion',
        provider=provider,
        request_model=request_payload.get('model'),
        inputs=request_payload.get('messages'),
        temperature=request_payload.get('temperature'),
        top_p=request_payload.get('top_p'),
        max_tokens=request_payload.get('max_tokens', request_payload.get('max_completion_tokens')),
        seed=request_payload.get('seed'),
        _defer_end=True,
    ) as span:
        response = await call()
        body_iterator = getattr(response, 'body_iterator', None)
        if body_iterator is not None:
            response.body_iterator = wrap_stream(span, body_iterator)
        else:
            tracer.finish_inference(span, response)
        return response
