from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pathlib import Path
import datetime
import uuid
from typing import Dict, List, Optional, Union, Any
from enum import Enum

from common.log import logger

_DEFAULT_PARTITION_KEY_PATH = "/type"

class WorldLineStatus(str, Enum):
    ALPHA = "alpha"
    BETA = "beta"
    STEINS_GATE = "steins_gate"
    DELTA = "delta"
    GAMMA = "gamma"
    OMEGA = "omega"

class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"

class FutureGadgetLabDataService:
    """Service for storing and retrieving research data from the Future Gadget Laboratory."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        mongodb_db: Optional[str] = None,
    ) -> None:
        self.mongodb_uri = mongodb_uri
        self.mongodb_db_name = mongodb_db
        self._mongo_client = None
        self._db = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize MongoDB backing storage."""
        if not self.mongodb_uri:
            # Fall back to tinydb for local dev without MongoDB
            from tinydb import TinyDB
            self._db = TinyDB("./data/fgl_data.json")
            self._experiments = self._db.table("experiments")
            self._readings = self._db.table("divergence_readings")
            self.storage_backend = "tinydb"
            logger.info("Using TinyDB (no MONGODB_URI provided)")
            return

        try:
            self._mongo_client = MongoClient(self.mongodb_uri)
            # Ping to verify connection
            self._mongo_client.admin.command('ping')
            self._db = self._mongo_client[self.mongodb_db_name]
            self.storage_backend = "mongodb"
            logger.info("Using MongoDB at %s/%s", self.mongodb_uri, self.mongodb_db_name)
            self._seed_mongodb_if_empty()
        except PyMongoError as exc:
            logger.error("Failed to connect to MongoDB: %s. Falling back to TinyDB.", exc)
            from tinydb import TinyDB
            self._db = TinyDB("./data/fgl_data.json")
            self._experiments = self._db.table("experiments")
            self._readings = self._db.table("divergence_readings")
            self.storage_backend = "tinydb"

    def _seed_mongodb_if_empty(self) -> None:
        """Seed MongoDB with test data if empty."""
        if self.storage_backend != "mongodb" or self._db is None:
            return

        try:
            count = self._db.experiments.count_documents({})
            if count > 0:
                return
        except PyMongoError as exc:
            logger.error("Failed to check MongoDB seed status: %s", exc)
            return

        logger.info("MongoDB empty. Seeding sample Future Gadget Lab data.")
        generate_test_data(self)

    # ----- EXPERIMENT CRUD -----

    def get_all_experiments(self) -> List[Dict]:
        if self.storage_backend == "mongodb":
            return list(self._db.experiments.find({}, {"_id": 0}))
        return self._experiments.all()

    def get_experiment_by_id(self, experiment_id: str) -> Optional[Dict]:
        if self.storage_backend == "mongodb":
            return self._db.experiments.find_one({"id": experiment_id}, {"_id": 0})
        for exp in self._experiments.all():
            if exp.get("id") == experiment_id:
                return exp
        return None

    def search_experiments(self, query_params: Dict) -> List[Dict]:
        if self.storage_backend == "mongodb":
            return list(self._db.experiments.find(query_params, {"_id": 0}))
        results = []
        for exp in self._experiments.all():
            if all(exp.get(k) == v for k, v in query_params.items()):
                results.append(exp)
        return results

    def create_experiment(self, experiment_data: Dict) -> Dict:
        prepared = self._prepare_experiment_payload(experiment_data)
        if self.storage_backend == "mongodb":
            self._db.experiments.insert_one(prepared)
            return prepared
        self._experiments.insert(prepared)
        return prepared

    def update_experiment(self, experiment_id: str, experiment_data: Dict) -> Optional[Dict]:
        existing = self.get_experiment_by_id(experiment_id)
        if not existing:
            return None
        update_payload = self._prepare_experiment_update_payload(experiment_data)
        if self.storage_backend == "mongodb":
            self._db.experiments.update_one({"id": experiment_id}, {"$set": update_payload})
            return self.get_experiment_by_id(experiment_id)
        for i, exp in enumerate(self._experiments.all()):
            if exp.get("id") == experiment_id:
                self._experiments.update(update_payload, doc_ids=[self._experiments.all()[i].doc_id])
        return self.get_experiment_by_id(experiment_id)

    def delete_experiment(self, experiment_id: str) -> bool:
        if self.storage_backend == "mongodb":
            result = self._db.experiments.delete_one({"id": experiment_id})
            return result.deleted_count > 0
        for i, exp in enumerate(self._experiments.all()):
            if exp.get("id") == experiment_id:
                self._experiments.remove(doc_ids=[exp.doc_id])
                return True
        return False

    # ----- DIVERGENCE READINGS CRUD -----

    def get_all_divergence_readings(self) -> List[Dict]:
        if self.storage_backend == "mongodb":
            return list(self._db.divergence_readings.find({}, {"_id": 0}))
        return self._readings.all()

    def get_divergence_reading_by_id(self, reading_id: str) -> Optional[Dict]:
        if self.storage_backend == "mongodb":
            return self._db.divergence_readings.find_one({"id": reading_id}, {"_id": 0})
        for r in self._readings.all():
            if r.get("id") == reading_id:
                return r
        return None

    def create_divergence_reading(self, reading_data: Dict) -> Dict:
        prepared = self._prepare_divergence_payload(reading_data)
        if self.storage_backend == "mongodb":
            self._db.divergence_readings.insert_one(prepared)
            return prepared
        self._readings.insert(prepared)
        return prepared

    def update_divergence_reading(self, reading_id: str, reading_data: Dict) -> Optional[Dict]:
        existing = self.get_divergence_reading_by_id(reading_id)
        if not existing:
            return None
        update_payload = self._prepare_divergence_update_payload(reading_data)
        if self.storage_backend == "mongodb":
            self._db.divergence_readings.update_one({"id": reading_id}, {"$set": update_payload})
            return self.get_divergence_reading_by_id(reading_id)
        for i, r in enumerate(self._readings.all()):
            if r.get("id") == reading_id:
                self._readings.update(update_payload, doc_ids=[r.doc_id])
        return self.get_divergence_reading_by_id(reading_id)

    def delete_divergence_reading(self, reading_id: str) -> bool:
        if self.storage_backend == "mongodb":
            result = self._db.divergence_readings.delete_one({"id": reading_id})
            return result.deleted_count > 0
        for i, r in enumerate(self._readings.all()):
            if r.get("id") == reading_id:
                self._readings.remove(doc_ids=[r.doc_id])
                return True
        return False

    def get_latest_divergence_reading(self) -> Optional[Dict]:
        if self.storage_backend == "mongodb":
            readings = list(self._db.divergence_readings.find({}, {"_id": 0}).sort("timestamp", -1).limit(1))
            return readings[0] if readings else None
        readings = self._readings.all()
        if not readings:
            return None
        return sorted(readings, key=lambda x: x.get("timestamp", ""), reverse=True)[0]

    # ----- HELPERS -----

    def _prepare_experiment_payload(self, experiment_data: Dict) -> Dict:
        payload = experiment_data.copy()
        if "id" not in payload:
            payload["id"] = f"EXP-{uuid.uuid4()}"
        if "created_at" not in payload:
            payload["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "world_line_change" in payload and isinstance(payload["world_line_change"], str):
            payload["world_line_change"] = float(payload["world_line_change"])
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return payload

    def _prepare_experiment_update_payload(self, update_data: Dict) -> Dict:
        payload = update_data.copy()
        payload.pop("id", None)
        if "world_line_change" in payload and isinstance(payload["world_line_change"], str):
            payload["world_line_change"] = float(payload["world_line_change"])
        payload["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return payload

    def _prepare_divergence_payload(self, reading_data: Dict) -> Dict:
        payload = reading_data.copy()
        if "id" not in payload:
            if self.storage_backend == "mongodb":
                count = self._db.divergence_readings.count_documents({})
                payload["id"] = f"DR-{count + 1:03d}"
            else:
                payload["id"] = f"DR-{uuid.uuid4()}"
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if "reading" in payload and isinstance(payload["reading"], str):
            payload["reading"] = float(payload["reading"])
        if "value" in payload and isinstance(payload["value"], str):
            payload["value"] = float(payload["value"])
        if "status" not in payload:
            payload["status"] = WorldLineStatus.ALPHA.value
        return payload

    def _prepare_divergence_update_payload(self, update_data: Dict) -> Dict:
        payload = update_data.copy()
        payload.pop("id", None)
        if "reading" in payload and isinstance(payload["reading"], str):
            payload["reading"] = float(payload["reading"])
        if "value" in payload and isinstance(payload["value"], str):
            payload["value"] = float(payload["value"])
        return payload

def generate_test_data(service: FutureGadgetLabDataService) -> Dict[str, List[Dict]]:
    """Generate test data for experiments and divergence readings."""
    created_items = {"experiments": [], "divergence_readings": []}

    def js_iso_format(dt: datetime.datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    current_time = datetime.datetime.now(datetime.timezone.utc)

    experiments = [
        {
            "name": "Phone Microwave (Name subject to change)",
            "description": "A microwave that can send text messages to the past",
            "status": ExperimentStatus.COMPLETED.value,
            "creator_id": "Rintaro Okabe",
            "collaborators": ["Kurisu Makise", "Itaru Hashida"],
            "results": "Successfully sent messages to the past, causing world line shifts",
            "world_line_change": 0.409431,
            "timestamp": js_iso_format(current_time),
        },
        {
            "name": "Divergence Meter",
            "description": "Device that measures the divergence between world lines",
            "status": ExperimentStatus.COMPLETED.value,
            "creator_id": "Kurisu Makise",
            "collaborators": ["Rintaro Okabe"],
            "results": "Accurately displays the current world line divergence value",
            "world_line_change": 0.000124,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=5)),
        },
        {
            "name": "Time Leap Machine",
            "description": "Device that allows transferring memories to the past self",
            "status": ExperimentStatus.COMPLETED.value,
            "creator_id": "Kurisu Makise",
            "collaborators": ["Rintaro Okabe", "Itaru Hashida"],
            "results": "Successfully allows transferring consciousness to past self within 48-hour limit",
            "world_line_change": -0.000337,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=10)),
        },
        {
            "name": "IBN 5100 Decoder",
            "description": "Using the IBN 5100 to decode SERN's classified database",
            "status": ExperimentStatus.FAILED.value,
            "creator_id": "Itaru Hashida",
            "collaborators": ["Suzuha Amane"],
            "results": "IBN 5100 was lost before project could be completed",
            "world_line_change": -0.048256,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=15)),
        },
        {
            "name": "Operation Skuld",
            "description": "Plan to reach Steins;Gate worldline and save Kurisu without changing observed history",
            "status": ExperimentStatus.COMPLETED.value,
            "creator_id": "Rintaro Okabe",
            "collaborators": ["Suzuha Amane"],
            "results": "Successfully reached Steins;Gate worldline while saving Kurisu",
            "world_line_change": 0.334137,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=20)),
        },
        {
            "name": "Jelly Person Experiment",
            "description": "Experiment attempting to transform a person into jelly-like state",
            "status": ExperimentStatus.FAILED.value,
            "creator_id": "Rintaro Okabe",
            "collaborators": ["Itaru Hashida"],
            "results": "Resulted in unstable human teleportation with catastrophic failure",
            "world_line_change": -0.275349,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=25)),
        },
        {
            "name": "D-Mail Recovery Operation",
            "description": "Operation to undo previous D-Mail effects",
            "status": ExperimentStatus.COMPLETED.value,
            "creator_id": "Rintaro Okabe",
            "collaborators": ["Kurisu Makise", "Moeka Kiryu"],
            "results": "Successfully undid effects of previous D-Mails, returning closer to Beta attractor field",
            "world_line_change": -0.412591,
            "timestamp": js_iso_format(current_time - datetime.timedelta(minutes=30)),
        },
    ]

    for exp_data in experiments:
        created_exp = service.create_experiment(exp_data)
        created_items["experiments"].append(created_exp)

    readings = [
        {
            "reading": 1.048596,
            "status": WorldLineStatus.STEINS_GATE.value,
            "recorded_by": "Rintaro Okabe",
            "notes": "Steins;Gate worldline - mission accomplished",
        },
        {
            "reading": 0.571024,
            "status": WorldLineStatus.ALPHA.value,
            "recorded_by": "Rintaro Okabe",
            "notes": "Alpha worldline - SERN dystopia",
        },
        {
            "reading": 0.523299,
            "status": WorldLineStatus.ALPHA.value,
            "recorded_by": "Rintaro Okabe",
            "notes": "Alpha worldline variant - Mayuri dies in different way",
        },
        {
            "reading": 1.130205,
            "status": WorldLineStatus.BETA.value,
            "recorded_by": "Suzuha Amane",
            "notes": "Beta worldline - World War 3 occurs",
        },
        {
            "reading": 1.382733,
            "status": WorldLineStatus.BETA.value,
            "recorded_by": "Suzuha Amane",
            "notes": "Beta worldline variant - Failed attempt to save Kurisu",
        },
    ]

    for reading_data in readings:
        created_reading = service.create_divergence_reading(reading_data)
        created_items["divergence_readings"].append(created_reading)

    return created_items

def calculate_worldline_status(experiments, readings=None):
    """Calculate the current worldline by summing all experiment divergences."""
    base_worldline = 1.0
    current_worldline = base_worldline

    for exp in experiments:
        if exp.get("world_line_change") is not None:
            current_worldline += exp.get("world_line_change", 0.0)

    last_timestamp = None
    if experiments:
        sorted_exps = sorted(
            [exp for exp in experiments if exp.get("timestamp")],
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )
        if sorted_exps:
            last_timestamp = sorted_exps[0].get("timestamp")

    response = {
        "current_worldline": round(current_worldline, 6),
        "base_worldline": base_worldline,
        "total_divergence": round(current_worldline - base_worldline, 6),
        "experiment_count": len(experiments),
        "last_experiment_timestamp": last_timestamp,
    }

    if readings:
        closest_reading = None
        min_distance = float("inf")
        for reading in readings:
            reading_value = reading.get("reading") or reading.get("value") or 0.0
            if isinstance(reading_value, str):
                try:
                    reading_value = float(reading_value)
                except ValueError:
                    reading_value = 0.0
            distance = abs(reading_value - current_worldline)
            if distance < min_distance:
                min_distance = distance
                closest_reading = reading

        if not closest_reading:
            closest_reading = {
                "reading": current_worldline,
                "status": "unknown",
                "recorded_by": "System",
                "notes": "No divergence readings available for comparison",
            }

        response["closest_reading"] = {
            "value": closest_reading.get("reading"),
            "status": closest_reading.get("status"),
            "recorded_by": closest_reading.get("recorded_by", "Unknown"),
            "notes": closest_reading.get("notes", ""),
            "distance": round(min_distance, 6),
        }

    return response