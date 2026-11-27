"""Validate the assignment's system description and API contracts."""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main():
    system = read_yaml(ROOT / "system.yaml")
    schema = json.loads((ROOT / "system.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(system)

    services = system["services"]
    compose = read_yaml(ROOT / "docker-compose.yml")["services"]
    if not (ROOT / system["ui"]["path"]).is_dir():
        raise SystemExit("system.yaml points at a missing UI directory")
    for name in system["ui"]["calls"]:
        if name not in services:
            raise SystemExit(f"UI calls undocumented service {name}")

    specs = {}
    for name, service in services.items():
        directory = ROOT / service["path"]
        build = compose.get(name, {}).get("build")
        if not build or (ROOT / build).resolve() != directory.resolve():
            raise SystemExit(f"{name}: system.yaml path does not match its Compose build context")
        if not (ROOT / service["migrations"]).is_dir():
            raise SystemExit(f"{name}: missing migrations directory {service['migrations']}")
        path = ROOT / service["openapi"]
        spec = read_yaml(path)
        validate(spec, base_uri=path.as_uri())
        if "health" in service and "get" not in spec["paths"].get(service["health"], {}):
            raise SystemExit(f"{name}: missing GET {service['health']} in {service['openapi']}")
        specs[name] = spec
        print(f"{service['openapi']} is valid", flush=True)

    for name, service in services.items():
        for call in service.get("calls", []):
            target = call["service"]
            if target not in specs or call["url_env"] not in service["env"]:
                raise SystemExit(f"{name}: invalid destination or URL variable for call to {target}")
            for endpoint in call["endpoints"]:
                method, path = endpoint.split(" ", 1)
                if method.lower() not in specs[target]["paths"].get(path, {}):
                    raise SystemExit(f"{name}: {target} does not document {endpoint}")

    print("system.yaml matches system.schema.json, Compose and the OpenAPI contracts")


if __name__ == "__main__":
    main()
