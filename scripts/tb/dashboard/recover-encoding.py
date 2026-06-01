#!/usr/bin/env python3
"""
Reverse the double-UTF-8 encoding mojibake introduced by a PowerShell roundtrip
(Invoke-RestMethod -> ConvertTo-Json -> UTF8 GetBytes -> POST).

PowerShell 5.1 reads JSON responses as Latin-1 by default, so each UTF-8 byte
becomes a separate codepoint in 0x80-0xFF. When re-serialized to JSON, ConvertTo-Json
may either keep them as native chars OR emit \\u00XY escape sequences. UTF8.GetBytes
then encodes those chars again, producing the mojibake.

Recovery strategy:
  - Load JSON properly with json.loads (expands all \\u escapes to Unicode codepoints).
  - Walk the structure, apply recovery on each string value:
      * Chars 0x00-0x7F : keep
      * Chars 0x80-0xFF : these are mojibake-flagged bytes -> reinterpret as UTF-8 bytes
      * Chars > 0xFF    : keep as-is (emojis, curly quotes etc. were native multi-byte UTF-8)
  - Re-serialize JSON with ensure_ascii=False so the recovered chars appear as native UTF-8.

Usage:
  recover-encoding.py <input.json> <output.json>
"""

import json
import sys

if len(sys.argv) != 3:
    sys.exit('Usage: recover-encoding.py <input.json> <output.json>')


def recover_string(s):
    """Apply mojibake recovery to a string.
    Returns the recovered string."""
    # Collect bytes from chars in 0x80-0xFF range; emit other chars as-is.
    out_bytes = bytearray()
    i = 0
    chars = list(s)
    while i < len(chars):
        c = chars[i]
        cp = ord(c)
        if cp < 0x80:
            out_bytes.append(cp)
            i += 1
        elif cp < 0x100:
            # Mojibake byte. Collect contiguous run.
            run = bytearray()
            while i < len(chars) and 0x80 <= ord(chars[i]) < 0x100:
                run.append(ord(chars[i]))
                i += 1
            # Try to decode the run as UTF-8.
            try:
                # decode then re-encode to validate
                decoded = run.decode('utf-8')
                out_bytes.extend(decoded.encode('utf-8'))
            except UnicodeDecodeError:
                # Not valid UTF-8 - emit as Latin-1 chars
                out_bytes.extend(run)
        else:
            # Native multi-byte (emoji, curly quote, etc.) - keep
            out_bytes.extend(c.encode('utf-8'))
            i += 1
    return out_bytes.decode('utf-8')


def walk(obj):
    """Recursively walk JSON structure, applying recover_string to all strings."""
    if isinstance(obj, dict):
        return {recover_string(k) if isinstance(k, str) else k: walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v) for v in obj]
    if isinstance(obj, str):
        return recover_string(obj)
    return obj


with open(sys.argv[1], 'rb') as f:
    raw = f.read()
if raw.startswith(b'\xef\xbb\xbf'):
    raw = raw[3:]

obj = json.loads(raw.decode('utf-8'))
recovered = walk(obj)

# Serialize without ASCII escaping so accents appear as native UTF-8 bytes.
out = json.dumps(recovered, ensure_ascii=False, indent=None, separators=(',', ':'))

with open(sys.argv[2], 'wb') as f:
    f.write(out.encode('utf-8'))

print(f'Input  : {len(raw)} bytes')
print(f'Output : {len(out.encode("utf-8"))} bytes')
