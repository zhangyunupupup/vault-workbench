"""VAULT Workbench. Python 3.10+, standard library only; loopback only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
import argparse
import json
import mimetypes
import os
import secrets
import threading
import webbrowser

from vault.catalog import Catalog, DEFAULT_ROOT, DOCS, ValidationError
from vault.exporter import ExportManager
from vault.geometry import preview
from vault.recipes import plan
from vault.scene import validate_scene


BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
RUNTIME.mkdir(exist_ok=True)
SETTINGS = RUNTIME / "settings.json"
TOKEN = secrets.token_urlsafe(32)
EXPORTS = ExportManager(BASE / "exports")
CATALOG = None
CATALOG_ERROR = ""
SCAN_LOCK = threading.Lock()


def scan(root):
    global CATALOG, CATALOG_ERROR
    with SCAN_LOCK:
        fresh = Catalog(root)
        temporary = SETTINGS.with_suffix(".tmp")
        temporary.write_text(json.dumps({"root": str(fresh.root)}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, SETTINGS)
        CATALOG = fresh
        CATALOG_ERROR = ""
    return fresh


def current_catalog():
    if CATALOG is None:
        raise ValidationError("请先连接模型库。" + CATALOG_ERROR)
    return CATALOG


class Handler(BaseHTTPRequestHandler):
    server_version = "VAULT/1.0"

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def host_valid(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def headers_common(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Cache-Control", "no-store")

    def json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.headers_common()
        self.end_headers()
        self.wfile.write(body)

    def file(self, path, mime=None, *, download=False):
        path = Path(path)
        if not path.is_file():
            return self.json({"error": "文件不存在或已被移走。"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="VAULT-print-package.zip"')
        self.headers_common()
        self.end_headers()
        with path.open("rb") as inp:
            for block in iter(lambda: inp.read(1024 * 1024), b""):
                self.wfile.write(block)

    def do_GET(self):
        if not self.host_valid():
            return self.json({"error": "只允许本机访问。"}, 403)
        route = unquote(urlparse(self.path).path)
        try:
            if route == "/api/health":
                return self.json({"app": "vault-workbench", "project": str(BASE), "port": self.server.server_port})
            if route == "/api/state":
                return self.json({"token": TOKEN, "catalog": CATALOG.public() if CATALOG else None,
                                  "error": CATALOG_ERROR, "history": EXPORTS.history(),
                                  "output": str(EXPORTS.output)})
            if route == "/api/history":
                return self.json(EXPORTS.history())
            if route.startswith("/api/jobs/"):
                job = EXPORTS.get(route.rsplit("/", 1)[-1])
                return self.json(job or {"error": "任务不存在。"}, 200 if job else 404)
            if route.startswith("/api/download/"):
                return self.file(EXPORTS.download_path(route.rsplit("/", 1)[-1]), "application/zip", download=True)
            if route.startswith("/api/docs/"):
                doc_id = route.rsplit("/", 1)[-1]
                if doc_id not in ("1", "2", "3", "4", "5"):
                    raise ValidationError("说明书编号无效。")
                return self.file(current_catalog().root / DOCS[int(doc_id) - 1][0], "application/pdf")
            if route.startswith("/api/mesh/"):
                source = current_catalog().resolve(route.rsplit("/", 1)[-1])
                stat = source.stat()
                return self.json(preview(str(source), stat.st_size, stat.st_mtime_ns))
            if route == "/":
                return self.file(BASE / "web" / "index.html", "text/html; charset=utf-8")
            if route.startswith("/assets/"):
                path = (BASE / "web" / route.lstrip("/")).resolve()
                if not path.is_relative_to(BASE / "web" / "assets"):
                    raise ValidationError("无效的资源路径。")
                return self.file(path)
            if route in ("/app.js", "/styles.css", "/viewer.js", "/builder.js", "/builder-stage.js", "/builder.css"):
                return self.file(BASE / "web" / route[1:])
            return self.json({"error": "页面不存在。"}, 404)
        except ValidationError as exc:
            self.json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:
            self.log_message("GET error: %r", exc)
            self.json({"error": "读取失败，请检查文件权限或重新扫描模型库。"}, 500)

    def do_POST(self):
        origin = self.headers.get("Origin")
        origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if not self.host_valid() or (origin is not None and origin not in origins) or not secrets.compare_digest(self.headers.get("X-Vault-Token", ""), TOKEN):
            return self.json({"error": "本机会话失效，请刷新工作台。"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                raise ValidationError("请求大小无效。")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValidationError("请求格式无效。")
            route = urlparse(self.path).path
            if route == "/api/scan":
                root = payload.get("root")
                if not isinstance(root, str) or not root.strip():
                    raise ValidationError("请输入模型库路径。")
                return self.json({"catalog": scan(root.strip()).public()})
            if route == "/api/preview":
                return self.json(plan(current_catalog(), payload))
            if route == '/api/scene':
                return self.json(validate_scene(current_catalog(), payload))
            if route == "/api/export":
                return self.json(EXPORTS.start(current_catalog(), payload), 202)
            if route == "/api/open-output":
                folder = EXPORTS.output
                if payload.get("id"):
                    folder = EXPORTS.download_path(payload["id"]).parent
                if os.name == "nt":
                    os.startfile(str(folder))
                return self.json({"path": str(folder)})
            return self.json({"error": "接口不存在。"}, 404)
        except (ValidationError, ValueError, TypeError) as exc:
            self.json({"error": str(exc)}, 400)
        except Exception as exc:
            self.log_message("POST error: %r", exc)
            self.json({"error": "操作失败，请检查文件权限和剩余磁盘空间。"}, 500)


def main():
    global CATALOG_ERROR
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    try:
        saved = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.is_file() else {}
        scan(args.root or saved.get("root", DEFAULT_ROOT))
    except (OSError, ValueError) as exc:
        CATALOG_ERROR = str(exc)
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("无法启动本地端口，请关闭重复的工作台后重试。")
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    (RUNTIME / "server.json").write_text(json.dumps({"pid": os.getpid(), "url": url}, ensure_ascii=False), encoding="utf-8")
    print(f"VAULT 中文打印工作台  {url}", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
