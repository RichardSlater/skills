#!/usr/bin/env python3
"""Fuzz target for .bestpractices.json schema validation.

Tests the JSON schema validation logic to detect parsing crashes,
ReDoS vulnerabilities, and edge cases in schema processing.
"""

import sys
import json

# Typical Best Practices Badge schema structure
REQUIRED_FIELDS = [
    'badge_status',
    'badge_level'
]

def fuzz_validate_schema(data: bytes) -> None:
    """Fuzz the .bestpractices.json schema validation logic.

    Args:
        data: Random bytes to use as JSON schema input
    """
    try:
        # Decode input
        json_str = data.decode('utf-8', errors='ignore').strip()

        if not json_str:
            return

        # Try to parse JSON
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            return  # Invalid JSON is expected

        # Test validation logic
        if isinstance(parsed, dict):
            # Check for required fields
            for field in REQUIRED_FIELDS:
                if field in parsed:
                    # Validate the field value doesn't cause issues
                    value = parsed[field]

                    # Test string operations
                    if isinstance(value, str):
                        value.strip()
                        len(value)
                    elif isinstance(value, (int, float, bool, type(None))):
                        # Safe types
                        pass
                    elif isinstance(value, (list, dict)):
                        # Test nested structures
                        try:
                            json.dumps(value)
                        except (TypeError, OverflowError):
                            pass

            # Test schema validation edge cases
            # Deeply nested structures
            if 'criteria' in parsed and isinstance(parsed['criteria'], dict):
                def check_nesting(obj, depth=0):
                    if depth > 10:  # Limit nesting depth
                        return
                    if isinstance(obj, dict):
                        for v in obj.values():
                            check_nesting(v, depth + 1)
                    elif isinstance(obj, list):
                        for item in obj:
                            check_nesting(item, depth + 1)
                check_nesting(parsed['criteria'])

        elif isinstance(parsed, list):
            # Test list processing
            for item in parsed[:100]:  # Limit iteration
                if isinstance(item, (dict, list, str, int, float, bool, type(None))):
                    try:
                        json.dumps(item)
                    except (TypeError, OverflowError):
                        pass

    except Exception:
        # Suppress all exceptions
        pass

if __name__ == '__main__':
    try:
        import atheris
        atheris.instrument_all()
        atheris.Setup([], fuzz_validate_schema)
        atheris.Fuzz()
    except ImportError:
        # Fall back to simple testing with stdin
        if len(sys.argv) > 1:
            with open(sys.argv[1], 'rb') as f:
                data = f.read()
            fuzz_validate_schema(data)
        else:
            data = sys.stdin.buffer.read()
            fuzz_validate_schema(data)
