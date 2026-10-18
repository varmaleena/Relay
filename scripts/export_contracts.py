"""Deterministically export domain JSON schemas, OpenAPI and a typed TS client."""
# ruff: noqa: E501 -- embedded generated TypeScript source retains readable lines.

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from packages.schemas import models
from services.api.contracts import contract_app

ROOT = Path(__file__).resolve().parents[1]


def ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1].replace("-", "_")
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    for key in ["anyOf", "oneOf"]:
        if key in schema:
            return " | ".join(ts_type(item) for item in schema[key])
    kind = schema.get("type")
    if kind == "array":
        return f"Array<{ts_type(schema.get('items', {}))}>"
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not properties:
            additional = schema.get("additionalProperties", {})
            return f"Record<string, {ts_type(additional) if isinstance(additional, dict) else 'unknown'}>"
        required = schema.get("required", [])
        fields = [
            f"{json.dumps(name)}{'' if name in required else '?'}: {ts_type(value)}"
            for name, value in properties.items()
        ]
        return "{ " + "; ".join(fields) + " }"
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }.get(str(kind), "unknown")


def outputs() -> dict[Path, str]:
    app = contract_app()
    document = app.openapi()
    document["components"]["securitySchemes"] = {
        "FirebaseAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "Firebase ID token"},
        "AppCheck": {"type": "apiKey", "in": "header", "name": "X-Firebase-AppCheck"},
    }
    paged = {"E20", "E22", "E31", "E37", "E39"}
    filters = {
        "E22": ["status", "urgency", "typology"],
        "E23": ["packetId"],
        "E27": ["jurisdiction", "status"],
        "E31": ["q"],
        "E39": ["system", "metric", "slice"],
    }
    for _path, methods in document["paths"].items():
        for method, operation in methods.items():
            identifier = operation["operationId"]
            parameters = operation.setdefault("parameters", [])
            if operation["x-relay-roles"]:
                operation["security"] = [{"FirebaseAuth": [], "AppCheck": []}]
            if identifier == "E38":
                operation["x-relay-public-if"] = "PUBLIC_EVAL=true"
            parameters.append(
                {
                    "name": "X-Request-Id",
                    "in": "header",
                    "required": False,
                    "schema": {"type": "string"},
                }
            )
            if method == "post":
                parameters.append(
                    {
                        "name": "Idempotency-Key",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                )
            if identifier in paged:
                parameters += [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                    },
                    {
                        "name": "cursor",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                    },
                ]
            parameters += [
                {"name": name, "in": "query", "required": False, "schema": {"type": "string"}}
                for name in filters.get(identifier, [])
            ]
            for response_entry in operation["responses"].values():
                response_entry["headers"] = {"X-Request-Id": {"schema": {"type": "string"}}}
    result = {ROOT / "docs/openapi.json": json.dumps(document, indent=2, ensure_ascii=False) + "\n"}
    domain = {}
    for name, cls in inspect.getmembers(models, inspect.isclass):
        if issubclass(cls, BaseModel) and cls.__module__ == models.__name__:
            domain[name] = cls.model_json_schema(by_alias=True)
    result[ROOT / "docs/schemas/domain.json"] = (
        json.dumps(domain, indent=2, ensure_ascii=False) + "\n"
    )
    result[ROOT / "docs/schemas/pack.disk.json"] = (
        json.dumps(models.Pack.model_json_schema(by_alias=False), indent=2, ensure_ascii=False)
        + "\n"
    )
    # Include domain-only types (Live frames, approval, job envelope).
    schemas = dict(document["components"]["schemas"])
    for domain_name, schema in domain.items():
        schemas.setdefault(domain_name, schema)
        for definition_name, definition in schema.get("$defs", {}).items():
            schemas.setdefault(definition_name, definition)
    declarations = ["// Generated by scripts/export_contracts.py. Do not edit."]
    declarations += [
        f"export type {name.replace('-', '_')} = {ts_type(schema)};"
        for name, schema in sorted(schemas.items())
    ]
    operations = []
    methods = []
    for path, verbs in document["paths"].items():
        for verb, operation in verbs.items():
            name = operation["operationId"]
            body = (
                operation.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            response: dict[str, Any] = next(
                (
                    value
                    for code, value in operation["responses"].items()
                    if code.startswith("2") or code == "302"
                ),
                {},
            )
            response_type = ts_type(
                response.get("content", {}).get("application/json", {}).get("schema", {})
            )
            if not response.get("content"):
                response_type = "void"
            fields = []
            arguments = []
            route = json.dumps(path)
            for parameter in operation.get("parameters", []):
                if parameter["in"] == "path":
                    key = parameter["name"]
                    fields.append(f"{key}: string")
                    arguments.append(key)
                    route += f".replace('{{{key}}}', encodeURIComponent(input.{key}))"
            if body:
                fields.append(f"body: {ts_type(body)}")
            fields.append("query?: Record<string, string | number>")
            fields.append("idempotencyKey?: string")
            operations.append(
                f"  {name}: {{ input: {{ {'; '.join(fields)} }}; output: {response_type} }};"
            )
            methods.append(
                f"  {name}(input: Operations['{name}']['input']): Promise<Operations['{name}']['output']> {{\n"
                f"    return this.request({json.dumps(verb.upper())}, {route}, input);\n  }}"
            )
    declarations += ["export interface Operations {", *operations, "}"]
    result[ROOT / "apps/web/src/generated/contracts.ts"] = "\n".join(declarations) + "\n"
    client = """// Generated. Contract-only operations currently return 501; this is not a functioning product.
import type { Operations } from './contracts';
export class RelayClient {
  constructor(private baseUrl: string, private tokens: () => Promise<{idToken: string; appCheckToken: string}>) {}
  private async request<T>(method: string, path: string, input: {body?: unknown; query?: Record<string, string | number>; idempotencyKey?: string}): Promise<T> {
    const auth = await this.tokens();
    const url = new URL(this.baseUrl.replace(/\\/$/, '') + path);
    for (const [key, value] of Object.entries(input.query ?? {})) url.searchParams.set(key, String(value));
    const headers: Record<string, string> = {'Authorization': `Bearer ${auth.idToken}`, 'X-Firebase-AppCheck': auth.appCheckToken};
    if (input.body !== undefined) headers['Content-Type'] = 'application/json';
    if (method === 'POST') headers['Idempotency-Key'] = input.idempotencyKey ?? crypto.randomUUID();
    const response = await fetch(url, {method, headers, body: input.body === undefined ? undefined : JSON.stringify(input.body), redirect: 'manual'});
    if (response.status === 302) throw new Error('PDF redirect requires explicit navigation to the authorized Location URL');
    if (!response.ok) {
      const delay = Number(response.headers.get('Retry-After'));
      const retryAfterSeconds = Number.isFinite(delay) && delay > 0 && delay <= 3600 ? Math.ceil(delay) : undefined;
      throw Object.assign(new Error(`Relay HTTP ${response.status}`), {status: response.status, retryAfterSeconds, problem: await response.json()});
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
"""
    result[ROOT / "apps/web/src/generated/client.ts"] = client + "\n".join(methods) + "\n}\n"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    for path, content in outputs().items():
        if arguments.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(
                    f"Contract drift: {path.relative_to(ROOT)}; run python -m scripts.export_contracts"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
