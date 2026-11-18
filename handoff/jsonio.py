from decimal import Decimal
import json


def deterministic_json(value: object) -> str:
    """Serialize to stable, ASCII, compact JSON.

    Unbounded Python integers are emitted through ``Decimal`` so every digit
    is preserved without touching the interpreter's integer string limit.
    The same stored object always renders to the same bytes.
    """
    if type(value) is int:
        return str(Decimal(value))
    if isinstance(value, dict):
        members = (
            json.dumps(key) + ':' + deterministic_json(item)
            for key, item in value.items()
        )
        return '{' + ','.join(members) + '}'
    if isinstance(value, list):
        return '[' + ','.join(deterministic_json(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))
