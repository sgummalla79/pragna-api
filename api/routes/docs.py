"""
Custom Swagger UI with version switcher.

GET /docs              — version-aware Swagger UI (query: ?version=v1|v2)
GET /openapi/v1.json   — OpenAPI schema for v1 routes only
GET /openapi/v2.json   — OpenAPI schema for v2 routes only
"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(include_in_schema=False)

_ROOT_PATH = os.getenv("ROOT_PATH", "")

_SWAGGER_JS  = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
_SWAGGER_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"


def _docs_html(openapi_url: str, title: str, version: str) -> str:
    v1_url   = f"{_ROOT_PATH}/docs?version=v1"
    v2_url   = f"{_ROOT_PATH}/docs?version=v2"
    login_url = f"{_ROOT_PATH}/auth/initiate"

    v1_active = "active" if version == "v1" else ""
    v2_active = "active" if version == "v2" else ""

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
      gap: 12px;
      padding: 10px 20px;
      font-family: sans-serif;
      font-size: 14px;
      position: sticky;
      top: 0;
      z-index: 9999;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }}

    #version-bar .label {{
      opacity: 0.6;
      margin-right: 4px;
    }}

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

    #version-bar a.version-btn:hover {{
      color: #fff;
      border-color: #555;
    }}

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

    #version-bar .login-btn:hover {{
      background: #2563eb;
    }}

    .swagger-ui .topbar {{ display: none; }}
  </style>
</head>
<body>

<div id="version-bar">
  <span class="label">API version:</span>
  <a class="version-btn {v1_active}" href="{v1_url}">v1</a>
  <a class="version-btn {v2_active}" href="{v2_url}">v2</a>
  <a class="login-btn" href="{login_url}">Log in</a>
</div>

<div id="swagger-ui"></div>

<script src="{_SWAGGER_JS}"> </script>
<script>
  window.onload = function() {{
    SwaggerUIBundle({{
      url:            "{openapi_url}",
      dom_id:         "#swagger-ui",
      presets:        [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout:         "BaseLayout",
      deepLinking:    true,
      withCredentials: true,
      defaultModelsExpandDepth: -1,
    }});
  }};
</script>
</body>
</html>"""


@router.get("/docs")
async def custom_docs(version: str = "v1"):
    if version == "v2":
        openapi_url = f"{_ROOT_PATH}/openapi/v2.json"
        title       = "Pragna API — v2"
    else:
        openapi_url = f"{_ROOT_PATH}/openapi/v1.json"
        title       = "Pragna API — v1"

    return HTMLResponse(_docs_html(openapi_url, title, version))


@router.get("/openapi/v1.json")
async def openapi_v1(request: Request):
    schema = request.app.openapi()
    return JSONResponse({
        **schema,
        "info": {**schema.get("info", {}), "title": "Pragna API — v1"},
        "paths": {
            path: ops
            for path, ops in schema.get("paths", {}).items()
            if not path.startswith("/api/v2/")
        },
    })


@router.get("/openapi/v2.json")
async def openapi_v2(request: Request):
    schema = request.app.openapi()
    return JSONResponse({
        **schema,
        "info": {**schema.get("info", {}), "title": "Pragna API — v2"},
    })
