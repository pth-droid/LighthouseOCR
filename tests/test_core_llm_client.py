"""
Tests for core_llm_client.parse_json_response.
ASCII-only to avoid Windows encoding issues.
"""
import sys
sys.path.insert(0, '.')

from core_llm_client import parse_json_response

def check(label, condition, detail=""):
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label} | {detail}")
        sys.exit(1)

print("=" * 60)
print("TEST: core_llm_client.parse_json_response")
print("=" * 60)

# Plain JSON
result = parse_json_response('{"key": "value"}')
check("plain JSON object", result == {"key": "value"}, f"got {result}")

# JSON with whitespace
result = parse_json_response('  {"a": 1}  ')
check("JSON with leading/trailing whitespace", result == {"a": 1}, f"got {result}")

# Markdown fence stripped
result = parse_json_response('```json\n{"b": 2}\n```')
check("markdown fence stripped", result == {"b": 2}, f"got {result}")

# Markdown fence without language tag
result = parse_json_response('```\n{"c": 3}\n```')
check("markdown fence no language tag", result == {"c": 3}, f"got {result}")

# ast.literal_eval fallback for Python-style dict
result = parse_json_response("{'d': 4}")
check("ast.literal_eval fallback", result == {"d": 4}, f"got {result}")

# Nested structure
result = parse_json_response('{"items": [1, 2, 3], "total": 6}')
check("nested JSON", result == {"items": [1, 2, 3], "total": 6}, f"got {result}")

# Unparseable input raises ValueError
raised = False
try:
    parse_json_response("not json at all")
except ValueError:
    raised = True
check("unparseable input raises ValueError", raised)

# Non-dict ast result raises ValueError (list)
raised = False
try:
    parse_json_response("[1, 2, 3]")
except ValueError:
    raised = True
check("non-dict ast result raises ValueError", raised)

print("\n" + "=" * 60)
print("ALL core_llm_client TESTS PASSED")
print("=" * 60)
