#!/usr/bin/env python3
"""G2 browser acceptance for the packaged Qdrant dashboard.

Runs inside the loopback-only Bubblewrap namespace with the host's reviewed
Chrome and Playwright. The browser only ever receives a short-lived,
collection-scoped prw JWT; it never sees the admin secret.

Usage: browser_acceptance.py <jwt-file> <out.json>
"""
import asyncio
import hashlib
import json
import sys
from importlib.metadata import version as distribution_version
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:6333"
COLLECTION = "browser-fixture"
CHROME_LAUNCHER = Path("/opt/google/chrome/google-chrome")
CHROME_BINARY = Path("/opt/google/chrome/chrome")
EXPECTED_CSP = (
    "default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; img-src 'self' data: blob:; "
    "object-src 'none'; script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:"
)
GRAPH_JS = """
async ({collection, workerUrl}) => {
  const settings = JSON.parse(localStorage.getItem('settings') || '{}');
  const response = await fetch(`/collections/${collection}/points/search/matrix/offsets`, {
    method: 'POST',
    headers: {'content-type': 'application/json', 'api-key': settings.apiKey || ''},
    body: JSON.stringify({sample: 6, limit: 5}),
  });
  if (!response.ok) return {error: `matrix status ${response.status}`};
  const graph = (await response.json()).result;
  return await new Promise((resolve) => {
    const worker = new Worker(workerUrl, {type: 'module'});
    const timer = setTimeout(() => { worker.terminate(); resolve({error: 'timeout'}); }, 30000);
    worker.onerror = (event) => { clearTimeout(timer); worker.terminate(); resolve({error: String(event.message || 'worker error')}); };
    worker.onmessage = (event) => {
      if (event.data.error) { clearTimeout(timer); worker.terminate(); resolve({error: event.data.error}); return; }
      if (event.data.done) {
        clearTimeout(timer); worker.terminate();
        resolve({positions: event.data.result.length / 2, ids: graph.ids.length, done: true});
      }
    };
    worker.postMessage({result: {graph, metric: 'Cosine', points: graph.ids.map((id) => ({id}))}, params: {algorithm: 'UMAP'}});
  });
}
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset(pattern: str) -> str:
    matches = sorted(Path("/usr/share/qdrant/web-ui/assets").glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one packaged asset for {pattern}")
    return f"/dashboard/assets/{matches[0].name}"


async def run(token: str) -> dict:
    requests: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    workers: dict[str, bool] = {}
    cloud: dict = {"requestObserved": False}
    editor_worker = asset("editor.worker-*.js")
    json_worker = asset("json.worker-*.js")
    graph_worker = asset("worker-*.js")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=str(CHROME_BINARY),
            headless=True,
            args=["--no-first-run", "--disable-background-networking", "--disable-sync"],
        )
        browser_version = browser.version
        context = await browser.new_context()
        await context.add_init_script(
            "if (location.origin === %s && !localStorage.getItem('settings')) {"
            " localStorage.setItem('settings', JSON.stringify({apiKey: %s})); }"
            % (json.dumps(BASE_URL), json.dumps(token))
        )

        def on_request(request):
            headers = request.headers
            requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "authorization": "api-key" in headers or "authorization" in headers,
                    "token_exact": headers.get("api-key", token) == token,
                }
            )

        async def on_response(response):
            if urlsplit(response.url).path == "/dashboard/cloud/data.json":
                cloud["requestObserved"] = True
                cloud["status"] = response.status
                try:
                    cloud["value"] = json.loads(await response.text())
                except Exception as error:  # noqa: BLE001
                    cloud["value_error"] = type(error).__name__

        context.on("request", on_request)
        context.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        page = await context.new_page()
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        async def on_worker(worker):
            path = urlsplit(worker.url).path
            try:
                workers[path] = (await worker.evaluate("typeof self.postMessage")) == "function"
            except Exception:  # noqa: BLE001
                workers.setdefault(path, False)

        page.on("worker", lambda w: asyncio.ensure_future(on_worker(w)))

        response = await page.goto(f"{BASE_URL}/dashboard/", wait_until="networkidle")
        headers = response.headers
        document = {
            "status": response.status,
            "contentSecurityPolicy": headers.get("content-security-policy"),
            "referrerPolicy": headers.get("referrer-policy"),
            "contentTypeOptions": headers.get("x-content-type-options"),
            "frameOptions": headers.get("x-frame-options"),
        }
        await page.goto(f"{BASE_URL}/dashboard/#/collections", wait_until="networkidle")
        await page.goto(f"{BASE_URL}/dashboard/#/console", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        # Exercise Monaco's JSON language worker through the packaged editor
        # bundle: a JSON model in the console editor starts it on demand.
        await page.evaluate(
            """() => { const m = window.monaco; if (m && m.editor) {
                 m.editor.createModel('{"probe": true}', 'json'); } }"""
        )
        await page.wait_for_timeout(3000)
        graph = await page.evaluate(GRAPH_JS, {"collection": COLLECTION, "workerUrl": graph_worker})
        await page.wait_for_timeout(1000)
        request_count = len(requests)

        cdp = await context.new_cdp_session(page)
        await cdp.send(
            "Storage.clearDataForOrigin", {"origin": BASE_URL, "storageTypes": "all"}
        )
        remaining = await page.evaluate("() => localStorage.length")
        await context.clear_cookies()
        await context.close()
        await browser.close()

    unexpected = [
        r["url"]
        for r in requests
        if not r["url"].startswith(("data:", "blob:"))
        and urlsplit(r["url"]).netloc != urlsplit(BASE_URL).netloc
    ]
    return {
        "browserVersion": browser_version,
        "playwrightPythonVersion": distribution_version("playwright"),
        "chromeLauncherSha256": sha256_file(CHROME_LAUNCHER),
        "chromeBinarySha256": sha256_file(CHROME_BINARY),
        "document": document,
        "cspExact": document["contentSecurityPolicy"] == EXPECTED_CSP,
        "cloudMetadata": {"requestPath": "/dashboard/cloud/data.json", **cloud},
        "workers": workers,
        "monacoEditorWorker": workers.get(editor_worker, False),
        "monacoJsonWorker": workers.get(json_worker, False),
        "graphWorker": workers.get(graph_worker, False),
        "graph": graph,
        "requestCount": request_count,
        "authorizedRequestCount": sum(1 for r in requests if r["authorization"]),
        "allAuthorizedRequestsUseScopedJwt": all(r["token_exact"] for r in requests),
        "unexpectedNetworkRequests": unexpected,
        "consoleErrors": console_errors,
        "pageErrors": page_errors,
        "siteDataCleared": remaining == 0,
    }


def main() -> int:
    jwt_file, out_path = sys.argv[1:3]
    token = Path(jwt_file).read_text(encoding="ascii").strip()
    result = asyncio.run(run(token))
    text = json.dumps(result, indent=1, sort_keys=True)
    if token in text:
        raise SystemExit("refusing to write a result that contains the JWT")
    Path(out_path).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
