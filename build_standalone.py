"""Build dist/threadline-standalone.html: the whole app in one file.

The frontend (static/) and the Python rules engine are embedded. Python runs in the browser through Pyodide, so every
action works without a server. Needs internet on first open for Pyodide, Leaflet, map tiles and fonts.
Usage: python build_standalone.py
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
PY_MODULES = ["models", "seed", "domain", "comms", "engine", "assistant", "views", "bridge"]
JS_ORDER = ["util", "table", "map", "viz", "pages", "app"]


def bundle_js() -> str:
    parts = []
    for name in JS_ORDER:
        src = (ROOT / "static" / f"{name}.js").read_text(encoding="utf8")
        src = re.sub(r"^import [^\n]*\n", "", src, flags=re.M)
        src = re.sub(r"^export (async )?(function|const)", r"\1\2", src, flags=re.M)
        if name == "util":
            old = "    else el.setAttribute(k, v)"
            assert src.count(old) == 1
            src = src.replace(old, "    else el.setAttribute(k, k === 'src' && window.__IMG && String(v).startsWith('/assets/products/') ? (window.__IMG[String(v).split('/').pop()] || v) : v)")
        parts.append(f"// ---- {name}.js ----\n{src}")
    return "\n".join(parts)


def images() -> dict:
    out = {}
    for f in sorted((ROOT / "assets" / "products").glob("*.webp")):
        out[f.name] = "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()
    return out


def safe(text: str) -> str:
    return text.replace("</", "<\\/")


def main() -> Path:
    css = (ROOT / "static" / "app.css").read_text(encoding="utf8")
    py = {f"{m}.py": (ROOT / f"{m}.py").read_text(encoding="utf8") for m in PY_MODULES}
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Threadline Operations</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="">
<style>
{safe(css)}
.splash{{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#6B6A64;font-size:14px}}
.splash b{{font-size:28px;color:#24262A;letter-spacing:-.015em}}
</style>
</head>
<body>
<div id="root"><div class="splash"><b>threadline</b><span id="splash-msg">Starting the Python engine in your browser (about 10 MB, first load only)…</span></div></div>
<div id="toasts" aria-live="polite"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script src="{PYODIDE}pyodide.js"></script>
<script>
window.__IMG = {safe(json.dumps(images()))};
window.__PY = {safe(json.dumps(py))};
(function () {{
  const realFetch = window.fetch.bind(window);
  window.__ready = (async () => {{
    const py = await loadPyodide({{ indexURL: "{PYODIDE}" }});
    py.FS.mkdirTree("/app");
    for (const [name, src] of Object.entries(window.__PY)) py.FS.writeFile("/app/" + name, src);
    py.runPython("import sys; sys.path.insert(0, '/app')\\nimport bridge");
    window.__handle = py.runPython("bridge.handle");
  }})();
  window.fetch = async (url, opts = {{}}) => {{
    if (!String(url).startsWith("/api/")) return realFetch(url, opts);
    await window.__ready;
    const r = JSON.parse(window.__handle(opts.method || "GET", String(url), opts.body || ""));
    return new Response(JSON.stringify(r.body), {{ status: r.status, headers: {{ "Content-Type": "application/json" }} }});
  }};
}})();
</script>
<script>
function startApp() {{
{safe(bundle_js())}
}}
window.__ready.then(startApp).catch((e) => {{ document.getElementById('splash-msg').textContent = 'Could not start: ' + e.message + '. This file needs internet access on first open.'; }});
</script>
</body>
</html>
"""
    out = ROOT / "dist" / "threadline-standalone.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf8")
    return out


if __name__ == "__main__":
    path = main()
    print(f"{path} ({path.stat().st_size / 1024:.0f} KB)")
