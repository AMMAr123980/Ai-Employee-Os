import subprocess
import sys
import os
import time

root_dir = r"c:\Users\Horizon\Downloads\AI_Employee_OS_Turnkey"
script_path = os.path.join(root_dir, "run_backend.py")
log_path = os.path.join(root_dir, "backend_runtime.log")

log_file = open(log_path, "a")

p = subprocess.Popen(
    [sys.executable, script_path],
    cwd=root_dir,
    stdout=log_file,
    stderr=log_file,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008, # DETACHED_PROCESS
)

print(f"Backend process spawned with PID {p.pid}")
