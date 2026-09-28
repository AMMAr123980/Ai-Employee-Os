import os
import sys
import uvicorn

# Add the backend folder to sys.path so 'app' is importable
root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    print(f"Starting AI Employee OS Backend from {backend_dir} on port 8001...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
