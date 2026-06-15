import json
import os
from pathlib import Path

mock_enabled = os.environ.get("MOCK", "false").lower() == "true"

# In k8s, terraform config is mounted as a secret/configmap
# In local dev with MOCK, use the mock config
if mock_enabled:
    config_path = Path(__file__).parent.parent / "mock" / "terraform.mock.config.json"
else:
    # Try k8s config mount first, then fallback to terraform.config.json
    config_path = Path(os.environ.get("TERRAFORM_CONFIG", "/run/config/terraform.config.json"))
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / "terraform.config.json"

print(f"Loading configuration from: {config_path}")

tfconfig = None
try:
    with open(config_path, "r") as f:
        tfconfig = json.load(f)
except FileNotFoundError:
    alt_path = Path(__file__).parent.parent / "terraform.config.json"
    with open(alt_path, "r") as f:
        tfconfig = json.load(f)

# CORS origins — dev gets localhost, prod gets empty (allow all from app service domain)
origins = ["http://localhost:5173", "http://localhost:5173/__cypress/", "http://localhost:8000"] if tfconfig["env"]["value"] == "dev" else []