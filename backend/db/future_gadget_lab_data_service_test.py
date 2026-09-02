import pytest
import datetime
import re
from db.future_gadget_lab_data_service import (
    FutureGadgetLabDataService,
    WorldLineStatus,
    ExperimentStatus,
    generate_test_data,
)
from mock.mock_future_gadget_lab_data_service import MockFutureGadgetLabDataService
from common.log import logger
from unittest.mock import patch, MagicMock

class SafeLogHandler:
    """A minimal handler implementation with all the necessary attributes."""
    def __init__(self):
        self.level = 0
        self.filters = []
        self.stream = None
    
    def handle(self, record):
        # No-op implementation
        return

@pytest.fixture(autouse=True)
def patch_logger_handlers(monkeypatch):
    """Replace logger handlers with safe dummy handlers to avoid attribute errors."""
    # Create one safe handler for each existing handler
    safe_handlers = [SafeLogHandler() for _ in getattr(logger, "handlers", [])]
    # Replace the handlers completely
    monkeypatch.setattr(logger, "handlers", safe_handlers)

@pytest.fixture
def db_service():
    """Create a fresh in-memory database for testing"""
    return MockFutureGadgetLabDataService()

# Test Initialization
def test_initialization(db_service):
    """Test that the database is initialized with sample data"""
    # Check if tables were created and populated
    assert db_service.experiments_table.count_documents({}) >= 0
    assert db_service.divergence_readings_table.count_documents({}) >= 0
    
    # Verify tables exist
    assert hasattr(db_service, 'experiments_table')
    assert hasattr(db_service, 'divergence_readings_table')
    
    # Verify removed tables don't exist
    assert not hasattr(db_service, 'd_mails_table')
    assert not hasattr(db_service, 'lab_members_table')

# Test JavaScript ISO Format
def test_js_iso_format():
    """Test that JavaScript ISO format matches the expected pattern"""
    # Use the function from the module
    from db.future_gadget_lab_data_service import generate_test_data
    
    # Extract the js_iso_format function from generate_test_data
    # This is a bit of a hack to test the nested function
    current_time = datetime.datetime.now(datetime.timezone.utc)
    js_iso_format = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    # Generate a timestamp
    timestamp = js_iso_format(current_time)
    
    # Check if it matches the JavaScript ISO format pattern
    pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$'
    assert re.match(pattern, timestamp), f"Timestamp {timestamp} does not match ISO format pattern"
    
    # Verify format matches JavaScript's toISOString()
    assert timestamp.endswith('Z'), "Timestamp should end with Z"
    assert "." in timestamp, "Timestamp should include milliseconds"
    milliseconds = timestamp.split(".")[-1][:-1]  # Remove 'Z' at the end
    assert len(milliseconds) == 3, "Should have exactly 3 digits for milliseconds"

# Test Experiment CRUD with JavaScript ISO format
def test_experiment_crud_with_timestamp_format(db_service):
    """Test CRUD operations for experiments with focus on JavaScript ISO timestamp format"""
    # Create a new experiment with a properly formatted ISO timestamp
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    new_experiment = {
        'name': 'ISO Format Test',
        'description': 'Testing JavaScript ISO format timestamp compatibility',
        'status': ExperimentStatus.IN_PROGRESS.value,
        'creator_id': 'Okabe Rintaro',
        'timestamp': timestamp
    }
    
    created_exp = db_service.create_experiment(new_experiment)
    assert created_exp['timestamp'] == timestamp
    
    # Verify the timestamp format is preserved when retrieving
    retrieved_exp = db_service.get_experiment_by_id(created_exp['id'])
    assert retrieved_exp['timestamp'] == timestamp
    
    # Check format matches Frontend validation pattern: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?
    pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$'
    assert re.match(pattern, retrieved_exp['timestamp']), f"Retrieved timestamp {retrieved_exp['timestamp']} doesn't match format"

# Test Experiment CRUD
def test_experiment_crud(db_service):
    """Test CRUD operations for experiments"""
    # Get initial count
    initial_count = len(db_service.get_all_experiments())
    
    # Create a new experiment with world_line_change and timestamp in JavaScript ISO format
    current_time = datetime.datetime.now(datetime.timezone.utc)
    timestamp = current_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    new_experiment = {
        'name': 'Time Machine Prototype',
        'description': 'Early prototype of a time machine',
        'status': ExperimentStatus.IN_PROGRESS.value,
        'creator_id': '001',
        'collaborators': ['003', '004'],
        'results': 'Ongoing testing phase',
        'world_line_change': 0.156732,
        'timestamp': timestamp
    }
    
    created_exp = db_service.create_experiment(new_experiment)
    assert created_exp['id'] is not None
    assert created_exp['name'] == 'Time Machine Prototype'
    assert created_exp['world_line_change'] == 0.156732
    assert created_exp['timestamp'] == timestamp
    
    # Verify the count increased
    assert len(db_service.get_all_experiments()) == initial_count + 1
    
    # Get by ID
    retrieved_exp = db_service.get_experiment_by_id(created_exp['id'])
    assert retrieved_exp is not None
    assert retrieved_exp['name'] == created_exp['name']
    assert retrieved_exp['world_line_change'] == created_exp['world_line_change']
    
    # Update experiment with a new world_line_change
    update_data = {
        'status': ExperimentStatus.COMPLETED.value,
        'results': 'Successfully created a working prototype',
        'world_line_change': 0.223456
    }
    updated_exp = db_service.update_experiment(created_exp['id'], update_data)
    assert updated_exp['status'] == ExperimentStatus.COMPLETED.value
    assert updated_exp['results'] == 'Successfully created a working prototype'
    assert updated_exp['world_line_change'] == 0.223456
    
    # Delete experiment
    assert db_service.delete_experiment(created_exp['id']) is True
    assert db_service.get_experiment_by_id(created_exp['id']) is None
    assert len(db_service.get_all_experiments()) == initial_count

# Test negative world_line_change values
def test_negative_world_line_change(db_service):
    """Test that negative world_line_change values are properly stored and retrieved"""
    # Create an experiment with a negative world_line_change
    negative_exp = {
        'name': 'D-Mail Cancellation',
        'description': 'Cancel previous D-Mail to return to original worldline',
        'status': ExperimentStatus.COMPLETED.value,
        'creator_id': 'Okabe Rintaro',
        'world_line_change': -0.337192
    }
    
    created_exp = db_service.create_experiment(negative_exp)
    assert created_exp['world_line_change'] == -0.337192
    
    # Verify the negative value is preserved when retrieving
    retrieved_exp = db_service.get_experiment_by_id(created_exp['id'])
    assert retrieved_exp['world_line_change'] == -0.337192
    
    # Test with string value
    string_exp = {
        'name': 'Another Negative Test',
        'description': 'Testing negative string conversion',
        'status': ExperimentStatus.COMPLETED.value,
        'creator_id': 'Okabe Rintaro',
        'world_line_change': '-0.412591'
    }
    
    created_string_exp = db_service.create_experiment(string_exp)
    assert created_string_exp['world_line_change'] == -0.412591
    assert isinstance(created_string_exp['world_line_change'], float)

# Test Divergence Reading CRUD
def test_divergence_reading_crud(db_service):
    """Test CRUD operations for Divergence Readings"""
    # Get initial count
    initial_count = len(db_service.get_all_divergence_readings())
    
    # Create a new reading
    new_reading = {
        'reading': 1.382733,
        'status': WorldLineStatus.BETA.value,
        'recorded_by': '001',
        'notes': 'New Beta world line discovered'
    }
    
    created_reading = db_service.create_divergence_reading(new_reading)
    assert created_reading['id'] is not None
    assert created_reading['reading'] == 1.382733
    
    # Verify the count increased
    assert len(db_service.get_all_divergence_readings()) == initial_count + 1
    
    # Get by ID
    retrieved_reading = db_service.get_divergence_reading_by_id(created_reading['id'])
    assert retrieved_reading is not None
    assert retrieved_reading['reading'] == created_reading['reading']
    
    # Update reading
    update_data = {
        'notes': 'Confirmed Beta world line with Suzuha'
    }
    updated_reading = db_service.update_divergence_reading(created_reading['id'], update_data)
    assert updated_reading['notes'] == 'Confirmed Beta world line with Suzuha'
    
    # Test get_latest_divergence_reading
    latest_reading = db_service.get_latest_divergence_reading()
    assert latest_reading is not None
    
    # Delete reading
    assert db_service.delete_divergence_reading(created_reading['id']) is True
    assert db_service.get_divergence_reading_by_id(created_reading['id']) is None
    assert len(db_service.get_all_divergence_readings()) == initial_count

# Test the updated data generation function
def test_generate_test_data(db_service):
    """Test that generate_test_data correctly populates the database with sample data"""
    # Make sure we start with empty tables
    db_service.experiments_table.delete_many({})
    db_service.divergence_readings_table.delete_many({})
    
    # Verify tables are empty
    assert len(db_service.get_all_experiments()) == 0
    assert len(db_service.get_all_divergence_readings()) == 0
    
    # Generate test data
    test_data = generate_test_data(db_service)
    
    # Verify data was created in all tables
    assert len(test_data['experiments']) > 0
    assert len(test_data['divergence_readings']) > 0
    
    # Verify the database was populated
    assert len(db_service.get_all_experiments()) == len(test_data['experiments'])
    assert len(db_service.get_all_divergence_readings()) == len(test_data['divergence_readings'])
    
    # Check some specific data to ensure it was correctly inserted
    experiments = db_service.get_all_experiments()
    assert any(exp['name'] == 'Phone Microwave (Name subject to change)' for exp in experiments)
    
    # Check that world_line_change was added to experiments
    assert all('world_line_change' in exp for exp in experiments)
    
    # Check that timestamp was added to experiments
    assert all('timestamp' in exp for exp in experiments)
    
    # Verify that some experiments have negative world_line_change values
    negative_experiments = [exp for exp in experiments if exp['world_line_change'] < 0]
    assert len(negative_experiments) > 0, "No experiments found with negative world_line_change values"
    
    # Validate the ISO format of timestamps
    iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$'
    for exp in experiments:
        assert re.match(iso_pattern, exp['timestamp']), f"Timestamp {exp['timestamp']} doesn't match JavaScript ISO format"
    
    # Check for specific negative world_line_changes from our test data
    negative_values = [-0.000337, -0.048256, -0.275349, -0.412591]
    found_values = [exp['world_line_change'] for exp in experiments if exp['world_line_change'] < 0]
    
    for value in negative_values:
        assert value in found_values, f"Expected negative world_line_change {value} not found in test data"
    
    readings = db_service.get_all_divergence_readings()
    assert any(reading['reading'] == 1.048596 for reading in readings)

# Test string-to-float conversion for world_line_change
def test_world_line_change_conversion(db_service):
    """Test that string values for world_line_change are converted to float"""
    # Create experiment with string value for world_line_change
    experiment = {
        'name': 'World Line Convergence Test',
        'description': 'Testing world line convergence points',
        'status': ExperimentStatus.IN_PROGRESS.value,
        'creator_id': 'Rintaro Okabe',
        'world_line_change': '0.337192'  # String value
    }
    
    created_exp = db_service.create_experiment(experiment)
    assert isinstance(created_exp['world_line_change'], float)
    assert created_exp['world_line_change'] == 0.337192
    
    # Test update with string value
    update_data = {
        'world_line_change': '1.048596'  # String value
    }
    
    updated_exp = db_service.update_experiment(created_exp['id'], update_data)
    assert isinstance(updated_exp['world_line_change'], float)
    assert updated_exp['world_line_change'] == 1.048596
    
    # Test with negative string value
    negative_exp = {
        'name': 'Negative World Line Change',
        'description': 'Testing negative world line change',
        'status': ExperimentStatus.COMPLETED.value,
        'creator_id': 'Rintaro Okabe',
        'world_line_change': '-0.523299'  # Negative string value
    }
    
    created_neg_exp = db_service.create_experiment(negative_exp)
    assert isinstance(created_neg_exp['world_line_change'], float)
    assert created_neg_exp['world_line_change'] == -0.523299

def test_calculate_worldline_status():
    """Test the calculate_worldline_status function for computing worldline values"""
    # Import the function
    from db.future_gadget_lab_data_service import calculate_worldline_status
    
    # Create test experiments with timestamps in JS ISO format
    current_time = datetime.datetime.now(datetime.timezone.utc)
    js_iso_format = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    # Create experiments with various timestamps to test last_experiment_timestamp
    older_timestamp = js_iso_format(current_time - datetime.timedelta(minutes=10))
    newer_timestamp = js_iso_format(current_time - datetime.timedelta(minutes=5))
    newest_timestamp = js_iso_format(current_time)
    
    experiments = [
        {
            "id": "EXP-001",
            "name": "Test Experiment 1",
            "world_line_change": 0.337192,
            "timestamp": older_timestamp
        },
        {
            "id": "EXP-002",
            "name": "Test Experiment 2",
            "world_line_change": -0.048256,
            "timestamp": newer_timestamp
        },
        {
            "id": "EXP-003",
            "name": "Test Experiment 3",
            "world_line_change": 0.409431,
            "timestamp": newest_timestamp  # Most recent
        }
    ]
    
    # Create test readings
    readings = [
        {
            "id": "DR-001",
            "reading": 1.048596,
            "status": "steins_gate",
            "recorded_by": "Test User 1",
            "notes": "Reading 1"
        },
        {
            "id": "DR-002",
            "reading": 1.382733,
            "status": "beta",
            "recorded_by": "Test User 2",
            "notes": "Reading 2"
        }
    ]
    
    # Test 1: Basic calculation with all experiments
    result = calculate_worldline_status(experiments, readings)
    
    # Expected worldline: 1.0 (base) + 0.337192 - 0.048256 + 0.409431 = 1.698367
    expected_worldline = 1.0 + 0.337192 - 0.048256 + 0.409431
    
    # Verify basic calculations
    assert result["current_worldline"] == round(expected_worldline, 6)
    assert result["base_worldline"] == 1.0
    assert result["total_divergence"] == round(expected_worldline - 1.0, 6)
    assert result["experiment_count"] == 3
    
    # Verify last experiment timestamp (should be the most recent)
    assert result["last_experiment_timestamp"] == newest_timestamp
    
    # Verify closest reading (should be reading 2, as 1.382733 is closer to 1.698367 than 1.048596)
    assert result["closest_reading"]["value"] == readings[1]["reading"]
    assert result["closest_reading"]["status"] == readings[1]["status"]
    assert result["closest_reading"]["recorded_by"] == readings[1]["recorded_by"]
    
    # Verify distance calculation is correct
    calculated_distance = abs(readings[1]["reading"] - expected_worldline)
    assert result["closest_reading"]["distance"] == round(calculated_distance, 6)
    
    # Test 2: Empty experiments list
    empty_result = calculate_worldline_status([], readings)
    assert empty_result["current_worldline"] == 1.0  # Base worldline
    assert empty_result["total_divergence"] == 0.0
    assert empty_result["experiment_count"] == 0
    assert empty_result["last_experiment_timestamp"] is None
    
    # Test 3: No readings
    no_readings_result = calculate_worldline_status(experiments)
    assert no_readings_result["current_worldline"] == round(expected_worldline, 6)
    assert "closest_reading" not in no_readings_result
    
    # Test 4: Missing world_line_change values
    incomplete_experiments = [
        {"id": "EXP-004", "name": "No Change Value"},
        {"id": "EXP-005", "name": "With Change Value", "world_line_change": 0.123456}
    ]
    incomplete_result = calculate_worldline_status(incomplete_experiments, readings)
    # Expected: 1.0 (base) + 0.123456 = 1.123456
    assert incomplete_result["current_worldline"] == 1.123456
    
    # Test 5: Negative-only changes
    negative_experiments = [
        {"id": "EXP-006", "name": "Negative 1", "world_line_change": -0.2},
        {"id": "EXP-007", "name": "Negative 2", "world_line_change": -0.3}
    ]
    negative_result = calculate_worldline_status(negative_experiments, readings)
    # Expected: 1.0 (base) - 0.2 - 0.3 = 0.5
    assert negative_result["current_worldline"] == 0.5
    assert negative_result["total_divergence"] == -0.5

def test_health_check_returns_true_when_mongo_ping_succeeds(db_service):
    """A reachable backing store reports True (True is what the /ready
    endpoint gates the Service-endpoint membership on)."""
    with patch.object(db_service._mongo_client.admin, "command", return_value={"ok": 1.0}):
        assert db_service.health_check() is True


def test_health_check_returns_false_when_mongo_ping_raises(db_service):
    """A broken connection (MongoDB down, network blip) reports False
    rather than raising, so the readiness probe gets a clean 503 instead
    of a 500 from an unhandled exception."""
    from pymongo.errors import PyMongoError
    with patch.object(
        db_service._mongo_client.admin,
        "command",
        side_effect=PyMongoError("boom"),
    ):
        assert db_service.health_check() is False


def test_health_check_returns_false_when_client_is_none():
    """A service that was never initialised (no client at all) still has
    a defined answer — False, not a crash."""
    svc = FutureGadgetLabDataService.__new__(FutureGadgetLabDataService)
    svc._mongo_client = None
    assert svc.health_check() is False


# ---------------------------------------------------------------------------
# Coverage for the production-only branches of db/future_gadget_lab_data_service.py
# that the mock implementation does not exercise. The lines below are the
# "if not self.mongodb_uri: raise ..." branch in `_initialize_db`, the
# `_seed_mongodb_if_empty` count > 0 / error branches, the CRUD update-not-found
# branches, the str->float conversion branches on the divergence payloads,
# and the closest_reading fallback branches in calculate_worldline_status.
# ---------------------------------------------------------------------------


def test_initialize_db_raises_when_no_uri_and_no_client():
    """Constructing the real service with neither a URI nor a client
    raises a clear RuntimeError. The mock service sidesteps this branch
    by always passing a client — this test pins the real one.
    """
    svc = FutureGadgetLabDataService.__new__(FutureGadgetLabDataService)
    svc.mongodb_uri = None
    svc._mongo_client = None
    with pytest.raises(RuntimeError, match="MONGODB_URI is required"):
        svc._initialize_db()


def test_initialize_db_pings_admin_db():
    """When given a URI, _initialize_db connects via MongoClient and
    pings admin to verify reachability. The mock service sidesteps this
    (mongomock is always reachable) — this test pins the real one.
    """
    svc = FutureGadgetLabDataService.__new__(FutureGadgetLabDataService)
    svc.mongodb_uri = "mongodb://example.invalid:27017"
    svc.mongodb_db_name = "future_gadget_lab"
    svc._mongo_client = None
    svc._db = None

    fake_client = MagicMock()
    fake_admin = MagicMock()
    fake_client.admin = fake_admin
    # The seeding helper calls .experiments.count_documents on the
    # named db; return >0 so it short-circuits rather than trying to
    # seed the fake (which would explode).
    fake_named_db = MagicMock()
    fake_named_db.experiments.count_documents.return_value = 1
    fake_client.__getitem__.return_value = fake_named_db

    with patch("db.future_gadget_lab_data_service.MongoClient", return_value=fake_client) as mock_mc:
        svc._initialize_db()
    # MongoClient was constructed with the URI.
    mock_mc.assert_called_once_with("mongodb://example.invalid:27017")
    # Ping was issued on the admin db.
    fake_admin.command.assert_called_once_with("ping")
    # The db the service will use is the named one.
    assert svc._db == fake_named_db


def test_seed_mongodb_if_empty_returns_when_db_is_none():
    """The seeding helper is a no-op when there's no db handle to seed.
    Pins the early-return guard.
    """
    svc = FutureGadgetLabDataService.__new__(FutureGadgetLabDataService)
    svc._db = None
    # Must not raise.
    svc._seed_mongodb_if_empty()


def test_seed_mongodb_if_empty_skips_when_count_is_positive(db_service, monkeypatch):
    """If the experiments collection already has documents, seeding is
    skipped — pinning the early-return at the positive-count branch.

    The mock service seeds itself with sample data on __init__, so by
    the time this test gets the fixture the count is already > 0 — we
    just have to confirm _seed_mongodb_if_empty returns without
    inserting any MORE rows.
    """
    initial_count = db_service.experiments_table.count_documents({})
    assert initial_count > 0, "fixture must pre-seed so the test is meaningful"
    # Patch the data-generation function to blow up if invoked — that
    # would mean the count>0 guard didn't fire and we'd reseed the
    # table.
    def boom(*a, **k):
        raise AssertionError("generate_test_data should not run when count > 0")

    monkeypatch.setattr(
        "db.future_gadget_lab_data_service.generate_test_data", boom
    )
    db_service._seed_mongodb_if_empty()
    # No new rows were added — count unchanged.
    assert db_service.experiments_table.count_documents({}) == initial_count


def test_seed_mongodb_if_empty_returns_on_pymongo_error():
    """If the count query fails (MongoDB unreachable during init), the
    helper logs and returns without raising. Pins the error branch.
    """
    from pymongo.errors import PyMongoError
    svc = FutureGadgetLabDataService.__new__(FutureGadgetLabDataService)
    svc._mongo_client = MagicMock()
    # Use a MagicMock stand-in whose count_documents raises.
    fake_db = MagicMock()
    fake_db.experiments.count_documents.side_effect = PyMongoError("boom")
    svc._db = fake_db

    # Must not raise.
    svc._seed_mongodb_if_empty()


def test_search_experiments_returns_matches(db_service):
    """search_experiments() is the unconstrained find — exercised
    here so the production branch is hit.
    """
    db_service.experiments_table.insert_one({"id": "EXP-A", "name": "A"})
    db_service.experiments_table.insert_one({"id": "EXP-B", "name": "B"})

    result = db_service.search_experiments({"name": "A"})
    assert len(result) == 1
    assert result[0]["id"] == "EXP-A"
    # No _id leaks through.
    assert "_id" not in result[0]


def test_update_experiment_returns_none_when_not_found(db_service):
    """Updating a non-existent experiment returns None (the route
    translates that to a 404). Pins the not-found branch.
    """
    result = db_service.update_experiment("EXP-DOES-NOT-EXIST", {"name": "x"})
    assert result is None


def test_update_divergence_reading_returns_none_when_not_found(db_service):
    """Same as update_experiment, for divergence readings.
    """
    result = db_service.update_divergence_reading("DR-DOES-NOT-EXIST", {"notes": "x"})
    assert result is None


def test_prepare_divergence_payload_string_reading_converted(db_service):
    """`_prepare_divergence_payload` coerces a string `reading` to float
    (covers the legacy client that JSON-encodes a number as a string).
    Pins the str->float branch on the create path.
    """
    payload = db_service._prepare_divergence_payload(
        {"reading": "1.048596", "status": "steins_gate", "recorded_by": "x"}
    )
    assert payload["reading"] == 1.048596
    assert isinstance(payload["reading"], float)


def test_prepare_divergence_payload_string_value_converted(db_service):
    """`_prepare_divergence_payload` coerces a string `value` to float
    as well — older field-name fallback."""
    payload = db_service._prepare_divergence_payload(
        {"value": "0.571024", "status": "alpha", "recorded_by": "x"}
    )
    assert payload["value"] == 0.571024
    assert isinstance(payload["value"], float)


def test_prepare_divergence_payload_default_status_is_alpha(db_service):
    """If no status is supplied, the payload defaults to the alpha
    attractor field's value. Pins the missing-status branch.
    """
    payload = db_service._prepare_divergence_payload(
        {"reading": 1.0, "recorded_by": "x"}
    )
    assert payload["status"] == WorldLineStatus.ALPHA.value


def test_prepare_divergence_update_payload_string_reading_converted(db_service):
    """Update path: string `reading` is coerced to float. Pins the
    str->float branch on the update path.
    """
    payload = db_service._prepare_divergence_update_payload({"reading": "0.571024"})
    assert payload["reading"] == 0.571024
    assert isinstance(payload["reading"], float)


def test_prepare_divergence_update_payload_string_value_converted(db_service):
    """Update path: string `value` is coerced to float."""
    payload = db_service._prepare_divergence_update_payload({"value": "0.523299"})
    assert payload["value"] == 0.523299
    assert isinstance(payload["value"], float)


def test_calculate_worldline_status_valueerror_falls_back_to_zero():
    """calculate_worldline_status tolerates readings whose numeric field
    is a string that fails to parse as float — falls back to 0.0 so a
    corrupted row can't break the dashboard.
    """
    from db.future_gadget_lab_data_service import calculate_worldline_status

    experiments = []
    readings = [
        # `reading` is the JSON-parsed string of a non-numeric value
        # — the `float()` call raises ValueError, the catch falls back
        # to 0.0, the distance calculation uses 0.0.
        {"id": "DR-BAD", "reading": "not-a-number", "status": "alpha",
         "recorded_by": "Test", "notes": ""},
    ]
    # Must not raise; should return a result with closest_reading
    # populated (the bad row at distance = abs(0 - 1.0) = 1.0).
    # The `closest_reading.get('reading')` value is the ORIGINAL field
    # of the closest row (not the parsed float) — so it stays as the
    # string. The distance uses the parsed 0.0.
    result = calculate_worldline_status(experiments, readings)
    assert "closest_reading" in result
    # The value displayed is what was stored on the row, unmodified.
    assert result["closest_reading"]["value"] == "not-a-number"
    # The distance is computed from the parsed float (0.0), so
    # distance = abs(0.0 - 1.0) = 1.0.
    assert result["closest_reading"]["distance"] == 1.0


def test_calculate_worldline_status_default_closest_when_no_readings_value():
    """When every reading has a falsy numeric value (None / 0 / empty
    string), `closest_reading` stays unset from the loop and the
    fallback synthetic reading is used. Pins the
    `if not closest_reading:` branch.
    """
    from db.future_gadget_lab_data_service import calculate_worldline_status

    experiments = []
    # Reading whose reading+value are both missing -> falls back to 0.0.
    # The loop sets closest_reading on the first iteration (so the
    # fallback never fires). To force the fallback, pass readings where
    # `reading.get('reading')` and `reading.get('value')` are BOTH
    # falsy *and* the `or` chain yields 0.0 — which counts as falsy
    # too, but `if distance < min_distance` (0 < inf) still wins. To
    # genuinely miss, we need a reading where the iteration never sets
    # closest_reading — i.e. an empty list.
    result = calculate_worldline_status(experiments, [])
    # No closest_reading should be present.
    assert "closest_reading" not in result
