import subprocess
import sys
import os

root_dir = r"c:\Users\Horizon\Downloads\AI_Employee_OS_Turnkey"
script_path = os.path.join(root_dir, "run_backend.py")

subprocess.Popen(
    [sys.executable, script_path],
    cwd=root_dir,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=0x00000008 | 0x00000200
)

print("Backend daemon started with DEVNULL handles!")
