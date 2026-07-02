import asyncio
import json
import logging
import websockets
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

class UpstoxV3SubscriptionManager:
    """
    Manages the Upstox V3 Portfolio WebSocket stream.
    Re-implements the Phase 4 architectural findings:
    Listens for 'order' and 'trade' payloads to update local state in real time.
    """
    def __init__(self, wss_url: str, token: str, on_message_callback: Callable[[dict], Awaitable[None]]):
        self.wss_url = wss_url
        self.token = token
        self.on_message_callback = on_message_callback
        self._running = False
        self._ws = None

    async def connect_and_listen(self):
        self._running = True
        headers = {"Authorization": f"Bearer {self.token}"}
        
        while self._running:
            try:
                logger.info("Connecting to Upstox V3 WebSocket...")
                async with websockets.connect(self.wss_url, additional_headers=headers) as ws:
                    self._ws = ws
                    logger.info("Upstox V3 WebSocket Connected.")
                    await self._listen_loop()
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Upstox WS Closed: {e}. Reconnecting in 5s...")
            except Exception as e:
                logger.error(f"Upstox WS Error: {e}. Reconnecting in 5s...")
            
            if self._running:
                await asyncio.sleep(5)

    async def _listen_loop(self):
        while self._running and self._ws:
            message = await self._ws.recv()
            try:
                data = json.loads(message)
                if data.get("type") in ["order", "trade"]:
                    await self.on_message_callback(data)
            except Exception as e:
                logger.error(f"Error processing Upstox WS message: {e}")

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
            logger.info("Upstox V3 WebSocket Disconnected.")
