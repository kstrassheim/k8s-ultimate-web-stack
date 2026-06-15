"""Mock implementation of the Future Gadget Lab data service using in-memory mongomock storage."""

from __future__ import annotations

from typing import Optional
import mongomock

from db.future_gadget_lab_data_service import FutureGadgetLabDataService


class MockFutureGadgetLabDataService(FutureGadgetLabDataService):
    """In-memory mock data service for local development and testing."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        mongodb_db: Optional[str] = None,
    ) -> None:
        super().__init__(mongodb_db="future_gadget_lab_mock", client=mongomock.MongoClient())

    # Property aliases for test compatibility (tests reference .experiments_table etc.)
    @property
    def experiments_table(self):
        return self._db.experiments

    @property
    def divergence_readings_table(self):
        return self._db.divergence_readings
