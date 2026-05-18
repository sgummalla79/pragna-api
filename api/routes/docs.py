"""
Custom Swagger UI with version switcher.

Versioning strategy:
  - Routes without a version prefix (/api/...) are v1.
  - Routes at /api/v2/... are v2-specific additions/changes.
  - /api/v3/... would be v3-specific, and so on.

Each version is cumulative:
  v1 docs → all routes with no version prefix
  v2 docs → all v1 routes + all /api/v2/ routes
  v3 docs → all v1 + v2 routes + all /api/v3/ routes
  ...

When a new version is added, these endpoints pick it up automatically.

GET /docs              — version-aware Swagger UI (?version=1|2|...)
GET /openapi/v{n}.json — cumulative OpenAPI schema for version n
"""

import os
import re
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(include_in_schema=False)

_ROOT_PATH = os.getenv("ROOT_PATH", "")

_SWAGGER_JS  = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
_SWAGGER_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"


def _path_version(path: str) -> int:
    """Return the version number a path belongs to. Unversioned paths are v1."""
    m = re.search(r"^/api/v(\d+)/", path)
    return int(m.group(1)) if m else 1


def _available_versions(schema: dict) -> list[int]:
    """Detect all API versions present in the schema."""
    versions = {1}
    for path in schema.get("paths", {}):
        versions.add(_path_version(path))
    return sorted(versions)


def _schema_for_version(schema: dict, version: int) -> dict:
    """Return a cumulative schema containing all routes up to and including `version`."""
    return {
        **schema,
        "info": {
            **schema.get("info", {}),
            "title": f"Pragna API — v{version}",
        },
        "paths": {
            path: ops
            for path, ops in schema.get("paths", {}).items()
            if _path_version(path) <= version
        },
    }


def _docs_html(openapi_url: str, title: str, current_version: int, versions: list[int]) -> str:
    login_url = f"{_ROOT_PATH}/auth/initiate"

    version_buttons = ""
    for v in versions:
        active = "active" if v == current_version else ""
        url = f"{_ROOT_PATH}/docs?version={v}"
        version_buttons += f'<a class="version-btn {active}" href="{url}">v{v}</a>\n'

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>{title}</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="{_SWAGGER_CSS}">
  <style>
    body {{ margin: 0; }}

    #version-bar {{
      background: #1b1b1b;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 20px;
      font-family: sans-serif;
      font-size: 14px;
      position: sticky;
      top: 0;
      z-index: 9999;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }}

    #version-bar .label {{ opacity: 0.6; margin-right: 4px; }}

    #version-bar a.version-btn {{
      text-decoration: none;
      padding: 5px 16px;
      border-radius: 20px;
      font-weight: 600;
      font-size: 13px;
      border: 2px solid transparent;
      color: #aaa;
      transition: all 0.15s;
    }}

    #version-bar a.version-btn:hover {{ color: #fff; border-color: #555; }}

    #version-bar a.version-btn.active {{
      color: #fff;
      background: #4caf7d;
      border-color: #4caf7d;
    }}

    #version-bar .login-btn {{
      margin-left: auto;
      background: #3b82f6;
      color: #fff;
      padding: 5px 16px;
      border-radius: 20px;
      text-decoration: none;
      font-weight: 600;
      font-size: 13px;
      transition: background 0.15s;
    }}

    #version-bar .login-btn:hover {{ background: #2563eb; }}

    .swagger-ui .topbar {{ display: none; }}
  </style>
</head>
<body>

<div id="version-bar">
  <span class="label">API version:</span>
  {version_buttons}
  <a class="login-btn" href="{login_url}">Log in</a>
</div>

<div id="swagger-ui"></div>

<script src="{_SWAGGER_JS}"> </script>
<script>
  window.onload = function() {{
    SwaggerUIBundle({{
      url:             "{openapi_url}",
      dom_id:          "#swagger-ui",
      presets:         [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout:          "BaseLayout",
      deepLinking:     true,
      withCredentials: true,
      defaultModelsExpandDepth: -1,
    }});
  }};
</script>
</body>
</html>"""


@router.get("/docs")
async def custom_docs(request: Request, version: int = 1):
    schema   = request.app.openapi()
    versions = _available_versions(schema)
    version  = max(1, min(version, max(versions)))

    openapi_url = f"{_ROOT_PATH}/openapi/v{version}.json"
    title       = f"Pragna API — v{version}"

    return HTMLResponse(_docs_html(openapi_url, title, version, versions))


@router.get("/openapi/v{version}.json")
async def versioned_openapi(request: Request, version: int):
    schema   = request.app.openapi()
    versions = _available_versions(schema)

    if version not in versions:
        return JSONResponse({"detail": f"Version {version} not found."}, status_code=404)

    return JSONResponse(_schema_for_version(schema, version))
