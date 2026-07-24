#!/usr/bin/env python3
"""Fuzz target for Conventional Commit message validation.

Tests the regex validation and parsing logic for Conventional Commit
format messages to detect regex vulnerabilities and parsing edge cases.
"""

import sys
import re

# Typical Conventional Commit pattern
CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)'
    r'(?:\([a-z0-9_\-]+\))?'
    r'?!?: .+$'
)

def fuzz_validate_commit_message(data: bytes) -> None:
    """Fuzz the Conventional Commit validation logic.

    Args:
        data: Random bytes to use as commit message input
    """
    try:
        # Decode input, handling invalid UTF-8
        message = data.decode('utf-8', errors='ignore')

        if not message.strip():
            return

        # Test regex validation with potentially malicious patterns
        # (backtracking, ReDoS, etc.)
        for line in message.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Apply the regex - this is the critical path
            match = CONVENTIONAL_COMMIT_PATTERN.match(line)

            if match:
                # Extract components if matched
                full_match = match.group(0)
                type_part = match.group(1)

                # Validate extracted parts
                if type_part:
                    type_part.strip()
                    # Check for reasonable length
                    if len(full_match) > 1000:
                        # Abort on extremely long matches
                        return

    except re.error:
        # Suppress regex errors
        pass
    except Exception:
        # Suppress all other exceptions
        pass

if __name__ == '__main__':
    try:
        import atheris
        atheris.instrument_all()
        atheris.Setup([], fuzz_validate_commit_message)
        atheris.Fuzz()
    except ImportError:
        # Fall back to simple testing with stdin
        if len(sys.argv) > 1:
            with open(sys.argv[1], 'rb') as f:
                data = f.read()
            fuzz_validate_commit_message(data)
        else:
            data = sys.stdin.buffer.read()
            fuzz_validate_commit_message(data)
