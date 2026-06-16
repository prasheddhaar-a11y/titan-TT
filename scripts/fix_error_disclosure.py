"""
fix_error_disclosure.py
=======================
Fixes CWE-200/CWE-209 Information Disclosure: raw database/exception messages
returned in HTTP responses.

What it does:
  - Scans all production Python views.py / services.py files (skips bck/, Recovery_*,
    migrations/, env/, __pycache__, staticfiles/).
  - Replaces any `str(e)` appearing inside response payloads (JsonResponse, Response,
    messages.error, response dict keys 'error'/'message') with the generic safe message.
  - Converts print(...str(e)...) exception logging to logger.error(..., exc_info=True).
  - Ensures `import logging` + `logger = logging.getLogger(__name__)` is present in
    every touched file.

Run:
    python scripts/fix_error_disclosure.py
"""

import re
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAFE_MSG = "Unable to process the request. Please verify the submitted data and try again."

SKIP_DIRS = {
    'bck', 'Recovery_IQF', 'Recovery_IS', 'Recovery_DP',
    'Recovery_Brass_QC', 'Recovery_BrassAudit',
    '__pycache__', 'env', 'staticfiles', 'migrations',
    'node_modules', '.git', 'automation',
}


def should_skip_path(path: str) -> bool:
    parts = path.replace('\\', '/').split('/')
    return any(p in SKIP_DIRS for p in parts)


def collect_python_files(base: str):
    result = []
    for root, dirs, files in os.walk(base):
        # Prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if fname.endswith('.py'):
                full = os.path.join(root, fname)
                if not should_skip_path(full):
                    result.append(full)
    return result


# ---------------------------------------------------------------------------
# Patterns that expose str(e) in responses
# ---------------------------------------------------------------------------

# Matches:  'error': 'Unable to process the request. Please verify the submitted data and try again.'   or   "error": 'Unable to process the request. Please verify the submitted data and try again.'
# inside a response dict value position
PATTERN_ERROR_KEY_STR_E = re.compile(
    r"""(['"]error['"])\s*:\s*str\(e\)""",
    re.IGNORECASE,
)

# Matches:  'message': 'Unable to process the request. Please verify the submitted data and try again.'
PATTERN_MESSAGE_KEY_STR_E = re.compile(
    r"""(['"]message['"])\s*:\s*str\(e\)""",
    re.IGNORECASE,
)

# Matches f-string value for 'error' key:  'error': 'Unable to process the request. Please verify the submitted data and try again.'
# Handles both single and double-quoted f-strings (non-greedy, single line)
PATTERN_ERROR_FSTR = re.compile(
    r"""(['"]error['"])\s*:\s*f(['"])[^'"]*\{str\(e\)[^'"]*\2""",
)

# Matches f-string value for 'message' key: 'message': 'Unable to process the request. Please verify the submitted data and try again.'
PATTERN_MESSAGE_FSTR = re.compile(
    r"""(['"]message['"])\s*:\s*f(['"])[^'"]*\{str\(e\)[^'"]*\2""",
)

# Matches f-string value for 'valid' => 'message' pattern
#   Response({'valid': False, 'message': 'Unable to process the request. Please verify the submitted data and try again.'}, ...)
PATTERN_VALID_MSG_FSTR = re.compile(
    r"""(['"]message['"])\s*:\s*f(['"])[^'"]*\{str\(e\)[^'"]*\2""",
)

# Matches: messages.error(request, "Unable to process the request. Please verify the submitted data and try again.")
PATTERN_MESSAGES_ERROR = re.compile(
    r"""messages\.error\(request,\s*f(['"])[^'"]*\{str\(e\)[^'"]*\1\)""",
)

# Matches: 'exception_message': 'Unable to process the request. Please verify the submitted data and try again.'  or any other key exposing str(e)
PATTERN_ANY_KEY_STR_E = re.compile(
    r"""(['"][a-z_]*['"])\s*:\s*str\(e\)""",
    re.IGNORECASE,
)

# Matches f-string values for any key exposing str(e)
PATTERN_ANY_KEY_FSTR = re.compile(
    r"""(['"][a-z_]*['"])\s*:\s*f(['"])[^'"]*\{str\(e\)[^'"]*\2""",
)

# Matches print(...str(e)...) — convert to logger.error
PATTERN_PRINT_STR_E = re.compile(
    r"""print\(f(['"])[^'"]*\{str\(e\)[^'"]*\1\)""",
)

# Failed rows list append with str(e) — internal Excel row error (sanitize the displayed part)
PATTERN_FAILED_ROWS_APPEND = re.compile(
    r"""(failed_rows\.append\()f(['"])[^'"]*\{str\(e\)[^'"]*\2(\))""",
)


def ensure_logger(content: str, filepath: str) -> str:
    """Make sure the file has `import logging` and a module-level logger."""
    changed = False

    if 'import logging' not in content:
        # Insert after first import block line
        content = 'import logging\n' + content
        changed = True

    if 'logger = logging.getLogger(__name__)' not in content and \
       'logger = logging.getLogger(' not in content:
        # Add after the logging import line
        content = re.sub(
            r'(import logging\n)',
            r'\1logger = logging.getLogger(__name__)\n',
            content,
            count=1,
        )
        changed = True

    return content


def fix_content(content: str, filepath: str) -> tuple[str, int]:
    """Apply all fixes. Returns (new_content, num_changes)."""
    changes = 0
    orig = content

    # --- Response key patterns ---

    def replace_any_key_str_e(m):
        return f"{m.group(1)}: '{SAFE_MSG}'"

    def replace_any_key_fstr(m):
        return f"{m.group(1)}: '{SAFE_MSG}'"

    new = PATTERN_ANY_KEY_STR_E.sub(replace_any_key_str_e, content)
    if new != content:
        changes += len(PATTERN_ANY_KEY_STR_E.findall(content))
        content = new

    new = PATTERN_ANY_KEY_FSTR.sub(replace_any_key_fstr, content)
    if new != content:
        changes += len(PATTERN_ANY_KEY_FSTR.findall(content))
        content = new

    # --- messages.error ---
    def replace_messages_error(m):
        return f'messages.error(request, "{SAFE_MSG}")'

    new = PATTERN_MESSAGES_ERROR.sub(replace_messages_error, content)
    if new != content:
        changes += len(PATTERN_MESSAGES_ERROR.findall(content))
        content = new

    # --- failed_rows.append with str(e) ---
    def replace_failed_rows(m):
        return f'{m.group(1)}"Row processing failed. Please verify the row data and try again."{m.group(3)}'

    new = PATTERN_FAILED_ROWS_APPEND.sub(replace_failed_rows, content)
    if new != content:
        changes += len(PATTERN_FAILED_ROWS_APPEND.findall(content))
        content = new

    # --- Convert logger.error(f"...{str(e)}", exc_info=True) to logger.error ---
    def replace_print(m):
        # Extract the format string content to use as log message
        quote = m.group(1)
        inner = m.group(0)[len('print('):-1]  # the f"..." part
        return f'logger.error({inner}, exc_info=True)'

    new = PATTERN_PRINT_STR_E.sub(replace_print, content)
    if new != content:
        changes += len(PATTERN_PRINT_STR_E.findall(content))
        content = new

    if changes > 0:
        content = ensure_logger(content, filepath)

    return content, changes


def process_file(filepath: str) -> int:
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig strips BOM
            original = f.read()
    except Exception as ex:
        print(f"  [SKIP] Cannot read {filepath}: {ex}")
        return 0

    new_content, num_changes = fix_content(original, filepath)

    if num_changes == 0:
        return 0

    try:
        with open(filepath, 'w', encoding='utf-8') as f:  # always write clean utf-8 (no BOM)
            f.write(new_content)
        print(f"  [FIXED] {os.path.relpath(filepath, BASE_DIR)} — {num_changes} change(s)")
    except Exception as ex:
        print(f"  [ERROR] Cannot write {filepath}: {ex}")
        return 0

    return num_changes


def main():
    print(f"Base directory: {BASE_DIR}")
    print("Scanning Python files...\n")

    files = collect_python_files(BASE_DIR)
    print(f"Found {len(files)} Python files to inspect.\n")

    total_files_changed = 0
    total_changes = 0

    for fp in sorted(files):
        n = process_file(fp)
        if n:
            total_files_changed += 1
            total_changes += n

    print(f"\n{'='*60}")
    print(f"Done. {total_changes} disclosure(s) fixed across {total_files_changed} file(s).")


if __name__ == '__main__':
    main()
