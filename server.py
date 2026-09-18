"""
server.py - Lightweight backend server for our Custom Agent Framework.

Provides:
  - Serves the minimalist black-themed Web UI
  - REST endpoints to run agent tasks, inspect steps, view saved files, and manage API key
"""

import base64
import json
import os
import subprocess
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

from agent_brain import CustomAgentBrain
from tools import (
    get_live_weather,
    calculate_currency_or_math,
    save_report_file,
    unreliable_live_rates,
    generate_fusion360_cad,
    generate_ltspice_circuit,
    search_web_for_circuit_or_model,
    TOOL_REGISTRY,
    _validate_safe_filename,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AgentRequestHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            index_path = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
            return

        if path == "/api/status":
            key = os.environ.get("GEMINI_API_KEY", "")
            preview = (key[:6] + "..." + key[-4:]) if len(key) > 10 else ("Configured" if key else "")
            data = {
                "has_key": bool(key),
                "key_preview": preview,
                "tools": [
                    {
                        "name": "get_live_weather",
                        "desc": "Real-time weather query (wttr.in)",
                    },
                    {
                        "name": "calculate_currency_or_math",
                        "desc": "Safe precision mathematical and conversion calculator",
                    },
                    {
                        "name": "save_report_file",
                        "desc": "Writes reports directly to local hard drive",
                    },
                    {
                        "name": "unreliable_live_rates",
                        "desc": "The Troublemaker (Simulates 503 outage to test recovery)",
                    },
                    {
                        "name": "generate_fusion360_cad",
                        "desc": "Autodesk Fusion 360 3D parametric CAD script generator",
                    },
                    {
                        "name": "generate_ltspice_circuit",
                        "desc": "LTspice schematic & simulation netlist generator",
                    },
                    {
                        "name": "search_web_for_circuit_or_model",
                        "desc": "Live web research for component datasheets, pinouts & CAD specs",
                    },
                ],
            }
            self.send_json(data)
            return

        if path == "/api/files":
            # List user files created in output/ folder
            files = []
            if os.path.exists(OUTPUT_DIR):
                for fname in os.listdir(OUTPUT_DIR):
                    if fname.startswith("."):
                        continue
                    if fname.endswith((".txt", ".md", ".csv", ".json", ".log", ".cir", ".net", ".asc", "_fusion.py", ".py", ".step", ".stp", ".stl", ".dxf")):
                        fpath = os.path.join(OUTPUT_DIR, fname)
                        if os.path.isfile(fpath):
                            stat = os.stat(fpath)
                            files.append({
                                "name": fname,
                                "size": stat.st_size,
                                "modified": int(stat.st_mtime),
                            })
            files.sort(key=lambda x: x["modified"], reverse=True)
            self.send_json({"files": files, "folder": "output"})
            return

        if path == "/api/file":
            qs = urllib.parse.parse_qs(parsed.query)
            filename = qs.get("name", [""])[0]
            try:
                safe_name = _validate_safe_filename(
                    filename,
                    allowed_extensions={".txt", ".md", ".csv", ".json", ".log", ".cir", ".net", ".asc", ".py", ".step", ".stp", ".stl", ".dxf"}
                )
            except Exception as val_err:
                self.send_json({"error": f"Invalid filename: {val_err}"}, status=400)
                return

            file_path = os.path.join(OUTPUT_DIR, safe_name)
            if not (os.path.exists(file_path) and os.path.isfile(file_path)):
                file_path = os.path.join(BASE_DIR, safe_name)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.send_json({"name": safe_name, "content": content})
                except Exception as e:
                    self.send_json({"error": str(e)}, status=500)
            else:
                self.send_json({"error": "File not found"}, status=404)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(post_body.decode("utf-8"))
        except Exception:
            self.send_json({"error": "Invalid JSON"}, status=400)
            return

        if path == "/api/open_folder":
            try:
                os.startfile(OUTPUT_DIR)
                self.send_json({"success": True, "message": f"Opened output folder: {OUTPUT_DIR}"})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        if path == "/api/open":
            filename = payload.get("filename", "").strip()
            try:
                safe_name = _validate_safe_filename(
                    filename,
                    allowed_extensions={".txt", ".md", ".csv", ".json", ".log", ".cir", ".net", ".asc", ".py", ".step", ".stp", ".stl", ".dxf"}
                )
            except Exception as val_err:
                self.send_json({"error": f"Invalid filename: {val_err}"}, status=400)
                return

            file_path = os.path.join(OUTPUT_DIR, safe_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(BASE_DIR, safe_name)
            if not os.path.exists(file_path):
                self.send_json({"error": f"File '{safe_name}' not found"}, status=404)
                return

            ltspice_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\LTspice.exe"),
                r"C:\Program Files\ADI\LTspice\LTspice.exe",
                r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe"
            ]
            ltspice_exe = next((p for p in ltspice_paths if os.path.exists(p)), None)
            try:
                if safe_name.endswith((".asc", ".cir", ".net")) and ltspice_exe:
                    subprocess.Popen([ltspice_exe, file_path])
                else:
                    os.startfile(file_path)
                self.send_json({"success": True, "message": f"Opened {safe_name}"})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        if path == "/api/key":
            key = payload.get("api_key", "").strip()
            if not key:
                self.send_json({"error": "No API key provided"}, status=400)
                return
            os.environ["GEMINI_API_KEY"] = key
            with open(os.path.join(BASE_DIR, ".env"), "w") as f:
                f.write(f"GEMINI_API_KEY={key}\n")
            preview = (key[:6] + "..." + key[-4:]) if len(key) > 10 else "Configured"
            self.send_json({"success": True, "key_preview": preview})
            return

        if path == "/api/run":
            prompt = payload.get("prompt", "").strip()
            image_base64 = payload.get("image_base64")
            image_mime = payload.get("image_mime", "image/jpeg")

            if not prompt and not image_base64:
                self.send_json({"error": "Please provide a prompt or attach an image."}, status=400)
                return

            image_bytes = None
            if image_base64:
                try:
                    if "," in image_base64:
                        header, data_part = image_base64.split(",", 1)
                        if "image/" in header:
                            image_mime = header.split(";")[0].replace("data:", "")
                        image_base64 = data_part
                    image_bytes = base64.b64decode(image_base64)
                except Exception as b64_err:
                    self.send_json({"error": f"Invalid image encoding: {str(b64_err)}"}, status=400)
                    return

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                self.send_json({
                    "error": "GEMINI_API_KEY is not configured. Please save your API key first."
                }, status=401)
                return

            collected_steps = []

            def on_step(event_type: str, data: dict):
                collected_steps.append({
                    "type": event_type,
                    "data": data,
                })

            try:
                agent = CustomAgentBrain(api_key=api_key)
                agent.register_tools([
                    get_live_weather,
                    calculate_currency_or_math,
                    save_report_file,
                    unreliable_live_rates,
                    generate_fusion360_cad,
                    generate_ltspice_circuit,
                    search_web_for_circuit_or_model,
                ])
                effective_prompt = prompt or "Analyze this image and model or simulate it using the appropriate engineering tools."
                final_answer = agent.run(
                    effective_prompt,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                    step_callback=on_step
                )
                self.send_json({
                    "success": True,
                    "steps": collected_steps,
                    "final_answer": final_answer,
                })
            except Exception as e:
                self.send_json({
                    "success": False,
                    "error": str(e),
                    "steps": collected_steps,
                }, status=500)
            return

        self.send_error(404, "Endpoint not found")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


def run_server(port=8000):
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("", port)
    httpd = ThreadedHTTPServer(server_address, AgentRequestHandler)
    print(f"\n=============================================================")
    print(f"🚀 Custom Agent Web UI running at: http://localhost:{port}")
    print(f"=============================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
