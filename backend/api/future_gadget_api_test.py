import pytest
import sys
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import patch, MagicMock, AsyncMock
from types import SimpleNamespace
from fastapi import WebSocketDisconnect
import datetime

from api.future_gadget_api import future_gadget_api_router
from common.auth import azure_scheme
from common.role_based_access import required_roles
from common.log import logger

# Create a test app using the actual router
app = FastAPI()
app.include_router(future_gadget_api_router)
client = TestClient(app)
API_PREFIX = ""

# Fixture to override security and logging similar to api_test.py
@pytest.fixture
def mock_dependencies():
    mock_token = SimpleNamespace(roles=["Admin"])
    with patch("api.future_gadget_api.azure_scheme") as mock_scheme, \
         patch("api.future_gadget_api.required_roles", return_value=lambda f: f), \
         patch("api.future_gadget_api.logger") as mock_logger:
        mock_scheme.return_value = mock_token
        yield {
            "token": mock_token,
            "scheme": mock_scheme,
            "logger": mock_logger
        }

# Fixture to override dependencies in the app for integration testing
@pytest.fixture
def client_with_overridden_dependencies():
    test_app = FastAPI()
    mock_token = SimpleNamespace(roles=["Admin"])

    async def override_security_dependency():
        return mock_token

    with patch("api.future_gadget_api.logger") as mock_logger:
        test_app.dependency_overrides[azure_scheme] = override_security_dependency
        test_app.include_router(future_gadget_api_router)
        test_client = TestClient(test_app)
        yield test_client, mock_logger

# New fixture to patch the fgl_service with dummy CRUD behavior
@pytest.fixture
def setup_fgl_service():
    with patch("api.future_gadget_api.fgl_service") as mock_service:
        # Current timestamp
        current_time = datetime.datetime.now().isoformat()
        
        # Dummy experiment that already exists
        experiment_data = {
            "id": "FG-01",
            "name": "Phone Microwave",
            "description": "A microwave that sends text messages to the past",
            "status": "completed",
            "creator_id": "001",
            "collaborators": [],
            "world_line_change": 0.337192,
            "timestamp": current_time
        }
        mock_service.get_all_experiments.return_value = [experiment_data]
        mock_service.get_experiment_by_id.return_value = experiment_data
        mock_service.create_experiment.return_value = {
            "id": "FG-02",
            "name": "New Experiment",
            "description": "Test experiment",
            "status": "planned",
            "creator_id": "001",
            "collaborators": [],
            "world_line_change": 0.409431,
            "timestamp": current_time
        }
        mock_service.update_experiment.return_value = {
            "id": "FG-01",
            "name": "Updated Experiment",
            "description": "Updated description",
            "status": "completed",
            "creator_id": "001",
            "collaborators": [],
            "world_line_change": 0.571024,
            "timestamp": current_time
        }
        mock_service.delete_experiment.return_value = True
        
        # Mock divergence reading data for worldline calculations
        mock_service.get_all_divergence_readings.return_value = [
            {
                "id": "DR-001",
                "reading": 1.048596,
                "status": "steins_gate",
                "recorded_by": "Rintaro Okabe",
                "notes": "Steins;Gate worldline"
            }
        ]
        
        yield mock_service

# Add this fixture at the module level, outside of any class

@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket object with all necessary attributes"""
    mock_ws = MagicMock()
    
    # Set up the state with user info
    mock_ws.state = MagicMock()
    mock_ws.state.user = MagicMock()
    mock_ws.state.user.name = "Test User"
    mock_ws.state.user.sub = "test-id"
    mock_ws.state.user.roles = ["Admin"]
    
    # Set up receive_text that can be overridden in tests
    mock_ws.receive_text = AsyncMock(return_value="Hello, WebSocket!")
    
    # Set up send_text method
    async def mock_send_text(message):
        mock_ws.sent_messages = getattr(mock_ws, 'sent_messages', [])
        mock_ws.sent_messages.append(message)
    
    mock_ws.send_text = mock_send_text
    
    # Set up send_json method
    async def mock_send_json(data):
        mock_ws.sent_json = getattr(mock_ws, 'sent_json', [])
        mock_ws.sent_json.append(data)
    
    mock_ws.send_json = mock_send_json
    
    return mock_ws


class TestExperimentEndpoints:
    """Test the experiment endpoints with updated paths and fields"""

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_get_all_experiments(self, client_with_overridden_dependencies, setup_fgl_service):
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.get_all_experiments", return_value=[
            {
                "id": "EXP-001",
                "name": "Phone Microwave",
                "description": "Send messages to the past",
                "status": "in_progress",
                "creator_id": "001",
                "collaborators": ["002", "003"],
                "results": None,
                "world_line_change": 0.337192,
                "timestamp": current_time
            }
        ]):
            test_client, _ = client_with_overridden_dependencies
            # Use the correct lab-experiments route
            response = test_client.get(f"{API_PREFIX}/lab-experiments")
            assert response.status_code == 200
            experiments = response.json()
            assert isinstance(experiments, list)
            assert experiments[0]["id"] == "EXP-001"
            assert experiments[0]["world_line_change"] == 0.337192
            assert "timestamp" in experiments[0]

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_get_experiment_by_id(self, client_with_overridden_dependencies, setup_fgl_service):
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.get_experiment_by_id", return_value={
            "id": "EXP-001",
            "name": "Phone Microwave",
            "description": "Send messages to the past",
            "status": "in_progress",
            "creator_id": "001",
            "collaborators": ["002", "003"],
            "results": None,
            "world_line_change": 0.409431,
            "timestamp": current_time
        }):
            test_client, _ = client_with_overridden_dependencies
            # Updated from /experiments to /lab-experiments
            response = test_client.get(f"{API_PREFIX}/lab-experiments/EXP-001")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "EXP-001"
            assert data["world_line_change"] == 0.409431
            assert "timestamp" in data

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_create_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: the k8s-port's create_experiment does
        # not call broadcast_worldline_status (that helper was removed
        # when the parent-repo WebSocket plumbing was stripped — see
        # disposition in the PR). Verify only the HTTP contract: the
        # service is called with the dumped model and the returned row
        # comes back through the response.
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.create_experiment", return_value={
            "id": "EXP-002",
            "name": "Time Leap Machine",
            "description": "Transfer memories to the past",
            "status": "planned",
            "creator_id": "001",
            "collaborators": ["002"],
            "results": None,
            "world_line_change": 0.000337,
            "timestamp": current_time,
        }) as mock_create:
            test_client, _ = client_with_overridden_dependencies
            new_experiment = {
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": 0.000337,
            }
            response = test_client.post(
                f"{API_PREFIX}/lab-experiments", json=new_experiment
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["id"] == "EXP-002"
            assert data["world_line_change"] == 0.000337
            assert data["timestamp"] == current_time
            # The service was called with the dumped Pydantic model.
            mock_create.assert_called_once()
            kwargs = mock_create.call_args.args[0]
            assert kwargs["name"] == "Time Leap Machine"
            assert kwargs["world_line_change"] == 0.000337

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_create_experiment_with_string_world_line_change(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: removed broadcast_worldline_status
        # references, but the string->float coercion still happens in
        # the Pydantic field_validator on the request model.
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.create_experiment", return_value={
            "id": "EXP-002",
            "name": "Time Leap Machine",
            "description": "Transfer memories to the past",
            "status": "planned",
            "creator_id": "001",
            "collaborators": ["002"],
            "results": None,
            "world_line_change": 0.000337,
            "timestamp": current_time,
        }):
            test_client, _ = client_with_overridden_dependencies
            new_experiment = {
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": "0.000337",  # String, validator converts
            }
            response = test_client.post(
                f"{API_PREFIX}/lab-experiments", json=new_experiment
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["world_line_change"] == 0.000337
            assert isinstance(data["world_line_change"], float)

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_update_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: removed broadcast_worldline_status
        # references. Verify only the HTTP contract.
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.update_experiment", return_value={
            "id": "EXP-001",
            "name": "Phone Microwave (Name subject to change)",
            "description": "Send messages to the past",
            "status": "completed",
            "creator_id": "001",
            "collaborators": ["002", "003"],
            "results": "Successful test with banana",
            "world_line_change": 0.571024,
            "timestamp": current_time,
        }) as mock_update:
            test_client, _ = client_with_overridden_dependencies
            update_data = {
                "name": "Phone Microwave (Name subject to change)",
                "status": "completed",
                "results": "Successful test with banana",
                "world_line_change": 0.571024,
            }
            response = test_client.put(
                f"{API_PREFIX}/lab-experiments/EXP-001", json=update_data
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["name"] == "Phone Microwave (Name subject to change)"
            assert data["status"] == "completed"
            assert data["world_line_change"] == 0.571024
            # The service was called with the id and the dumped model
            # (exclude_unset=True means unset fields are dropped).
            mock_update.assert_called_once()
            args = mock_update.call_args.args
            assert args[0] == "EXP-001"
            assert args[1]["name"] == "Phone Microwave (Name subject to change)"
            # Unset fields should not be in the dumped dict.
            assert "description" not in args[1]
            assert "creator_id" not in args[1]

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_delete_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: the k8s-port's delete endpoint
        # returns {"status": "deleted"} rather than the parent-repo
        # {"message": "Experiment EXP-001 successfully deleted..."}.
        with patch("api.future_gadget_api.fgl_service.delete_experiment", return_value=True) as mock_delete:
            test_client, _ = client_with_overridden_dependencies
            response = test_client.delete(f"{API_PREFIX}/lab-experiments/EXP-001")
            assert response.status_code == 200, response.text
            assert response.json() == {"status": "deleted"}
            mock_delete.assert_called_once_with("EXP-001")

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_get_divergence_readings(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: the k8s-port endpoint returns the
        # full list with no filtering (status / recorded_by / value
        # filters were part of the parent-repo contract and were
        # removed when the port was simplified). Verify the basic
        # shape and that all readings come back.
        sample_readings = [
            {"id": "DR-001", "reading": 1.048596, "status": "steins_gate",
             "recorded_by": "Rintaro Okabe", "notes": "Steins;Gate worldline"},
            {"id": "DR-002", "reading": 0.571024, "status": "alpha",
             "recorded_by": "Rintaro Okabe", "notes": "Alpha worldline"},
            {"id": "DR-003", "reading": 1.382733, "status": "beta",
             "recorded_by": "Suzuha Amane", "notes": "Beta worldline variant"},
        ]

        with patch("api.future_gadget_api.fgl_service.get_all_divergence_readings",
                   return_value=sample_readings):
            test_client, _ = client_with_overridden_dependencies

            response = test_client.get(f"{API_PREFIX}/divergence-readings")
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data) == 3
            assert data[0]["id"] == "DR-001"
            assert data[0]["reading"] == 1.048596
            assert data[0]["status"] == "steins_gate"

    # Rewritten for k8s-port: the path is valid (both /lab-experiments and /experiments are registered).
    def test_non_admin_access_to_divergence_readings(self, setup_fgl_service):
        """Test non-admin users can access the divergence readings endpoint"""
        # Create special test app with normal user token
        test_app = FastAPI()
        mock_token = SimpleNamespace(roles=["User"])  # Non-admin token

        async def override_security_dependency():
            return mock_token

        # Set up overrides
        test_app.dependency_overrides[azure_scheme] = override_security_dependency
        test_app.include_router(future_gadget_api_router)
        test_client = TestClient(test_app)
        
        # Mock readings data
        sample_readings = [
            {
                "id": "DR-001",
                "reading": 1.048596,
                "status": "steins_gate",
                "recorded_by": "Rintaro Okabe"
            }
        ]
        
        with patch("api.future_gadget_api.fgl_service.get_all_divergence_readings", return_value=sample_readings):
            # Normal user should be able to access this endpoint
            response = test_client.get(f"{API_PREFIX}/divergence-readings")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "DR-001"


class TestWorldlineEndpoints:
    """Test the new worldline status endpoints and features"""
    
    def test_get_worldline_status(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: the k8s-port does NOT add a "timestamp"
        # key to the response (that was a parent-repo field), but
        # otherwise the contract is the same.
        mock_status = {
            "current_worldline": 1.337192,
            "base_worldline": 1.0,
            "total_divergence": 0.337192,
            "experiment_count": 5,
            "last_experiment_timestamp": "2025-04-07T12:00:00.000Z",
            "closest_reading": {
                "value": 1.382733,
                "status": "beta",
                "recorded_by": "Suzuha Amane",
                "notes": "Beta worldline variant",
                "distance": 0.045541,
            },
        }

        with patch("api.future_gadget_api.calculate_worldline_status",
                   return_value=mock_status):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get(f"{API_PREFIX}/worldline-status")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["current_worldline"] == 1.337192
            assert data["base_worldline"] == 1.0
            assert data["total_divergence"] == 0.337192
            assert data["experiment_count"] == 5
            assert data["closest_reading"]["value"] == 1.382733
            assert data["closest_reading"]["status"] == "beta"
    
    def test_get_worldline_history(self, client_with_overridden_dependencies, setup_fgl_service):
        # Rewritten for k8s-port: the k8s-port version of
        # get_worldline_history DOES exist — it builds a chronological
        # list from experiments + readings — but the response shape is
        # different from the parent-repo mock the skip was based on:
        # no `base_worldline`, `total_divergence`, `experiment_count`,
        # `added_experiment` keys. Verify the actual contract.
        sorted_experiments = [
            {
                "id": "EXP-001",
                "name": "Test Experiment 1",
                "status": "completed",
                "world_line_change": 0.337192,
                "timestamp": "2025-04-07T12:00:00.000Z",
            },
        ]
        readings = [
            {
                "id": "DR-001",
                "reading": 1.048596,
                "status": "steins_gate",
                "recorded_by": "Rintaro Okabe",
                "timestamp": "2025-04-07T13:00:00.000Z",
            },
        ]

        with patch("api.future_gadget_api.fgl_service.get_all_experiments",
                   return_value=sorted_experiments), \
             patch("api.future_gadget_api.fgl_service.get_all_divergence_readings",
                   return_value=readings):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get(f"{API_PREFIX}/worldline-history")
            assert response.status_code == 200, response.text
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2
            # First entry is the experiment (with its running total).
            assert data[0]["experiment_name"] == "Test Experiment 1"
            assert data[0]["current_worldline"] == round(1.0 + 0.337192, 6)
            # Second entry is the reading.
            assert data[1]["recorded_by"] == "Rintaro Okabe"
            assert data[1]["current_worldline"] == 1.048596
    
    # DELETED: `broadcast_worldline_status` was the parent-repo's
    # standalone worldline-broadcast helper, and the
    # `worldline_websocket_endpoint` test referenced a renamed-and-
    # simplified worldline_websocket handler that lost the
    # auto-status-on-message behaviour. Both removed because the
    # parent-repo WebSocket plumbing for mutations was stripped when
    # the k8s-port was forked off. Dead code on both sides — gone.

    # ---------------------------------------------------------------------------
# Issue #113 — server-side auth on /future-gadget-lab/*
#
# The original implementation accepted any request without authentication on
# both the REST endpoints and the two WebSocket endpoints. These tests pin
# the new contract:
#
#   * every REST route requires a valid bearer token (401 without one);
#   * mutations additionally require the `Admin` role (403 for plain Users);
#   * the WebSocket handlers call `auth_connect()` (not the unauth `connect()`),
#     so the manager's `receiver_roles` actually get enforced and a connection
#     without a token frame is closed with code 1008.
# ---------------------------------------------------------------------------


class TestRestEndpointCoverage:
    """Coverage for REST endpoints and field validators that the
    existing tests don't exercise. Each test pins a specific branch
    in api/future_gadget_api.py so the 100% coverage goal holds."""

    def test_get_experiment_by_id_404_when_missing(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """`get_experiment` raises HTTPException(404) when the service
        returns no record. Pins the `if not exp: raise ...` branch.
        """
        with patch("api.future_gadget_api.fgl_service.get_experiment_by_id",
                   return_value=None):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get("/lab-experiments/does-not-exist")
            assert response.status_code == 404
            assert response.json()["detail"] == "Experiment not found"

    def test_update_experiment_404_when_missing(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """`update_experiment` raises HTTPException(404) when the
        service returns no record (the service's `update_experiment`
        returns None on a miss)."""
        with patch("api.future_gadget_api.fgl_service.update_experiment",
                   return_value=None):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.put(
                "/lab-experiments/does-not-exist", json={"name": "x"}
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Experiment not found"

    def test_get_latest_divergence_reading_404_when_empty(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """`get_latest_divergence_reading` raises HTTPException(404)
        when the service returns no record."""
        with patch("api.future_gadget_api.fgl_service.get_latest_divergence_reading",
                   return_value=None):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get("/divergence-readings/latest")
            assert response.status_code == 404
            assert response.json()["detail"] == "No divergence readings found"

    def test_get_latest_divergence_reading_returns_record(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """The success path of `get_latest_divergence_reading`:
        the service returns a row, the endpoint forwards it through."""
        current_time = datetime.datetime.now().isoformat()
        record = {
            "id": "DR-LATEST",
            "reading": 1.048596,
            "status": "steins_gate",
            "recorded_by": "Rintaro Okabe",
            "timestamp": current_time,
        }
        with patch("api.future_gadget_api.fgl_service.get_latest_divergence_reading",
                   return_value=record):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get("/divergence-readings/latest")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["id"] == "DR-LATEST"
            assert data["reading"] == 1.048596
            assert data["status"] == "steins_gate"

    def test_create_divergence_reading_happy_path(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """`create_divergence_reading` returns the inserted record from
        the service. The endpoint body is just `return fgl_service
        .create_divergence_reading(...)` so the happy path is one line
        but it's not exercised by the existing mutation tests (those
        target /experiments)."""
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.fgl_service.create_divergence_reading",
                   return_value={
                       "id": "DR-NEW",
                       "reading": 1.048596,
                       "status": "steins_gate",
                       "recorded_by": "Rintaro Okabe",
                       "notes": "Steins;Gate worldline",
                       "timestamp": current_time,
                   }) as mock_create:
            test_client, _ = client_with_overridden_dependencies
            response = test_client.post(
                "/divergence-readings",
                json={
                    "reading": 1.048596,
                    "status": "steins_gate",
                    "recorded_by": "Rintaro Okabe",
                    "notes": "Steins;Gate worldline",
                },
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["id"] == "DR-NEW"
            assert data["reading"] == 1.048596
            mock_create.assert_called_once()

    def test_get_worldline_history_string_reading_falls_back_to_zero(
        self, client_with_overridden_dependencies, setup_fgl_service
    ):
        """`get_worldline_history` tolerates a `reading` field that's a
        non-numeric string by falling back to 0.0 (same ValueError
        handling as `calculate_worldline_status`). Pins the
        `try: float(...) except ValueError: 0.0` branch.
        """
        with patch("api.future_gadget_api.fgl_service.get_all_experiments",
                   return_value=[]), \
             patch("api.future_gadget_api.fgl_service.get_all_divergence_readings",
                   return_value=[{
                       "id": "DR-BAD",
                       "reading": "not-a-number",
                       "status": "alpha",
                       "recorded_by": "Test",
                       "timestamp": "2025-04-07T12:00:00.000Z",
                   }]):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get("/worldline-history")
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data) == 1
            assert data[0]["current_worldline"] == 0.0
            assert data[0]["recorded_by"] == "Test"


class TestPydanticValidators:
    """Coverage for the two `parse_world_line_change` field_validators
    on ExperimentBase (line 74) and ExperimentUpdate (lines 95, 97).
    The validators run on every request through the model — pinning the
    string->float and passthrough branches."""
    from api.future_gadget_api import ExperimentBase, ExperimentUpdate

    def test_experiment_base_validator_converts_string_to_float(self):
        """`ExperimentBase.parse_world_line_change("0.337192")`
        returns the parsed float."""
        result = self.ExperimentBase.parse_world_line_change("0.337192")
        assert result == 0.337192
        assert isinstance(result, float)

    def test_experiment_base_validator_passes_through_none(self):
        """None is a sentinel for 'no change' — the validator must
        return it unchanged."""
        assert self.ExperimentBase.parse_world_line_change(None) is None

    def test_experiment_base_validator_passes_through_numeric(self):
        """A numeric value passes through unchanged."""
        assert self.ExperimentBase.parse_world_line_change(0.337192) == 0.337192

    def test_experiment_update_validator_converts_string_to_float(self):
        """`ExperimentUpdate.parse_world_line_change("0.337192")`
        returns the parsed float."""
        result = self.ExperimentUpdate.parse_world_line_change("0.337192")
        assert result == 0.337192

    def test_experiment_update_validator_passes_through_none(self):
        assert self.ExperimentUpdate.parse_world_line_change(None) is None

    def test_experiment_update_validator_passes_through_numeric(self):
        """A numeric value passes through unchanged (the `return v`
        branch on line 97)."""
        assert self.ExperimentUpdate.parse_world_line_change(0.571024) == 0.571024


class TestServiceConstruction:
    """Coverage for the at-import service construction in
    api/future_gadget_api.py — the `if mongodb_uri:` branch (line 28)
    and the `raise RuntimeError` else-branch (line 38). These run once
    at import time, so we exercise them by re-binding `fgl_service` in
    the module's namespace under different env-var / patch
    combinations.

    Re-importing the module would create a fresh module object and a
    fresh class object for `FutureGadgetLabDataService`, leaving
    subsequent tests in other files with stale references to the old
    class — so we avoid re-import and just re-bind the module-level
    names instead."""

    def test_mongodb_uri_branch_constructs_real_service(self, monkeypatch):
        """When MONGODB_URI is set, fgl_service is built as a real
        FutureGadgetLabDataService against the configured URI — NOT the
        mongomock fallback. Pins the `if mongodb_uri:` branch (line 28).

        The at-import branch lives in module-top code that runs once.
        We re-import the module under our patched env so the
        branch fires in this test. To keep subsequent tests working,
        we drop the freshly-imported module from sys.modules BEFORE
        the test ends so the next consumer picks up the original
        module (which had the mock service, not a MagicMock).
        """
        monkeypatch.setenv("MONGODB_URI", "mongodb://example.invalid:27017")
        monkeypatch.setenv("MOCK", "false")
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        monkeypatch.setattr("common.config.mock_enabled", False)

        # Drop the cached api module so the next `import` actually
        # re-runs the module body under our env.
        sys.modules.pop("api.future_gadget_api", None)

        svc_cls = MagicMock()
        with patch(
            "db.future_gadget_lab_data_service.FutureGadgetLabDataService",
            svc_cls,
        ):
            import api.future_gadget_api  # noqa: F401

        # The real constructor was called with our URI.
        args, kwargs = svc_cls.call_args
        assert kwargs["mongodb_uri"] == "mongodb://example.invalid:27017"
        assert kwargs["mongodb_db"] == "future_gadget_lab"

        # Drop the freshly-imported module so the next test gets the
        # ORIGINAL module (with the real MockFutureGadgetLabDataService
        # instance) rather than this MagicMock-laden one.
        sys.modules.pop("api.future_gadget_api", None)

    def test_non_mock_non_uri_raises_runtime_error(self, monkeypatch):
        """When neither MONGODB_URI nor MOCK is set, the at-import
        branch raises RuntimeError("MONGODB_URI environment variable
        is required ..."). Pins the `else: raise RuntimeError(...)`
        branch (line 38).

        Re-importing api.future_gadget_api triggers the at-import
        branch directly. We pop the cached module so the import
        actually re-runs under our patched env, then drop the fresh
        module again so subsequent tests see the original one.
        """
        monkeypatch.delenv("MONGODB_URI", raising=False)
        monkeypatch.setenv("MOCK", "false")
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        monkeypatch.setattr("common.config.mock_enabled", False)

        sys.modules.pop("api.future_gadget_api", None)
        with pytest.raises(RuntimeError, match="MONGODB_URI"):
            import api.future_gadget_api  # noqa: F401
        # Drop the (partially-imported) module so the next consumer
        # gets the original one back.
        sys.modules.pop("api.future_gadget_api", None)


def _route_has_security_dependency(router, method, path_prefix):
    """A route is protected iff it has at least one security-scoped sub-
    dependency on its resolved dependant tree (the Security(azure_scheme,
    scopes=...) we added). In FastAPI's dependant tree, a Security() call
    appears as a child dependant with non-empty `oauth_scopes`."""
    for route in router.routes:
        if not hasattr(route, "methods"):
            continue
        if method.upper() not in route.methods:
            continue
        if not route.path.startswith(path_prefix):
            continue
        stack = list(route.dependant.dependencies)
        seen = set()
        while stack:
            dep = stack.pop()
            if id(dep) in seen:
                continue
            seen.add(id(dep))
            if getattr(dep, "oauth_scopes", None):
                return True
            stack.extend(dep.dependencies)
    return False


def _route_has_required_roles_decorator(router, method, path):
    """The `@required_roles(...)` decorator wraps the coroutine in a
    `@functools.wraps(func)` wrapper, which sets `__wrapped__` on the result.
    Routes WITHOUT required_roles stay as the bare async function and have no
    `__wrapped__` attribute. (FastAPI itself does not wrap endpoints this
    way, so this is a clean signal.)"""
    for route in router.routes:
        if not hasattr(route, "methods"):
            continue
        if method.upper() not in route.methods:
            continue
        if route.path != path:
            continue
        return hasattr(route.endpoint, "__wrapped__")
    return False


class TestAuthRequirementsOnRoutes:
    """Static checks: every /future-gadget-lab/* REST route has a Security
    dependency wired up by the fix, and the mutation routes additionally have
    the `required_roles` decorator applied."""

    def test_all_read_routes_have_security_dependency(self):
        for method, path_prefix in [
            ("GET", "/lab-experiments"),
            ("GET", "/experiments"),
            ("GET", "/divergence-readings"),
            ("GET", "/divergence-readings/latest"),
            ("GET", "/worldline/status"),
            ("GET", "/worldline-status"),
            ("GET", "/worldline/history"),
            ("GET", "/worldline-history"),
        ]:
            assert _route_has_security_dependency(
                future_gadget_api_router, method, path_prefix
            ), f"{method} {path_prefix}* is missing Security(...)"

    def test_all_get_by_id_routes_have_security_dependency(self):
        for path in ("/lab-experiments/{experiment_id}", "/experiments/{experiment_id}"):
            assert _route_has_security_dependency(
                future_gadget_api_router, "GET", path
            ), f"GET {path} is missing Security(...)"

    def test_all_mutation_routes_have_security_dependency(self):
        for method, path_prefix in [
            ("POST", "/lab-experiments"),
            ("POST", "/experiments"),
            ("POST", "/divergence-readings"),
        ]:
            assert _route_has_security_dependency(
                future_gadget_api_router, method, path_prefix
            ), f"{method} {path_prefix} is missing Security(...)"

    def test_all_put_delete_routes_have_security_dependency(self):
        for method in ("PUT", "DELETE"):
            for path in (
                "/lab-experiments/{experiment_id}",
                "/experiments/{experiment_id}",
            ):
                assert _route_has_security_dependency(
                    future_gadget_api_router, method, path
                ), f"{method} {path} is missing Security(...)"

    def test_all_mutations_require_admin_role(self):
        """Every POST/PUT/DELETE on /future-gadget-lab/* carries
        @required_roles(['Admin'])."""
        for method, path in [
            ("POST", "/lab-experiments"),
            ("POST", "/experiments"),
            ("POST", "/divergence-readings"),
            ("PUT", "/lab-experiments/{experiment_id}"),
            ("PUT", "/experiments/{experiment_id}"),
            ("DELETE", "/lab-experiments/{experiment_id}"),
            ("DELETE", "/experiments/{experiment_id}"),
        ]:
            assert _route_has_required_roles_decorator(
                future_gadget_api_router, method, path
            ), f"{method} {path} is missing @required_roles(['Admin'])"

    def test_get_routes_do_not_require_specific_role(self):
        """Reads are open to any authenticated user — no required_roles check."""
        for method, path in [
            ("GET", "/lab-experiments"),
            ("GET", "/experiments"),
            ("GET", "/divergence-readings"),
            ("GET", "/divergence-readings/latest"),
            ("GET", "/worldline/status"),
            ("GET", "/worldline-status"),
            ("GET", "/worldline/history"),
            ("GET", "/worldline-history"),
        ]:
            assert not _route_has_required_roles_decorator(
                future_gadget_api_router, method, path
            ), f"{method} {path} should NOT have required_roles"


class TestRestEndpointsRejectUnauthenticatedRequests:
    """Integration tests against the live FastAPI app. With the azure_scheme
    dependency overridden to raise 401, every route must return 401 — proving
    the Security dependency is actually resolved by FastAPI on each path."""

    @pytest.fixture
    def unauth_client(self):
        from fastapi import HTTPException, status as http_status

        app = FastAPI()
        app.include_router(future_gadget_api_router)

        async def reject_all():
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        app.dependency_overrides[azure_scheme] = reject_all
        return TestClient(app)

    def test_get_experiments_rejects_no_auth(self, unauth_client):
        assert unauth_client.get("/lab-experiments").status_code == 401
        assert unauth_client.get("/experiments").status_code == 401

    def test_get_experiment_by_id_rejects_no_auth(self, unauth_client):
        assert unauth_client.get("/lab-experiments/EXP-1").status_code == 401
        assert unauth_client.get("/experiments/EXP-1").status_code == 401

    def test_get_divergence_readings_rejects_no_auth(self, unauth_client):
        assert unauth_client.get("/divergence-readings").status_code == 401
        assert unauth_client.get("/divergence-readings/latest").status_code == 401

    def test_get_worldline_rejects_no_auth(self, unauth_client):
        assert unauth_client.get("/worldline/status").status_code == 401
        assert unauth_client.get("/worldline-status").status_code == 401
        assert unauth_client.get("/worldline/history").status_code == 401
        assert unauth_client.get("/worldline-history").status_code == 401

    def test_post_experiments_rejects_no_auth(self, unauth_client):
        payload = {
            "name": "x",
            "description": "x",
            "status": "planned",
            "creator_id": "x",
        }
        assert unauth_client.post("/experiments", json=payload).status_code == 401
        assert unauth_client.post("/lab-experiments", json=payload).status_code == 401

    def test_put_experiments_rejects_no_auth(self, unauth_client):
        assert unauth_client.put("/experiments/EXP-1", json={"name": "y"}).status_code == 401
        assert unauth_client.put("/lab-experiments/EXP-1", json={"name": "y"}).status_code == 401

    def test_delete_experiments_rejects_no_auth(self, unauth_client):
        assert unauth_client.delete("/experiments/EXP-1").status_code == 401
        assert unauth_client.delete("/lab-experiments/EXP-1").status_code == 401

    def test_post_divergence_reading_rejects_no_auth(self, unauth_client):
        payload = {"reading": 1.0, "status": "x", "recorded_by": "x"}
        assert unauth_client.post("/divergence-readings", json=payload).status_code == 401


class TestMutationsRequireAdminRole:
    """When a User-role token is presented, mutations must 403. The Security
    dependency passes (the user IS authenticated), but required_roles(['Admin'])
    must reject."""

    @pytest.fixture
    def user_client(self):
        app = FastAPI()
        app.include_router(future_gadget_api_router)
        user_token = SimpleNamespace(roles=["User"])
        app.dependency_overrides[azure_scheme] = lambda: user_token
        return TestClient(app)

    @pytest.fixture
    def admin_client(self):
        app = FastAPI()
        app.include_router(future_gadget_api_router)
        admin_token = SimpleNamespace(roles=["Admin"])
        app.dependency_overrides[azure_scheme] = lambda: admin_token
        return TestClient(app)

    def _experiment_payload(self):
        return {
            "name": "Test",
            "description": "x",
            "status": "planned",
            "creator_id": "x",
        }

    def test_user_cannot_create_experiment(self, user_client):
        r = user_client.post("/experiments", json=self._experiment_payload())
        assert r.status_code == 403, r.text

    def test_user_cannot_update_experiment(self, user_client):
        r = user_client.put("/experiments/EXP-1", json={"name": "y"})
        assert r.status_code == 403, r.text

    def test_user_cannot_delete_experiment(self, user_client):
        r = user_client.delete("/experiments/EXP-1")
        assert r.status_code == 403, r.text

    def test_user_cannot_create_divergence_reading(self, user_client):
        r = user_client.post(
            "/divergence-readings",
            json={"reading": 1.0, "status": "x", "recorded_by": "x"},
        )
        assert r.status_code == 403, r.text

    def test_user_can_read_experiments(self, user_client):
        """Reads are open to any authenticated user, regardless of role."""
        r = user_client.get("/experiments")
        # 200 (empty list from the mock DB) — not 401/403
        assert r.status_code == 200, r.text

    def test_admin_can_create_experiment(self, admin_client):
        r = admin_client.post("/experiments", json=self._experiment_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Test"

    def test_admin_can_delete_experiment(self, admin_client):
        r = admin_client.delete("/experiments/EXP-1")
        # 200 (deleted) or 404 (not found) — but NOT 401/403
        assert r.status_code in (200, 404), r.text


class TestWebSocketAuthWiring:
    """Pin the WS handlers to auth_connect, not the unauthenticated connect.
    Without this, the role config on the connection manager is dead code and
    anyone can join the broadcast."""

    @pytest.mark.asyncio
    async def test_experiments_websocket_calls_auth_connect(self, monkeypatch):
        """experiments_websocket must call auth_connect (manager has
        receiver_roles=['Admin'], so a non-admin connect gets 1008'd)."""
        from api.future_gadget_api import experiments_websocket
        from fastapi import WebSocketDisconnect

        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        mock_manager = MagicMock()

        async def fake_auth_connect(ws):
            return None

        async def fake_connect(ws):  # the OLD, insecure entry point
            raise AssertionError(
                "connect() must NOT be called — that was the bug"
            )

        mock_manager.auth_connect = fake_auth_connect
        mock_manager.connect = fake_connect
        mock_manager.disconnect = MagicMock()

        monkeypatch.setattr(
            "api.future_gadget_api.experiment_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())

        await experiments_websocket(mock_ws)

        mock_manager.disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_worldline_websocket_calls_auth_connect(self, monkeypatch):
        """Same for the worldline socket — even though its receiver_roles is
        None, the auth frame must still be consumed before the loop starts."""
        from api.future_gadget_api import worldline_websocket
        from fastapi import WebSocketDisconnect

        mock_ws = MagicMock()
        mock_ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        mock_manager = MagicMock()

        async def fake_auth_connect(ws):
            return None

        async def fake_connect(ws):  # the OLD, insecure entry point
            raise AssertionError(
                "connect() must NOT be called — that was the bug"
            )

        mock_manager.auth_connect = fake_auth_connect
        mock_manager.connect = fake_connect
        mock_manager.disconnect = MagicMock()

        monkeypatch.setattr(
            "api.future_gadget_api.worldline_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())

        await worldline_websocket(mock_ws)

        mock_manager.disconnect.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_experiments_websocket_rejects_connection_without_token(self):
        """End-to-end through the real ConnectionManager.auth_connect:
        the experiments manager has receiver_roles=['Admin'], so a connection
        that arrives without a token frame is closed with code 1008 and never
        added to active_connections.

        This is the third acceptance criterion from the issue."""
        from common.socket import ConnectionManager

        manager = ConnectionManager(
            receiver_roles=["Admin"], sender_roles=["Admin"]
        )

        mock_ws = MagicMock()
        closed = {}

        async def fake_accept():
            return None

        async def fake_receive_json():
            # No token frame — matches the unauthenticated curl scenario.
            return {}

        async def fake_close(code, reason):
            closed["code"] = code
            closed["reason"] = reason

        mock_ws.accept = fake_accept
        mock_ws.receive_json = fake_receive_json
        mock_ws.close = fake_close

        await manager.auth_connect(mock_ws)

        assert closed.get("code") == 1008
        assert "Missing authentication token" in closed.get("reason", "")
        assert mock_ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_experiments_websocket_does_not_raise_on_rejected_connect(self, monkeypatch):
        """Regression: when auth_connect rejects a connection (closes the
        socket with 1008 and never appends to active_connections), the
        next `await websocket.receive_json()` in the handler's while loop
        raises `RuntimeError("WebSocket is not connected. Need to call
        'accept' first.")` — that is NOT a `WebSocketDisconnect`, so it
        slips past the inner `except WebSocketDisconnect:` block.

        Before the fix, this RuntimeError propagated up and (with the
        suggested `finally:` cleanup) a subsequent `disconnect(websocket)`
        on a connection that was never added raised
        `ValueError: list.remove(x): x not in list` — flooding the server
        log with tracebacks on every probe / failed connect.

        The fix mirrors `backend/api/api.py:43-66` (`/chat`): wrap the
        body in an outer `try / except Exception` that only calls
        `disconnect` when the websocket is actually in `active_connections`.

        This test runs `experiments_websocket` against the REAL
        `ConnectionManager` with a no-token auth frame and asserts the
        handler does not raise — and that the close frame still carries
        code 1008 (AC #3)."""
        from api.future_gadget_api import experiments_websocket
        from common.socket import ConnectionManager

        manager = ConnectionManager(
            receiver_roles=["Admin"], sender_roles=["Admin"]
        )

        mock_ws = MagicMock()
        closed = {}

        async def fake_accept():
            return None

        # First call returns {} (auth frame); every subsequent call raises
        # RuntimeError (mimics the disconnected-socket state in Starlette
        # after `await websocket.close(code=1008, ...)`).
        mock_ws.receive_json = AsyncMock(
            side_effect=[
                {},
                RuntimeError(
                    "WebSocket is not connected. Need to call 'accept' first."
                ),
            ]
        )

        async def fake_close(code, reason=""):
            closed["code"] = code
            closed["reason"] = reason

        mock_ws.accept = fake_accept
        mock_ws.close = fake_close

        monkeypatch.setattr(
            "api.future_gadget_api.experiment_connection_manager", manager
        )
        mock_logger = MagicMock()
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        # Must NOT raise. With the buggy version this raised RuntimeError;
        # with the suggested `finally`-based fix, the second call would
        # also raise ValueError from disconnect().
        await experiments_websocket(mock_ws)

        # auth_connect still closes with 1008 (AC #3).
        assert closed.get("code") == 1008
        assert "Missing authentication token" in closed.get("reason", "")
        # The rejected connection was never added to active_connections.
        assert mock_ws not in manager.active_connections
        # The outer guard caught the RuntimeError and logged it.
        assert mock_logger.error.called, "RuntimeError must be logged"

    @pytest.mark.asyncio
    async def test_worldline_websocket_does_not_raise_on_rejected_connect(self, monkeypatch):
        """Same regression as the experiments handler: the worldline
        manager has `receiver_roles=None`, but a no-token auth frame is
        still rejected by auth_connect (because `if not auth_data.get("token")`
        fires before the role check). The handler must not raise."""
        from api.future_gadget_api import worldline_websocket
        from common.socket import ConnectionManager

        manager = ConnectionManager(
            receiver_roles=None, sender_roles=["Admin"]
        )

        mock_ws = MagicMock()
        closed = {}

        async def fake_accept():
            return None

        mock_ws.receive_json = AsyncMock(
            side_effect=[
                {},
                RuntimeError(
                    "WebSocket is not connected. Need to call 'accept' first."
                ),
            ]
        )

        async def fake_close(code, reason=""):
            closed["code"] = code
            closed["reason"] = reason

        mock_ws.accept = fake_accept
        mock_ws.close = fake_close

        monkeypatch.setattr(
            "api.future_gadget_api.worldline_connection_manager", manager
        )
        mock_logger = MagicMock()
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        await worldline_websocket(mock_ws)

        assert closed.get("code") == 1008
        assert "Missing authentication token" in closed.get("reason", "")
        assert mock_ws not in manager.active_connections
        assert mock_logger.error.called, "RuntimeError must be logged"

class TestWebSocketReceiveLoop:
    """Coverage for the happy-path message-loop body of the two WS
    endpoints. Each test pins `await websocket.send_json(...)` (the
    line-246 / line-261 branches) and the
    `if websocket in active_connections: disconnect(...)` cleanup
    inside the outer `except Exception:` (lines 252 / 267)."""

    @pytest.mark.asyncio
    async def test_experiments_websocket_receives_and_replies(self, monkeypatch):
        """When auth_connect succeeds, the experiments handler enters
        its message loop. The first message is echoed back via
        send_json (line 246), and a subsequent disconnect triggers the
        inner `disconnect(websocket)` branch."""
        from api.future_gadget_api import experiments_websocket
        from fastapi import WebSocketDisconnect

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            return None  # accept

        async def fake_send_json(data):
            sent_jsons.append(data)

        async def fake_receive_json():
            if not sent_jsons:
                return {"ping": "hello"}
            raise WebSocketDisconnect()

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect
        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)

        mock_manager.disconnect = fake_disconnect

        monkeypatch.setattr(
            "api.future_gadget_api.experiment_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())

        await experiments_websocket(mock_ws)

        # The handler echoed the first message back.
        assert sent_jsons == [{"status": "received", "data": {"ping": "hello"}}]
        # And the disconnect branch ran.
        assert disconnect_calls == [mock_ws]

    @pytest.mark.asyncio
    async def test_experiments_websocket_inner_exception_is_caught(self, monkeypatch):
        """When a non-disconnect exception escapes the inner try/except
        (the message-loop body), the OUTER except in the handler must
        catch it (line 249-250) and run the defensive
        `if websocket in active_connections: disconnect(websocket)`
        cleanup (line 251-252) rather than letting ValueError leak.
        """
        from api.future_gadget_api import experiments_websocket

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            return None  # accept (so active_connections stays empty
                         # in this scenario)

        async def fake_send_json(data):
            # First call (line 246) succeeds; second call blows up,
            # mimicking an aborted client connection mid-broadcast.
            sent_jsons.append(data)
            if len(sent_jsons) > 1:
                raise RuntimeError("simulated downstream failure")

        async def fake_receive_json():
            # Return TWO messages so the second send_json explodes.
            if not sent_jsons:
                return {"first": 1}
            return {"second": 2}

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect

        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)

        mock_manager.disconnect = fake_disconnect
        mock_manager.active_connections = []  # never added -> skip cleanup

        mock_logger = MagicMock()
        monkeypatch.setattr(
            "api.future_gadget_api.experiment_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        # Must NOT raise. The outer except must catch the RuntimeError.
        await experiments_websocket(mock_ws)

        # The outer except logged the error.
        assert mock_logger.error.called
        # The defensive `if websocket in active_connections` branch
        # evaluated to False (empty list), so disconnect was NOT called.
        assert disconnect_calls == []

    @pytest.mark.asyncio
    async def test_worldline_websocket_receives_and_replies(self, monkeypatch):
        """Same shape as the experiments test, for the worldline
        handler."""
        from api.future_gadget_api import worldline_websocket
        from fastapi import WebSocketDisconnect

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            return None

        async def fake_send_json(data):
            sent_jsons.append(data)

        async def fake_receive_json():
            if not sent_jsons:
                return {"ping": "hello"}
            raise WebSocketDisconnect()

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect
        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)

        mock_manager.disconnect = fake_disconnect

        monkeypatch.setattr(
            "api.future_gadget_api.worldline_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())

        await worldline_websocket(mock_ws)

        assert sent_jsons == [{"status": "received", "data": {"ping": "hello"}}]
        assert disconnect_calls == [mock_ws]

    @pytest.mark.asyncio
    async def test_experiments_websocket_outer_exception_disconnects_active(
        self, monkeypatch
    ):
        """When a non-disconnect exception escapes the inner try/except
        AND the websocket IS in active_connections, the outer-except
        branch must run disconnect(websocket) (line 251-252).

        The defensive `if websocket in active_connections` guard is
        what prevents the regression where a rejected connect (closed
        with 1008 and never appended) was being disconnected on the
        way out — which raised ValueError from list.remove and
        flooded the log with tracebacks.
        """
        from api.future_gadget_api import experiments_websocket

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            # Simulate a successful auth — add to active_connections.
            mock_manager.active_connections.append(ws)
            return None

        async def fake_send_json(data):
            sent_jsons.append(data)
            if len(sent_jsons) > 1:
                raise RuntimeError("simulated downstream failure")

        async def fake_receive_json():
            if not sent_jsons:
                return {"first": 1}
            return {"second": 2}

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect
        mock_manager.active_connections = []  # auth_connect will append

        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)
            # Mirror real behaviour: remove from active_connections.
            if ws in mock_manager.active_connections:
                mock_manager.active_connections.remove(ws)

        mock_manager.disconnect = fake_disconnect

        mock_logger = MagicMock()
        monkeypatch.setattr(
            "api.future_gadget_api.experiment_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        await experiments_websocket(mock_ws)

        # Outer except logged the error.
        assert mock_logger.error.called
        # disconnect(websocket) was called because the WS WAS in
        # active_connections.
        assert disconnect_calls == [mock_ws]
        # And the connection was actually removed from active_connections.
        assert mock_ws not in mock_manager.active_connections

    @pytest.mark.asyncio
    async def test_worldline_websocket_outer_exception_disconnects_active(
        self, monkeypatch
    ):
        """Same shape as the experiments test, for the worldline
        handler. Pins the line-267 branch."""
        from api.future_gadget_api import worldline_websocket

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            mock_manager.active_connections.append(ws)
            return None

        async def fake_send_json(data):
            sent_jsons.append(data)
            if len(sent_jsons) > 1:
                raise RuntimeError("simulated downstream failure")

        async def fake_receive_json():
            if not sent_jsons:
                return {"first": 1}
            return {"second": 2}

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect
        mock_manager.active_connections = []

        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)
            if ws in mock_manager.active_connections:
                mock_manager.active_connections.remove(ws)

        mock_manager.disconnect = fake_disconnect

        mock_logger = MagicMock()
        monkeypatch.setattr(
            "api.future_gadget_api.worldline_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        await worldline_websocket(mock_ws)

        assert mock_logger.error.called
        assert disconnect_calls == [mock_ws]
        assert mock_ws not in mock_manager.active_connections

    @pytest.mark.asyncio
    async def test_worldline_websocket_inner_exception_is_caught(self, monkeypatch):
        """Outer-except coverage for the worldline handler: a
        RuntimeError from inside the message loop must NOT escape
        the handler, and the defensive cleanup must skip disconnect
        when the connection was never registered.
        """
        from api.future_gadget_api import worldline_websocket

        mock_ws = MagicMock()
        sent_jsons = []

        async def fake_auth_connect(ws):
            return None

        async def fake_send_json(data):
            sent_jsons.append(data)
            if len(sent_jsons) > 1:
                raise RuntimeError("simulated downstream failure")

        async def fake_receive_json():
            if not sent_jsons:
                return {"first": 1}
            return {"second": 2}

        mock_ws.auth_connect = fake_auth_connect
        mock_ws.receive_json = fake_receive_json
        mock_ws.send_json = fake_send_json

        mock_manager = MagicMock()
        mock_manager.auth_connect = fake_auth_connect
        mock_manager.active_connections = []  # never added

        disconnect_calls = []

        def fake_disconnect(ws):
            disconnect_calls.append(ws)

        mock_manager.disconnect = fake_disconnect

        mock_logger = MagicMock()
        monkeypatch.setattr(
            "api.future_gadget_api.worldline_connection_manager", mock_manager
        )
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)

        await worldline_websocket(mock_ws)

        assert mock_logger.error.called
        assert disconnect_calls == []
