set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo -e "\033[34mInitializing Terraform\033[0m"
pushd terraform >/dev/null
terraform init
terraform apply
terraform output -json > "$ROOT_DIR/.terraform_apply_output.json"
popd >/dev/null

if [[ -f "$ROOT_DIR/.terraform_apply_output.json" ]]; then
  cp "$ROOT_DIR/.terraform_apply_output.json" "$ROOT_DIR/frontend/terraform.config.json"
  cp "$ROOT_DIR/.terraform_apply_output.json" "$ROOT_DIR/backend/terraform.config.json"
else
  echo -e "\033[31mERROR: .terraform_apply_output.json not found\033[0m"
  exit 1
fi

echo -e "\033[34mInitializing Frontend\033[0m"
pushd frontend >/dev/null
npm install
popd >/dev/null

echo -e "\033[34mInitializing Backend\033[0m"
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt

cd backend
if [[ ! -d "venv" || ! -f "venv/bin/activate" ]]; then
  echo "Virtual environment 'venv' not found. Please create one first."
  exit 1
fi

source "venv/bin/activate"
echo -e "\033[34mActivating backend\033[0m .. (type 'exit' to quit)"
bash --rcfile <(echo "source \"$PWD/venv/bin/activate\" && cd \"$ROOT_DIR\"") -i