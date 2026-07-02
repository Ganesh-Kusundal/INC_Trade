import os
import json
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class IdempotencyCache:
    """
    Prevents duplicate execution of critical commands (like place_order) during network retries.
    Follows the fail-safe principles audited in Phase 5:
    Memory primary -> FileSystem fallback.
    """
    def __init__(self, fallback_dir: str = ".cache/idempotency"):
        self.fallback_dir = fallback_dir
        self._memory_cache = {}
        if not os.path.exists(self.fallback_dir):
            os.makedirs(self.fallback_dir, exist_ok=True)

    def check_and_set(self, correlation_id: str) -> bool:
        """
        Returns True if the ID was successfully set (first time seen).
        Returns False if the ID already exists (duplicate detected).
        """
        # Primary check
        if correlation_id in self._memory_cache:
            logger.warning(f"Idempotency hit (Memory): {correlation_id}. Duplicate request blocked.")
            return False

        # Fallback file check
        file_path = os.path.join(self.fallback_dir, f"{correlation_id}.json")
        if os.path.exists(file_path):
            logger.warning(f"Idempotency hit (FileSystem): {correlation_id}. Duplicate request blocked.")
            return False

        # Set
        self._memory_cache[correlation_id] = datetime.utcnow().isoformat()
        try:
            with open(file_path, 'w') as f:
                json.dump({"timestamp": self._memory_cache[correlation_id]}, f)
        except Exception as e:
            logger.error(f"Failed to write idempotency fallback for {correlation_id}: {e}")
            
        return True

    def remove(self, correlation_id: str):
        if correlation_id in self._memory_cache:
            del self._memory_cache[correlation_id]
        
        file_path = os.path.join(self.fallback_dir, f"{correlation_id}.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
