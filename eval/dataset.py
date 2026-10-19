"""Labeled evaluation cases.

Each case is a tiny 'pull request' in which every line is new. Expected
issues are labeled by an ANCHOR (text that appears on the offending line)
instead of a line number, so editing the code can't silently break a label.
Clean cases contain no issues and measure false alarms.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedIssue:
    file: str
    anchor: str  # text that appears on the offending line
    label: str  # human-readable name of the issue
    category: str  # "security" or "bug"


@dataclass(frozen=True)
class EvalCase:
    id: str
    files: dict[str, str]
    expected: tuple[ExpectedIssue, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.expected


def resolve_line(case: EvalCase, issue: ExpectedIssue) -> int:
    """1-based line number of the first line containing the issue's anchor."""
    for number, line in enumerate(case.files[issue.file].splitlines(), start=1):
        if issue.anchor in line:
            return number
    raise ValueError(f"Anchor {issue.anchor!r} not found in {issue.file} (case {case.id})")


def _src(text: str) -> str:
    return text.lstrip("\n")


SQLI_FSTRING = _src('''
import sqlite3


def find_user(name):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute(f"SELECT id, email FROM users WHERE name = '{name}'")
    row = cur.fetchone()
    conn.close()
    return row
''')

HARDCODED_KEY = _src('''
import requests

API_KEY = "prod-key-1234567890abcdef"


def fetch_orders(customer_id):
    headers = {"Authorization": "Bearer " + API_KEY}
    url = f"https://api.example.com/customers/{customer_id}/orders"
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()
''')

COMMAND_INJECTION = _src('''
import os


def backup_directory(path, dest):
    command = "tar -czf " + dest + " " + path
    os.system(command)
    return dest
''')

UNSAFE_PICKLE = _src('''
import pickle


def load_session(raw_bytes):
    session = pickle.loads(raw_bytes)
    return session.get("user_id")
''')

PATH_TRAVERSAL = _src('''
import os

UPLOAD_DIR = "/srv/uploads"


def read_upload(filename):
    full_path = os.path.join(UPLOAD_DIR, filename)
    with open(full_path, "rb") as handle:
        return handle.read()
''')

WEAK_HASH = _src('''
import hashlib


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def check_password(password, stored_hash):
    return hash_password(password) == stored_hash
''')

TLS_OFF = _src('''
import requests


def download(url):
    response = requests.get(url, verify=False, timeout=30)
    return response.content
''')

DIV_ZERO = _src('''
def average(values):
    total = sum(values)
    return total / len(values)


def describe(values):
    return {"average": average(values), "count": len(values)}
''')

MUTABLE_DEFAULT = _src('''
def add_item(item, cart=[]):
    cart.append(item)
    return cart
''')

OFF_BY_ONE = _src('''
def last_items(items, count):
    result = []
    for i in range(len(items) - count, len(items) + 1):
        result.append(items[i])
    return result
''')

CLEAN_REPO = _src('''
import sqlite3
from contextlib import closing


def find_user(name: str):
    """Return the (id, email) row for a user, or None."""
    with closing(sqlite3.connect("app.db")) as conn:
        cur = conn.execute("SELECT id, email FROM users WHERE name = ?", (name,))
        return cur.fetchone()
''')

CLEAN_MATH = _src('''
def average(values: list[float]) -> float:
    """Return the mean of a non-empty list."""
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)


def clamp(value: float, low: float, high: float) -> float:
    """Limit value to the range [low, high]."""
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))
''')


CASES: list[EvalCase] = [
    EvalCase(
        "sqli_fstring", {"app/users.py": SQLI_FSTRING},
        (ExpectedIssue("app/users.py", 'cur.execute(f"SELECT',
                       "SQL injection via f-string", "security"),),
    ),
    EvalCase(
        "hardcoded_api_key", {"app/client.py": HARDCODED_KEY},
        (ExpectedIssue("app/client.py", 'API_KEY = "prod-key',
                       "Hardcoded API key", "security"),),
    ),
    EvalCase(
        "command_injection", {"app/backup.py": COMMAND_INJECTION},
        (ExpectedIssue("app/backup.py", "os.system(command)",
                       "Shell command injection", "security"),),
    ),
    EvalCase(
        "unsafe_pickle", {"app/session.py": UNSAFE_PICKLE},
        (ExpectedIssue("app/session.py", "pickle.loads(raw_bytes)",
                       "Unsafe pickle deserialization", "security"),),
    ),
    EvalCase(
        "path_traversal", {"app/files.py": PATH_TRAVERSAL},
        (ExpectedIssue("app/files.py", "full_path = os.path.join(UPLOAD_DIR, filename)",
                       "Path traversal", "security"),),
    ),
    EvalCase(
        "weak_password_hash", {"app/auth.py": WEAK_HASH},
        (ExpectedIssue("app/auth.py", "hashlib.md5(",
                       "Weak hash (MD5) for passwords", "security"),),
    ),
    EvalCase(
        "tls_verification_off", {"app/http_utils.py": TLS_OFF},
        (ExpectedIssue("app/http_utils.py", "verify=False",
                       "TLS verification disabled", "security"),),
    ),
    EvalCase(
        "division_by_zero", {"app/stats.py": DIV_ZERO},
        (ExpectedIssue("app/stats.py", "return total / len(values)",
                       "Division by zero on empty input", "bug"),),
    ),
    EvalCase(
        "mutable_default_argument", {"app/cart.py": MUTABLE_DEFAULT},
        (ExpectedIssue("app/cart.py", "def add_item(item, cart=[])",
                       "Mutable default argument", "bug"),),
    ),
    EvalCase(
        "off_by_one_range", {"app/pager.py": OFF_BY_ONE},
        (ExpectedIssue("app/pager.py", "range(len(items) - count, len(items) + 1)",
                       "Off-by-one causes IndexError", "bug"),),
    ),
    EvalCase("clean_repository_code", {"app/repo.py": CLEAN_REPO}),
    EvalCase("clean_math_helpers", {"app/mathutils.py": CLEAN_MATH}),
]