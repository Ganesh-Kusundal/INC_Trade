"""Request/Response pipeline framework.

Provides middleware-style processing for API requests and responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


@dataclass
class PipelineContext(Generic[RequestT, ResponseT]):
    """Context passed through the pipeline."""

    request: RequestT
    response: Optional[ResponseT] = None
    error: Optional[Exception] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    endpoint: str = ""


# Middleware type: async function that receives context and calls next
Middleware = Callable[
    [PipelineContext[Any, Any], Callable[[], Awaitable[PipelineContext[Any, Any]]]],
    Awaitable[PipelineContext[Any, Any]],
]


class RequestPipeline(Generic[RequestT, ResponseT]):
    """Request/response pipeline with middleware support.

    Middleware is executed in order for requests, and in reverse for responses.
    Similar to HTTP middleware in web frameworks.
    """

    def __init__(self) -> None:
        self._pre_middlewares: list[Middleware] = []
        self._post_middlewares: list[Middleware] = []
        self._handler: Optional[Callable[..., Awaitable[ResponseT]]] = None

    def use_pre(self, middleware: Middleware) -> RequestPipeline[RequestT, ResponseT]:
        """Add a pre-request middleware."""
        self._pre_middlewares.append(middleware)
        return self

    def use_post(self, middleware: Middleware) -> RequestPipeline[RequestT, ResponseT]:
        """Add a post-response middleware."""
        self._post_middlewares.append(middleware)
        return self

    def set_handler(
        self, handler: Callable[..., Awaitable[ResponseT]]
    ) -> RequestPipeline[RequestT, ResponseT]:
        """Set the actual request handler."""
        self._handler = handler
        return self

    async def execute(
        self, request: RequestT, **kwargs: Any
    ) -> PipelineContext[RequestT, ResponseT]:
        """Execute the pipeline with the given request."""
        if not self._handler:
            raise RuntimeError("No handler set on pipeline")

        ctx = PipelineContext(request=request, **kwargs)

        # Build the middleware chain
        async def _execute_chain() -> PipelineContext[RequestT, ResponseT]:
            # Execute pre-middlewares
            current_ctx = ctx
            for mw in self._pre_middlewares:
                current_ctx = await mw(current_ctx, lambda: _execute_chain_inner(current_ctx))
                if current_ctx.response is not None or current_ctx.error is not None:
                    return current_ctx

            # Execute handler
            try:
                response = await self._handler(current_ctx.request)
                current_ctx.response = response
            except Exception as e:
                current_ctx.error = e

            return current_ctx

        async def _execute_chain_inner(
            inner_ctx: PipelineContext[RequestT, ResponseT],
        ) -> PipelineContext[RequestT, ResponseT]:
            return await _execute_chain()

        result = await _execute_chain()

        # Execute post-middlewares
        for mw in self._post_middlewares:
            result = await mw(result, lambda: _post_chain_next(result))

        return result


async def _post_chain_next(ctx: PipelineContext[Any, Any]) -> PipelineContext[Any, Any]:
    """Default post-chain handler (pass-through)."""
    return ctx
