import argparse
import json
import os
from pathlib import Path
import secrets
import webbrowser
import threading

from .hoard_link import family
from .hoard_link.atomic import write_text_atomic, write_json_atomic
from .server import make_server
from .store import Workspace


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Atlas's Hoard: shared local files and native projects")
    parser.add_argument("--port", type=int, default=5203)
    parser.add_argument("--data-dir", type=Path, default=repo / "data")
    parser.add_argument("--root", type=Path, help="shared filesystem root; persisted on first launch")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    config_file = args.data_dir / "storage.json"
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    default = Path("D:/LocalAI/HoardStorage") if os.name == "nt" and Path("D:/LocalAI").is_dir() else Path.home() / "HoardStorage"
    root = args.root or Path(config.get("root") or default)
    store = Workspace(args.data_dir, root)
    write_json_atomic(config_file, {"root": str(store.root)})
    token_file = args.data_dir / "mcp-token"
    token = token_file.read_text(encoding="utf-8").strip() if token_file.exists() else secrets.token_urlsafe(32)
    if not token:
        token = secrets.token_urlsafe(32)
    write_text_atomic(token_file, token)
    family.configure("atlas", str(args.data_dir))
    server = make_server(store, token, args.port)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{server.server_port}/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
