#TODO check for az login
echo -e "\033[34mInitializing Frontend\033[0m"
cd frontend
npm install
echo -e "\033[34mInitializing Backend\033[0m"
cd ../
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv backend/venv --python 3.12
VIRTUAL_ENV="$PWD/backend/venv" uv pip sync backend/requirements.txt

cd backend
# Activate the virtual environment
source "venv/bin/activate"

# Launch an interactive shell with the virtualenv active
echo -e "\033[34mActivating backend\033[0m .. (type 'exit' to quit)"
bash --rcfile <(echo "source $PWD/venv/bin/activate && cd ../" && cd ../) -i