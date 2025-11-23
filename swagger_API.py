"""
OpenAPI Query Tool

Purpose:
- Fetch multiple swagger.json (OpenAPI v2/v3) documents from given URLs.
- For each API, generate requests for endpoints (path+operation) and execute safe methods (GET).
- Save each endpoint's response JSON separately under swagger/twse, swagger/tpex, swagger/taifex.

Usage:
    python swagger_API.py

Dependencies:
    pip install requests

Notes:
- This script only executes GET endpoints to avoid side effects.
- For endpoints requiring authentication or private access, the request will likely
  return 401/403; you can provide headers (e.g. API key) via config.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
import urllib3

# Disable insecure request warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SWAGGER_URLS = [
    "https://openapi.twse.com.tw/v1/swagger.json",
    "https://www.tpex.org.tw/openapi/swagger.json",
    "https://openapi.taifex.com.tw/swagger.json",
]
BASE_OUTPUT_DIR = "./swagger"
ALLOWED_METHODS = ("get",)  # only execute safe GET endpoints
REQUEST_TIMEOUT = 10
# Optional headers if you need to provide API keys or specific Accept headers
GLOBAL_HEADERS = {
    "Accept": "application/json",
}

# --- Helpers to generate sample values for parameters and schemas ---

def sample_for_type(param):
    """Generate a conservative sample value for a parameter definition.
    param: dict with fields like 'type', 'format', 'enum'
    """
    if not param:
        return "sample"
    if 'enum' in param and isinstance(param['enum'], list) and param['enum']:
        return param['enum'][0]
    t = param.get('type', 'string')
    fmt = param.get('format', '')
    if t == 'integer' or t == 'number':
        return 1
    if t == 'boolean':
        return True
    if fmt == 'date':
        return datetime.utcnow().strftime('%Y%m%d')
    if fmt == 'date-time':
        return datetime.utcnow().isoformat() + 'Z'
    # default: string
    if 'pattern' in param:
        # try to satisfy simple digit patterns
        if re.search(r"\\d", param['pattern']):
            return '123'
    return 'sample'


def make_sample_body_from_schema(schema, definitions=None):
    """Create a sample JSON body from a (possibly) Swagger schema object.
    Very small heuristic generator: follows $ref, object properties, arrays.
    """
    if not schema:
        return {}
    # resolve simple $ref like '#/definitions/XYZ'
    if '$ref' in schema:
        ref = schema['$ref']
        m = re.match(r"#/?(?:definitions|components/schemas)?/([^/]+)$", ref)
        if m and definitions:
            key = m.group(1)
            sub = definitions.get(key) or definitions.get(key.replace('"', ''))
            if sub:
                return make_sample_body_from_schema(sub, definitions)
        return {}
    t = schema.get('type')
    if not t and 'properties' in schema:
        t = 'object'
    if t == 'object':
        obj = {}
        props = schema.get('properties', {})
        for k, v in props.items():
            obj[k] = make_sample_body_from_schema(v, definitions)
        return obj
    if t == 'array':
        items = schema.get('items', {})
        return [make_sample_body_from_schema(items, definitions)]
    # primitives
    if t == 'integer' or t == 'number':
        return 1
    if t == 'boolean':
        return True
    # string
    fmt = schema.get('format', '')
    if fmt == 'date':
        return datetime.utcnow().strftime('%Y%m%d')
    if fmt == 'date-time':
        return datetime.utcnow().isoformat() + 'Z'
    if 'enum' in schema and isinstance(schema['enum'], list):
        return schema['enum'][0]
    return schema.get('example') or 'sample'

# New helpers

def get_source_dir_name(swagger_url: str) -> str:
    """Map swagger URL to output folder name: twse, tpex, taifex; otherwise sanitized host."""
    if "twse" in swagger_url:
        return "twse"
    if "tpex" in swagger_url:
        return "tpex"
    if "taifex" in swagger_url:
        return "taifex"
    # fallback: sanitize
    return re.sub(r"[^0-9A-Za-z_-]+", "_", swagger_url)


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", name)


def list_operations(swagger):
    """Return all (path, method, operationObject) tuples from swagger paths."""
    paths = swagger.get('paths', {})
    ops = []
    for path, methods in paths.items():
        for method, op in methods.items():
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                ops.append((path, method.lower(), op))
    return ops

# --- Main logic ---

def fetch_swagger(url):
    print(f"Fetching swagger: {url}")
    try:
        r = requests.get(url, headers=GLOBAL_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.SSLError as e:
        print(f"SSL error fetching {url}, retrying without verification...")
        r = requests.get(url, headers=GLOBAL_HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
        r.raise_for_status()
        return r.json()


def build_request_for_operation(base_url, path, method, operation, swagger):
    """Build a sample request dict: url, method, headers, params, json body."""
    url = urljoin(base_url + '/', path.lstrip('/'))
    params = {}
    headers = GLOBAL_HEADERS.copy()
    body = None
    definitions = {}
    # Swagger 2.0 definitions
    if 'definitions' in swagger:
        definitions = swagger['definitions']
    # OpenAPI 3.x components
    if 'components' in swagger and 'schemas' in swagger['components']:
        definitions = swagger['components']['schemas']

    # collect parameters from operation
    parameters = operation.get('parameters', [])
    for p in parameters:
        p_in = p.get('in')
        name = p.get('name')
        sample = None
        if 'schema' in p:
            sample = make_sample_body_from_schema(p['schema'], definitions)
        else:
            sample = sample_for_type(p)
        if p_in == 'path':
            # substitute into url
            url = url.replace('{' + name + '}', str(sample))
        elif p_in == 'query':
            params[name] = sample
        elif p_in == 'header':
            headers[name] = sample
        elif p_in == 'body':
            body = sample
        elif p_in == 'formData':
            # treat as form fields
            if body is None:
                body = {}
            body[name] = sample

    # If operation has requestBody (OpenAPI3)
    if 'requestBody' in operation:
        content = operation['requestBody'].get('content', {})
        # pick application/json if present
        if 'application/json' in content:
            schema = content['application/json'].get('schema')
            body = make_sample_body_from_schema(schema, definitions)
        else:
            # pick the first content type
            for k, v in content.items():
                schema = v.get('schema')
                body = make_sample_body_from_schema(schema, definitions)
                break

    return {
        'url': url,
        'method': method.upper(),
        'headers': headers,
        'params': params,
        'json': body,
    }


def execute_request(req):
    method = req['method']
    try:
        if method == 'GET':
            r = requests.get(req['url'], headers=req['headers'], params=req['params'], timeout=REQUEST_TIMEOUT, verify=False)
        elif method == 'POST':
            r = requests.post(req['url'], headers=req['headers'], params=req['params'], json=req['json'], timeout=REQUEST_TIMEOUT, verify=False)
        elif method == 'PUT':
            r = requests.put(req['url'], headers=req['headers'], params=req['params'], json=req['json'], timeout=REQUEST_TIMEOUT, verify=False)
        elif method == 'DELETE':
            r = requests.delete(req['url'], headers=req['headers'], params=req['params'], timeout=REQUEST_TIMEOUT, verify=False)
        else:
            return {'error': f'Unsupported method {method}'}
        # attempt to parse json
        try:
            body = r.json()
        except Exception:
            body = r.text
        return {'status_code': r.status_code, 'headers': dict(r.headers), 'body': body}
    except requests.RequestException as e:
        return {'error': str(e)}


if __name__ == '__main__':
    import os

    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

    summary = {}
    for swagger_url in SWAGGER_URLS:
        try:
            swagger = fetch_swagger(swagger_url)
        except Exception as e:
            print(f"Failed to fetch swagger {swagger_url}: {e}")
            summary[swagger_url] = {'error': str(e)}
            continue

        # Discover baseUrl
        # Swagger 2.0 may have 'host' and 'basePath'
        base_url = ''
        if 'servers' in swagger and isinstance(swagger['servers'], list) and swagger['servers']:
            base_url = swagger['servers'][0].get('url', '')
        else:
            host = swagger.get('host') or ''
            basePath = swagger.get('basePath') or ''
            schemes = swagger.get('schemes', [])
            scheme = schemes[0] if schemes else 'https'
            if host:
                base_url = f"{scheme}://{host}{basePath}"
            else:
                # fallback to swagger file location
                base_url = re.sub(r'/swagger.json$', '', swagger_url)

        # Prepare output directory per source
        source_dir_name = get_source_dir_name(swagger_url)
        source_dir = os.path.join(BASE_OUTPUT_DIR, source_dir_name)
        os.makedirs(source_dir, exist_ok=True)

        # List all operations and execute GET only
        ops = list_operations(swagger)
        manifest = []
        idx = 0
        for path, method, op in ops:
            if method.lower() not in ALLOWED_METHODS:
                continue
            idx += 1
            req = build_request_for_operation(base_url, path, method, op, swagger)
            print(f"[{source_dir_name}] {idx}: {req['method']} {req['url']}")
            exec_res = execute_request(req)
            out = {
                'path': path,
                'method': method.upper(),
                'operationId': op.get('operationId'),
                'summary': op.get('summary'),
                'request': req,
                'response': exec_res,
            }
            # Save per-endpoint JSON
            filename = f"{method.upper()}_{sanitize_filename(path)}.json"
            fn = os.path.join(source_dir, filename)
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            manifest.append({
                'file': filename,
                'path': path,
                'method': method.upper(),
                'operationId': op.get('operationId'),
                'summary': op.get('summary'),
                'status_code': exec_res.get('status_code'),
            })
            # be polite to remote servers
            time.sleep(0.3)

        # save manifest per source
        manifest_fn = os.path.join(source_dir, 'manifest.json')
        with open(manifest_fn, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(manifest)} GET endpoints to {source_dir}")
        summary[swagger_url] = {'output_dir': source_dir, 'get_count': len(manifest)}

    # summary
    summary_fn = os.path.join(BASE_OUTPUT_DIR, 'summary.json')
    with open(summary_fn, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Wrote summary to {summary_fn}")
