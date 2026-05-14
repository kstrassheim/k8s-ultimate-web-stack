"""Mock implementation of the Future Gadget Lab data service using in-memory TinyDB storage."""

from __future__ import annotations

from typing import Optional
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from common.log import logger
from db.future_gadget_lab_data_service import FutureGadgetLabDataService, generate_test_data


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
        # Seed mock data so e2e tests have predictable values to assert against
        try:
            generate_test_data(self)
            logger.info("Mock data seeded successfully")
        except Exception as exc:
            logger.warning("Failed to seed mock data: %s", exc)

    # Property aliases for test compatibility (tests reference .experiments_table etc.)
    @property
    def experiments_table(self):
        return self._experiments

    @property
    def divergence_readings_table(self):
        return self._readings
