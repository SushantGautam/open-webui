"""Inference spans following the OTel GenAI client inference conventions."""

from collections.abc import Awaitable, Callable

from open_webui.utils.telemetry.genai.content import StreamCapture
from open_webui.utils.telemetry.genai.purpose import purpose_for_task
from open_webui.utils.telemetry.genai.streaming import wrap_stream


async def traced_inference(tracer, *, provider: str, request_payload: dict, call: Callable[[], Awaitable]):
    payload = request_payload if isinstance(request_payload, dict) else {}
    metadata = payload.get('metadata') or {}
    purpose = purpose_for_task(metadata.get('task'))
    model = payload.get('model')
    name = f'chat {model}' if model else 'chat'
    # Capture the *actual* provider request history, not a prose summary.
    # Inline system messages belong in input.messages; system_instructions is
    # only for APIs with a distinct system-instruction parameter.
    with tracer.inference(
        name,
        operation_name='chat',
        provider=provider,
        request_model=model,
        inputs=payload.get('messages'),
        system_instructions=payload.get('system') if isinstance(payload.get('system'), (str, list)) else None,
        temperature=payload.get('temperature'),
        top_p=payload.get('top_p'),
        max_tokens=payload.get('max_tokens', payload.get('max_completion_tokens')),
        seed=payload.get('seed'),
        purpose=purpose,
        _defer_end=True,
    ) as span:
        response = await call()
        body_iterator = getattr(response, 'body_iterator', None)
        if body_iterator is not None:
            stream = StreamCapture(tracer.config)
            response.body_iterator = wrap_stream(
                span,
                body_iterator,
                on_item=stream.feed,
                on_finish=lambda: tracer.finish_stream(span, stream),
            )
        else:
            tracer.finish_inference(span, response)
        return response
