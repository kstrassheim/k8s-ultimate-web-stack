"""Mock implementation of the Future Gadget Lab data service using in-memory TinyDB storage."""

from __future__ import annotations

from typing import Optional
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from common.log import logger
from db.future_gadget_lab_data_service import FutureGadgetLabDataService


class MockFutureGadgetLabDataService(FutureGadgetLabDataService):
    """In-memory mock data service for local development and testing."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        mongodb_db: Optional[str] = None,
    ) -> None:
        # Pass None for mongodb_uri to force tinydb fallback
        super().__init__(mongodb_uri=None, mongodb_db=None)

    def _initialize_db(self) -> None:  # type: ignore[override]
        logger.info("Using in-memory TinyDB storage for MockFutureGadgetLabDataService")
        self.storage_backend = "tinydb"
        self.db = TinyDB(storage=MemoryStorage)  # type: ignore[assignment]
        self._experiments = self.db.table("experiments")
        self._readings = self.db.table("divergence_readings")