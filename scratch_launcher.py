import subprocess
import sys
import os

root_dir = r"c:\Users\Horizon\Downloads\AI_Employee_OS_Turnkey"
script_path = os.path.join(root_dir, "run_backend.py")
log_path = os.path.join(root_dir, "backend_output.log")

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

log_file = open(log_path, "a")

p = subprocess.Popen(
    [sys.executable, "-u", script_path],
    cwd=root_dir,
    env=env,
    stdout=log_file,
    stderr=log_file,
    creationflags=0x00000008 | 0x00000200,
    close_fds=True
)

print(f"Backend launched independently as PID {p.pid}")
