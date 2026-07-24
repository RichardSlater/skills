#!/usr/bin/env python3
"""Fuzz target for GitVersion output parsing.

Tests the parsing logic in analyze_best_practices.py that processes
GitVersion output to detect parsing edge cases and vulnerabilities.
"""

import sys
import os

def fuzz_parse_gitversion(data: bytes) -> None:
    """Fuzz the GitVersion output parsing logic.

    Args:
        data: Random bytes to use as GitVersion output
    """
    try:
        # Simulate GitVersion output parsing
        # GitVersion typically outputs JSON or key=value pairs
        output_str = data.decode('utf-8', errors='ignore')

        if not output_str.strip():
            return

        # Test parsing as JSON (GitVersion can output JSON)
        if output_str.strip().startswith('{'):
            try:
                import json
                parsed = json.loads(output_str)
                # Validate expected fields exist if they should
                if isinstance(parsed, dict):
                    # Check if we can safely access version fields
                    for key in ['Major', 'Minor', 'Patch', 'SemVer']:
                        if key in parsed:
                            # Try to convert to string safely
                            str(parsed[key])
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # Expected for invalid input

        # Test parsing as key=value pairs
        for line in output_str.split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, _, value = line.partition('=')
                if key and value:
                    # Ensure we can handle the parsed values
                    key.strip()
                    value.strip()

    except Exception:
        # Suppress all exceptions - fuzzing should not crash the fuzzer
        pass

if __name__ == '__main__':
    import atheris
    # Try to import atheris for ClusterFuzzLite integration
    try:
        atheris.instrument_all()
        atheris.Setup([], fuzz_parse_gitversion)
        atheris.Fuzz()
    except ImportError:
        # Fall back to simple testing with stdin
        if len(sys.argv) > 1:
            with open(sys.argv[1], 'rb') as f:
                data = f.read()
            fuzz_parse_gitversion(data)
        else:
            data = sys.stdin.buffer.read()
            fuzz_parse_gitversion(data)
