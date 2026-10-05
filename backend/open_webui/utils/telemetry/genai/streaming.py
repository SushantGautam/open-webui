import asyncio
import logging

from open_webui.utils.telemetry.genai.config import GenAIConfig
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)


async def wrap_stream(span, async_iterator):
    ended = False
    try:
        async for item in async_iterator:
            yield item
        span.set_status(StatusCode.OK)
    except asyncio.CancelledError:
        span.set_status(StatusCode.ERROR)
        raise
    except BaseException as exc:
        if span.is_recording():
            span.add_event(
                'exception',
                {
                    'exception.type': type(exc).__name__,
                    'exception.message': str(exc)[: GenAIConfig().exception_max_length],
                },
            )
        span.set_status(StatusCode.ERROR)
        raise
    finally:
        if not ended:
            ended = True
            try:
                span.end()
            except Exception:
                logger.exception('Unable to end GenAI streaming span')
