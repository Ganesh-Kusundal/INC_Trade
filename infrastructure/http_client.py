import httpx
import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class BaseResilientHttpClient:
    """
    A unified HTTP client providing exponential backoff, jitter, and 429 rate limit circuit breaking.
    """
    def __init__(self, base_url: str = "", timeout: float = 15.0):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._backoff_until: float = 0.0
        
    async def _check_backoff(self):
        import time
        now = time.time()
        if now < self._backoff_until:
            wait_time = self._backoff_until - now
            logger.warning(f"Rate limited. Backing off for {wait_time:.2f}s")
            await asyncio.sleep(wait_time)

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        retries = 3
        base_delay = 1.0
        
        for attempt in range(retries):
            await self._check_backoff()
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code == 429:
                    import time
                    # Dhan specific penalty
                    self._backoff_until = time.time() + 60.0 
                    raise httpx.HTTPStatusError("429 Too Many Requests", request=response.request, response=response)
                response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt == retries - 1:
                    raise
                import random
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                
        raise RuntimeError("Unreachable")
        
    async def close(self):
        await self.client.aclose()
