from fastapi import APIRouter, Security, HTTPException, Body, Path, Query, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from common.auth import azure_scheme, scopes
from common.log import logger
from common.role_based_access import required_roles
from common.socket import ConnectionManager
from db.future_gadget_lab_data_service import (
    FutureGadgetLabDataService,
    ExperimentStatus,
    calculate_worldline_status,
)

from common.config import mock_enabled, tfconfig

future_gadget_api_router = APIRouter(tags=["Future Gadget Lab"])

# Initialize data service based on environment
# Priority: MONGODB_URI env var > mock (TinyDB) for local dev
import os

mongodb_uri = os.environ.get("MONGODB_URI")
mongodb_db = os.environ.get("MONGODB_DB", "future_gadget_lab")

if mongodb_uri:
    # Use MongoDB in k8s
    fgl_service = FutureGadgetLabDataService(
        mongodb_uri=mongodb_uri,
        mongodb_db=mongodb_db,
    )
elif mock_enabled:
    # Use TinyDB for local dev mock mode
    from mock.mock_future_gadget_lab_data_service import MockFutureGadgetLabDataService
    fgl_service = MockFutureGadgetLabDataService()
else:
    # Production non-mock: require MongoDB
    raise RuntimeError(
        "MONGODB_URI environment variable is required when MOCK=false. "
        "Please set MONGODB_URI to connect to the MongoDB instance."
    )

# WebSocket connection managers
experiment_connection_manager = ConnectionManager(
    receiver_roles=["Admin"],
    sender_roles=["Admin"]
)

worldline_connection_manager = ConnectionManager(
    receiver_roles=None,
    sender_roles=["Admin"]
)

# --- Pydantic Models ---

class ExperimentBase(BaseModel):
    name: str
    description: str
    status: ExperimentStatus
    creator_id: str
    collaborators: List[str] = []
    results: Optional[str] = None
    world_line_change: Optional[float] = None
    timestamp: Optional[str] = None

    @field_validator("world_line_change", mode="before")
    @classmethod
    def parse_world_line_change(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            return float(v)
        return v

class ExperimentCreate(ExperimentBase):
    pass

class ExperimentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    creator_id: Optional[str] = None
    collaborators: Optional[List[str]] = None
    results: Optional[str] = None
    world_line_change: Optional[float] = None

    @field_validator("world_line_change", mode="before")
    @classmethod
    def parse_world_line_change(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            return float(v)
        return v

class DivergenceReadingBase(BaseModel):
    reading: float
    status: str
    recorded_by: str
    notes: Optional[str] = None

class DivergenceReadingCreate(DivergenceReadingBase):
    pass

# --- REST Endpoints ---

@future_gadget_api_router.get("/experiments", response_model=List[Dict])
async def get_experiments():
    return fgl_service.get_all_experiments()

@future_gadget_api_router.get("/experiments/{experiment_id}", response_model=Dict)
async def get_experiment(experiment_id: str):
    exp = fgl_service.get_experiment_by_id(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp

@future_gadget_api_router.post("/experiments", response_model=Dict)
async def create_experiment(exp: ExperimentCreate):
    return fgl_service.create_experiment(exp.model_dump())

@future_gadget_api_router.put("/experiments/{experiment_id}", response_model=Dict)
async def update_experiment(experiment_id: str, exp: ExperimentUpdate):
    updated = fgl_service.update_experiment(experiment_id, exp.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return updated

@future_gadget_api_router.delete("/experiments/{experiment_id}")
async def delete_experiment(experiment_id: str):
    if not fgl_service.delete_experiment(experiment_id):
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"status": "deleted"}

@future_gadget_api_router.get("/divergence-readings", response_model=List[Dict])
async def get_divergence_readings():
    return fgl_service.get_all_divergence_readings()

@future_gadget_api_router.get("/divergence-readings/latest", response_model=Dict)
async def get_latest_divergence_reading():
    reading = fgl_service.get_latest_divergence_reading()
    if not reading:
        raise HTTPException(status_code=404, detail="No divergence readings found")
    return reading

@future_gadget_api_router.post("/divergence-readings", response_model=Dict)
async def create_divergence_reading(reading: DivergenceReadingCreate):
    return fgl_service.create_divergence_reading(reading.model_dump())

@future_gadget_api_router.get("/worldline/status", response_model=Dict)
async def get_worldline_status():
    experiments = fgl_service.get_all_experiments()
    readings = fgl_service.get_all_divergence_readings()
    return calculate_worldline_status(experiments, readings)

# --- WebSocket Endpoints ---

@future_gadget_api_router.websocket("/ws/experiments")
async def experiments_websocket(websocket: WebSocket):
    await experiment_connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"status": "received", "data": data})
    except WebSocketDisconnect:
        experiment_connection_manager.disconnect(websocket)

@future_gadget_api_router.websocket("/ws/worldline")
async def worldline_websocket(websocket: WebSocket):
    await worldline_connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"status": "received", "data": data})
    except WebSocketDisconnect:
        worldline_connection_manager.disconnect(websocket)