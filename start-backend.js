import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isWindows = process.platform === 'win32';
const backendPath = path.resolve(__dirname, '../backend');

// Use the Python from the activated venv if it exists, otherwise fall back to system python3
// When CI runs "source venv/bin/activate" the VIRTUAL_ENV env var is set
function findPythonExecutable() {
  const venvPython = isWindows
    ? path.join(backendPath, 'venv', 'Scripts', 'python.exe')
    : path.join(backendPath, 'venv', 'bin', 'python');

  // First choice: venv python (if venv was properly created)
  if (fs.existsSync(venvPython)) {
    console.log(`Using venv Python: ${venvPython}`);
    return venvPython;
  }

  // Second choice: python3 from PATH (CI uses setup-python which puts python3 on PATH)
  // execSync which python returns the actual path so we get the right python3
  try {
    const pythonPath = execSync(isWindows ? 'where python' : 'which python3', { encoding: 'utf8' }).trim().split('\n')[0];
    if (pythonPath && fs.existsSync(pythonPath)) {
      console.log(`Using system Python: ${pythonPath}`);
      return pythonPath;
    }
  } catch {
    // which/where failed, try just python3
  }

  // Third choice: plain python3 (system default)
  console.log(`Using system Python: python3`);
  return 'python3';
}

const pythonExe = findPythonExecutable();

// Launch FastAPI with debugpy
const args = [
  '-m', 'uvicorn',
  'main:app',
  '--host', '0.0.0.0',
  '--port', '8000',
  '--reload',
  '--log-level', 'error'  // Add this line to set log level to error
];

// Add debugpy args if needed
const enableDebug = process.env.ENABLE_DEBUG === 'true';
if (enableDebug) {
  //args.unshift('--wait-for-client');
  args.unshift('5678');
  args.unshift('--listen');
  args.unshift('-m', 'debugpy');
}

const backend = spawn(pythonExe, args, {
  cwd: backendPath,
  env: { ...process.env, MOCK: process.env.MOCK || 'true' },
  stdio: 'inherit'
});

process.on('SIGINT', () => {
  backend.kill('SIGINT');
  process.exit(0);
});