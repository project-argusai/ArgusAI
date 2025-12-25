#!/usr/bin/env python3
"""
Story P10-5.1: Export OpenAPI Specification

Exports the ArgusAI OpenAPI 3.0 specification to YAML and JSON formats.

Usage:
    cd backend
    python scripts/export_openapi.py

Output:
    - docs/api/openapi-v1.yaml
    - docs/api/openapi-v1.json
"""
import sys
import json
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import yaml


def export_openapi():
    """Export OpenAPI specification to docs/api/ directory."""
    # Import FastAPI app to generate OpenAPI schema
    from main import app

    # Get the OpenAPI schema
    openapi_schema = app.openapi()

    # Define output paths
    project_root = backend_dir.parent
    api_docs_dir = project_root / "docs" / "api"
    api_docs_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = api_docs_dir / "openapi-v1.yaml"
    json_path = api_docs_dir / "openapi-v1.json"

    # Export as YAML
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Exported OpenAPI YAML to: {yaml_path}")

    # Export as JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    print(f"Exported OpenAPI JSON to: {json_path}")

    # Print summary
    paths_count = len(openapi_schema.get("paths", {}))
    schemas_count = len(openapi_schema.get("components", {}).get("schemas", {}))
    tags_count = len(openapi_schema.get("tags", []))

    print(f"\nOpenAPI Specification Summary:")
    print(f"  Version: {openapi_schema.get('info', {}).get('version', 'unknown')}")
    print(f"  Title: {openapi_schema.get('info', {}).get('title', 'unknown')}")
    print(f"  Paths: {paths_count}")
    print(f"  Schemas: {schemas_count}")
    print(f"  Tags: {tags_count}")

    return True


if __name__ == "__main__":
    try:
        export_openapi()
        print("\nExport complete!")
    except Exception as e:
        print(f"Export failed: {e}", file=sys.stderr)
        sys.exit(1)
