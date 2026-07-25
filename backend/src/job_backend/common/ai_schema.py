from pydantic import BaseModel, JsonValue, TypeAdapter


def completion_schema(response_model: type[BaseModel], *, strict: bool) -> dict[str, JsonValue]:
    schema = TypeAdapter(dict[str, JsonValue]).validate_python(response_model.model_json_schema())
    if strict:
        _require_properties(schema)
    return schema


def _require_properties(schema: dict[str, JsonValue]) -> None:
    schema.pop("default", None)
    properties = schema.get("properties")
    if schema.get("type") == "object" and isinstance(properties, dict):
        schema["required"] = list(properties)
        schema["additionalProperties"] = False
    for keyword in ("properties", "$defs", "definitions"):
        definitions = schema.get(keyword)
        if isinstance(definitions, dict):
            for child in definitions.values():
                if isinstance(child, dict):
                    _require_properties(child)
    items = schema.get("items")
    if isinstance(items, dict):
        _require_properties(items)
    for keyword in ("anyOf", "allOf", "oneOf", "prefixItems"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, list):
            for child in alternatives:
                if isinstance(child, dict):
                    _require_properties(child)
