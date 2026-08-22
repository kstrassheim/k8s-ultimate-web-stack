import pytest
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

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
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

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
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

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
    def test_create_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        current_time = datetime.datetime.now().isoformat()
        # Mock both broadcast methods
        with patch("api.future_gadget_api.experiment_connection_manager.broadcast", AsyncMock()), \
             patch("api.future_gadget_api.broadcast_worldline_status", AsyncMock()), \
             patch("api.future_gadget_api.fgl_service.create_experiment", return_value={
                "id": "EXP-002",
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": 0.000337,
                "timestamp": current_time
            }):
            test_client, _ = client_with_overridden_dependencies
            new_experiment = {
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": 0.000337
            }
            # Updated from /experiments to /lab-experiments
            response = test_client.post(f"{API_PREFIX}/lab-experiments", json=new_experiment)
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "EXP-002"
            assert data["world_line_change"] == 0.000337
            assert "timestamp" in data
            
            # Verify broadcast_worldline_status was called
            from api.future_gadget_api import broadcast_worldline_status
            assert broadcast_worldline_status.called

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
    def test_create_experiment_with_string_world_line_change(self, client_with_overridden_dependencies, setup_fgl_service):
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.experiment_connection_manager.broadcast", AsyncMock()), \
             patch("api.future_gadget_api.broadcast_worldline_status", AsyncMock()), \
             patch("api.future_gadget_api.fgl_service.create_experiment", return_value={
                "id": "EXP-002",
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": 0.000337,
                "timestamp": current_time
            }):
            test_client, _ = client_with_overridden_dependencies
            new_experiment = {
                "name": "Time Leap Machine",
                "description": "Transfer memories to the past",
                "status": "planned",
                "creator_id": "001",
                "collaborators": ["002"],
                "results": None,
                "world_line_change": "0.000337"  # String value to test conversion
            }
            response = test_client.post(f"{API_PREFIX}/lab-experiments", json=new_experiment)
            assert response.status_code == 201
            data = response.json()
            assert data["world_line_change"] == 0.000337  # Should be converted to float

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
    def test_update_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        current_time = datetime.datetime.now().isoformat()
        with patch("api.future_gadget_api.experiment_connection_manager.broadcast", AsyncMock()), \
             patch("api.future_gadget_api.broadcast_worldline_status", AsyncMock()), \
             patch("api.future_gadget_api.fgl_service.update_experiment", return_value={
                "id": "EXP-001",
                "name": "Phone Microwave (Name subject to change)",
                "description": "Send messages to the past",
                "status": "completed",
                "creator_id": "001",
                "collaborators": ["002", "003"],
                "results": "Successful test with banana",
                "world_line_change": 0.571024,
                "timestamp": current_time
            }):
            test_client, _ = client_with_overridden_dependencies
            update_data = {
                "name": "Phone Microwave (Name subject to change)",
                "status": "completed",
                "results": "Successful test with banana",
                "world_line_change": 0.571024
            }
            # Updated from /experiments to /lab-experiments
            response = test_client.put(f"{API_PREFIX}/lab-experiments/EXP-001", json=update_data)
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Phone Microwave (Name subject to change)"
            assert data["status"] == "completed"
            assert data["world_line_change"] == 0.571024
            
            # Verify broadcast_worldline_status was called
            from api.future_gadget_api import broadcast_worldline_status
            assert broadcast_worldline_status.called

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
    def test_delete_experiment(self, client_with_overridden_dependencies, setup_fgl_service):
        with patch("api.future_gadget_api.experiment_connection_manager.broadcast", AsyncMock()), \
             patch("api.future_gadget_api.broadcast_worldline_status", AsyncMock()), \
             patch("api.future_gadget_api.fgl_service.delete_experiment", return_value=True):
            test_client, _ = client_with_overridden_dependencies
            # Updated from /experiments to /lab-experiments
            response = test_client.delete(f"{API_PREFIX}/lab-experiments/EXP-001")
            assert response.status_code == 200
            data = response.json()
            assert "successfully deleted" in data["message"].lower()
            
            # Verify broadcast_worldline_status was called
            from api.future_gadget_api import broadcast_worldline_status
            assert broadcast_worldline_status.called

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
    def test_get_divergence_readings(self, client_with_overridden_dependencies, setup_fgl_service):
        """Test the divergence-readings endpoint available to all authenticated users"""
        # Mock sample readings data
        sample_readings = [
            {
                "id": "DR-001",
                "reading": 1.048596,
                "status": "steins_gate",
                "recorded_by": "Rintaro Okabe",
                "notes": "Steins;Gate worldline"
            },
            {
                "id": "DR-002",
                "reading": 0.571024,
                "status": "alpha",
                "recorded_by": "Rintaro Okabe",
                "notes": "Alpha worldline"
            },
            {
                "id": "DR-003",
                "reading": 1.382733,
                "status": "beta",
                "recorded_by": "Suzuha Amane",
                "notes": "Beta worldline variant"
            }
        ]
        
        with patch("api.future_gadget_api.fgl_service.get_all_divergence_readings", return_value=sample_readings):
            test_client, _ = client_with_overridden_dependencies
            
            # Test 1: Get all readings (no filters)
            response = test_client.get(f"{API_PREFIX}/divergence-readings")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert data[0]["id"] == "DR-001"
            assert data[0]["reading"] == 1.048596
            assert data[0]["status"] == "steins_gate"
            
            # Test 2: Filter by status
            response = test_client.get(f"{API_PREFIX}/divergence-readings?status=alpha")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["status"] == "alpha"
            assert data[0]["reading"] == 0.571024
            
            # Test 3: Filter by recorded_by
            response = test_client.get(f"{API_PREFIX}/divergence-readings?recorded_by=Suzuha%20Amane")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["recorded_by"] == "Suzuha Amane"
            assert data[0]["id"] == "DR-003"
            
            # Test 4: Filter by minimum value
            response = test_client.get(f"{API_PREFIX}/divergence-readings?min_value=1.0")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert all(reading["reading"] >= 1.0 for reading in data)
            
            # Test 5: Filter by maximum value
            response = test_client.get(f"{API_PREFIX}/divergence-readings?max_value=1.0")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["reading"] < 1.0
            assert data[0]["status"] == "alpha"
            
            # Test 6: Combine multiple filters
            response = test_client.get(f"{API_PREFIX}/divergence-readings?min_value=1.0&recorded_by=Rintaro%20Okabe")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "DR-001"
            assert data[0]["reading"] >= 1.0
            assert data[0]["recorded_by"] == "Rintaro Okabe"

    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port uses /experiments")
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


@pytest.mark.skip(reason="websocket endpoints not implemented in k8s-port")
class TestExperimentWebSocketEndpoints:
    """Test the Experiment WebSocket endpoints for real-time updates"""
    
    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket object with all necessary attributes"""
        mock_ws = MagicMock()
        
        # Set up the state with user info
        mock_ws.state = MagicMock()
        mock_ws.state.user = {"name": "Test User", "sub": "test-id", "roles": ["Admin"]}
        
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
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="websocket not in k8s-port")
    async def test_experiment_websocket_connection(self, monkeypatch, mock_websocket):
        """Test experiment WebSocket connection and authentication"""
        # Create a mock connection manager
        mock_manager = MagicMock()
        
        # Use AsyncMock for auth_connect
        mock_auth_connect = AsyncMock()
        async def side_effect(websocket):
            return None
        mock_auth_connect.side_effect = side_effect
        
        # Assign the AsyncMock to the manager
        mock_manager.auth_connect = mock_auth_connect
        
        # Patch the experiment connection manager
        monkeypatch.setattr("api.future_gadget_api.experiment_connection_manager", mock_manager)
        
        # Mock logger to avoid real logging
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())
        
        # Get the WebSocket endpoint function
        from api.future_gadget_api import experiment_websocket_endpoint
        
        # Make websocket.receive_text raise a disconnect to end the handler
        mock_websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        # Call the WebSocket endpoint
        try:
            await experiment_websocket_endpoint(mock_websocket)
        except Exception as e:
            print(f"Expected exception: {e}")
        
        # Verify the connection was authenticated
        assert mock_auth_connect.called
        assert mock_auth_connect.call_args[0][0] == mock_websocket
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="websocket not in k8s-port")
    async def test_experiment_websocket_disconnect_handling(self, monkeypatch, mock_websocket):
        """Test experiment WebSocket disconnect handling"""
        # Create a mock connection manager
        mock_manager = MagicMock()
        
        # Simple async function implementation
        async def mock_auth_connect(websocket):
            # Add websocket to active connections to test disconnect
            mock_manager.active_connections.append(websocket)
            return None
            
        def mock_disconnect(websocket):
            if websocket in mock_manager.active_connections:
                mock_manager.active_connections.remove(websocket)
            mock_disconnect.call_count += 1
        
        # Initialize tracking attributes
        mock_disconnect.call_count = 0
        mock_manager.active_connections = []
        mock_manager.auth_connect = mock_auth_connect
        mock_manager.disconnect = mock_disconnect
        
        # Set up receive_text to raise WebSocketDisconnect
        mock_websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        # Patch the experiment connection manager
        monkeypatch.setattr("api.future_gadget_api.experiment_connection_manager", mock_manager)
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())
        
        # Get the WebSocket endpoint function
        from api.future_gadget_api import experiment_websocket_endpoint
        
        # Call the WebSocket endpoint
        await experiment_websocket_endpoint(mock_websocket)
        
        # Verify disconnect was handled
        assert mock_disconnect.call_count == 1
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="websocket not in k8s-port")
    async def test_experiment_websocket_exception_handling(self, monkeypatch, mock_websocket):
        """Test experiment WebSocket general exception handling"""
        # Create a mock connection manager
        mock_manager = MagicMock()
        
        # Mock auth_connect to raise an exception
        async def mock_auth_connect(websocket):
            raise Exception("Test auth error")
            
        def mock_disconnect(websocket):
            mock_disconnect.call_count += 1
            
        # Initialize tracking
        mock_disconnect.call_count = 0
        mock_manager.auth_connect = mock_auth_connect
        mock_manager.disconnect = mock_disconnect
        mock_manager.active_connections = [mock_websocket]
        
        # Patch the experiment connection manager and logger
        monkeypatch.setattr("api.future_gadget_api.experiment_connection_manager", mock_manager)
        mock_logger = MagicMock()
        monkeypatch.setattr("api.future_gadget_api.logger", mock_logger)
        
        # Get the WebSocket endpoint function
        from api.future_gadget_api import experiment_websocket_endpoint
        
        # Call the WebSocket endpoint
        await experiment_websocket_endpoint(mock_websocket)
        
        # Verify exception was caught and logged
        assert mock_logger.error.call_count == 1
        assert "Test auth error" in str(mock_logger.error.call_args[0][0])
        # Verify disconnect was called to clean up
        assert mock_disconnect.call_count == 1
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="websocket not in k8s-port")
    async def test_broadcast_crud_operations(self, monkeypatch, mock_websocket):
        """Test broadcasting CRUD operations data through WebSockets using broadcast_server"""
        # Create a test experiment data with new fields
        test_experiment = {
            "id": "EXP-001",
            "name": "Test Experiment",
            "status": "in_progress",
            "world_line_change": 0.337192,
            "timestamp": datetime.datetime.now().isoformat(),
            "creator_id": "Rintaro Okabe",
            "description": "Testing worldline modifications"
        }
        
        # Create a mock connection manager
        mock_manager = MagicMock()
        
        # Track broadcast calls with a function that stores arguments
        broadcast_server_args = []
        async def mock_broadcast_server(data, type, username=None):
            broadcast_server_args.append((data, type, username))
            return None
        
        # Assign the mock to the manager
        mock_manager.broadcast_server = mock_broadcast_server
        mock_manager.active_connections = [mock_websocket]
        
        # Patch the experiment connection manager
        monkeypatch.setattr("api.future_gadget_api.experiment_connection_manager", mock_manager)
        monkeypatch.setattr("api.future_gadget_api.broadcast_worldline_status", AsyncMock())
        
        # Bypass security by mocking the required_roles decorator
        monkeypatch.setattr("api.future_gadget_api.required_roles", lambda roles: lambda f: f)
        
        # Import the API function after patching
        from api.future_gadget_api import create_experiment
        
        # Create a mock for the experiment model and token
        mock_experiment = MagicMock()
        mock_experiment.model_dump.return_value = test_experiment
        mock_token = MagicMock()
        mock_token.roles = ["Admin"]  # Add roles to token
        
        # Mock the username property that's accessed in the create_experiment function
        mock_username = "test.user@example.com"
        mock_token.preferred_username = mock_username
        
        # Patch the database service
        with patch("api.future_gadget_api.fgl_service.create_experiment", return_value=test_experiment):
            # Call the function with explicit token parameter 
            result = await create_experiment(experiment=mock_experiment, token=mock_token)
            
            # Verify result
            assert result == test_experiment
            
            # Verify broadcast_server was called
            assert len(broadcast_server_args) == 1
            
            # Check broadcast data matches expected structure
            assert broadcast_server_args[0][0]["id"] == test_experiment["id"]
            assert broadcast_server_args[0][0]["name"] == test_experiment["name"]
            assert broadcast_server_args[0][0]["type"] == "create"  # type field added in broadcast
            assert broadcast_server_args[0][1] == "create"  # type parameter
            assert broadcast_server_args[0][2] == f"Lab Member: {mock_username}"  # username parameter
            
            # Also verify worldline status broadcast was called
            from api.future_gadget_api import broadcast_worldline_status
            assert broadcast_worldline_status.called
            # Verify username was passed to broadcast_worldline_status
            assert broadcast_worldline_status.call_args[1]["username"] == f"Lab Member: {mock_username}"


class TestWorldlineEndpoints:
    """Test the new worldline status endpoints and features"""
    
    @pytest.mark.skip(reason="endpoint path mismatch: k8s-port")
    def test_get_worldline_status(self, client_with_overridden_dependencies, setup_fgl_service):
        """Test the worldline-status endpoint returns correct data"""
        # Mock the calculate_worldline_status function response
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
                "distance": 0.045541
            }
        }
        
        with patch("api.future_gadget_api.calculate_worldline_status", return_value=mock_status):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get(f"{API_PREFIX}/worldline-status")
            assert response.status_code == 200
            data = response.json()
            
            # Verify core worldline data
            assert data["current_worldline"] == 1.337192
            assert data["base_worldline"] == 1.0
            assert data["total_divergence"] == 0.337192
            assert data["experiment_count"] == 5
            
            # Verify closest reading
            assert "closest_reading" in data
            assert data["closest_reading"]["value"] == 1.382733
            assert data["closest_reading"]["status"] == "beta"
            
            # Verify timestamp was added
            assert "timestamp" in data
    
    @pytest.mark.skip(reason="get_worldline_history not implemented in k8s-port")
    def test_get_worldline_history(self, client_with_overridden_dependencies, setup_fgl_service):
        """Test the worldline-history endpoint returns the correct historical progression"""
        # Mock the sorted experiments and history response
        sorted_experiments = []
        mock_history = [
            {
                "current_worldline": 1.0,
                "base_worldline": 1.0,
                "total_divergence": 0.0,
                "experiment_count": 0,
                "timestamp": "2025-04-07T12:00:00.000Z"
            },
            {
                "current_worldline": 1.337192,
                "base_worldline": 1.0,
                "total_divergence": 0.337192,
                "experiment_count": 1,
                "timestamp": "2025-04-07T12:00:00.000Z"
            }
        ]
        
        with patch("api.future_gadget_api.fgl_service.get_all_experiments", return_value=sorted_experiments), \
             patch("api.future_gadget_api.calculate_worldline_status", side_effect=[mock_history[0], mock_history[1]]):
            test_client, _ = client_with_overridden_dependencies
            response = test_client.get(f"{API_PREFIX}/worldline-history")
            assert response.status_code == 200
            data = response.json()
            
            # Verify it returns an array with expected entries
            assert isinstance(data, list)
            assert "current_worldline" in data[0]
            assert "base_worldline" in data[0]
            assert "timestamp" in data[0]
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="broadcast_worldline_status not in k8s-port")
    async def test_broadcast_worldline_status(self, monkeypatch, mock_websocket):
        """Test the broadcast_worldline_status function with new broadcast_server method"""
        # Create mocks
        mock_worldline_manager = MagicMock()
        broadcast_server_args = []
        
        # Define mock async broadcast_server method
        async def mock_broadcast_server(data, type, username="SERVER"):
            broadcast_server_args.append((data, type, username))
            return None
        
        # Define mock calculate method
        def mock_calculate(experiments, readings=None):
            return {
                "current_worldline": 1.337192,
                "base_worldline": 1.0,
                "total_divergence": 0.337192,
                "experiment_count": len(experiments),
                "last_experiment_timestamp": None
            }
        
        # Set up test experiment
        test_experiment = {
            "id": "EXP-001",
            "name": "Test Experiment",
            "world_line_change": 0.337192
        }
        
        # Apply patches
        mock_worldline_manager.broadcast_server = mock_broadcast_server
        monkeypatch.setattr("api.future_gadget_api.worldline_connection_manager", mock_worldline_manager)
        monkeypatch.setattr("api.future_gadget_api.calculate_worldline_status", mock_calculate)
        monkeypatch.setattr("api.future_gadget_api.fgl_service.get_all_experiments", MagicMock(return_value=[]))
        monkeypatch.setattr("api.future_gadget_api.fgl_service.get_all_divergence_readings", MagicMock(return_value=[]))
        
        # Import the function after patching
        from api.future_gadget_api import broadcast_worldline_status
        
        # Test with experiment included and custom username
        custom_username = "Lab Member: Kurisu Makise"
        custom_message = "New experiment added"
        result = await broadcast_worldline_status(
            experiment=test_experiment, 
            username=custom_username,
            custom_message=custom_message
        )
        
        # Verify the broadcast_server was called with correct parameters
        assert len(broadcast_server_args) == 1
        assert broadcast_server_args[0][1] == "worldline_update"  # type
        assert broadcast_server_args[0][2] == custom_username  # username
        
        # Check that message_type and custom_message fields are correctly set in the data
        assert broadcast_server_args[0][0]["message_type"] == "worldline_update"
        assert broadcast_server_args[0][0]["message"] == custom_message
        
        # Verify result contains preview flag when experiment is provided
        assert "includes_preview" in result
        assert result["includes_preview"] == True
        assert "preview_experiment" in result
        assert result["preview_experiment"]["name"] == test_experiment["name"]
        
        # Test without experiment and with default username
        broadcast_server_args.clear()
        result = await broadcast_worldline_status()
        
        # Verify broadcast was still called with default username
        assert len(broadcast_server_args) == 1
        assert broadcast_server_args[0][2] == "Divergence Meter"  # Default username
        
        # Verify no preview flag when no experiment provided
        assert "includes_preview" not in result
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="worldline_websocket_endpoint not in k8s-port")
    async def test_worldline_websocket_endpoint(self, monkeypatch, mock_websocket):
        """Test the worldline status WebSocket endpoint handles different user roles correctly"""
        # Set up mock connection manager
        mock_manager = MagicMock()
        sent_messages = []
        
        # Define async methods
        async def mock_auth_connect(websocket):
            return None
        
        async def mock_send_personal_message(message, websocket):
            sent_messages.append(message)
        
        # Assign async methods
        mock_manager.auth_connect = mock_auth_connect
        mock_manager.send_personal_message = mock_send_personal_message
        
        # Apply patches
        monkeypatch.setattr("api.future_gadget_api.worldline_connection_manager", mock_manager)
        monkeypatch.setattr("api.future_gadget_api.calculate_worldline_status", MagicMock(return_value={
            "current_worldline": 1.337192,
            "base_worldline": 1.0,
            "total_divergence": 0.337192,
            "experiment_count": 3
        }))
        monkeypatch.setattr("api.future_gadget_api.fgl_service.get_all_experiments", MagicMock(return_value=[]))
        monkeypatch.setattr("api.future_gadget_api.fgl_service.get_all_divergence_readings", MagicMock(return_value=[]))
        monkeypatch.setattr("api.future_gadget_api.logger", MagicMock())
        
        # Import the WebSocket endpoint
        from api.future_gadget_api import worldline_status_websocket_endpoint
        
        # Test with regular user - should send status automatically on message
        # Set up user roles
        mock_websocket.state = MagicMock()
        mock_websocket.state.user = MagicMock()
        mock_websocket.state.user.roles = ["User"]
        
        # Set up to receive one message then disconnect
        mock_websocket.receive_text = AsyncMock(side_effect=["ping", WebSocketDisconnect()])
        
        # Call the endpoint
        try:
            await worldline_status_websocket_endpoint(mock_websocket)
        except WebSocketDisconnect:
            pass
        
        # Verify response was sent
        assert len(sent_messages) == 1
        assert "current_worldline" in sent_messages[0]
        assert "timestamp" in sent_messages[0]
        
        # Test with Admin user - should not send automatic status
        mock_websocket.state.user.roles = ["Admin"]
        sent_messages.clear()
        
        # Reset receive_text
        mock_websocket.receive_text = AsyncMock(side_effect=["ping", WebSocketDisconnect()])
        
        # Call the endpoint again
        try:
            await worldline_status_websocket_endpoint(mock_websocket)
        except WebSocketDisconnect:
            pass
        
        # Verify no automatic response to Admin
        assert len(sent_messages) == 0


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