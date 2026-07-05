from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"(?i)\b(cookie|set-cookie|authorization|bearer|token|password|secret|api[_-]?key)\b\s*[:=]"),
    re.compile(r"(?i)\"(cookie|authorization|token|password|secret|api_key)\"\s*:"),
]

EXPRESSION_PATTERNS = [
    re.compile(
        r"\b(rank|ts_rank|ts_corr|ts_mean|ts_std_dev|trade_when|group_rank|group_neutralize|decay_linear|scale|winsorize)\s*\(",
        re.IGNORECASE,
    ),
    re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*[+\-*/]\s*[a-zA-Z_][a-zA-Z0-9_]*"),
]

RAW_PAYLOAD_PATTERNS = [
    re.compile(r"(?i)\"raw\"\s*:"),
    re.compile(r"(?i)\"account(_id)?\"\s*:"),
    re.compile(r"(?i)\"platform_export\"\s*:"),
]


@dataclass(frozen=True)
class PrivacyFinding:
    path: str
    line: int
    kind: str
    snippet: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def redact_text(text: str, max_chars: int = 420) -> str:
    cleaned = re.sub(r"(?is)<script.*?</script>", " ", text)
    cleaned = re.sub(r"(?is)<style.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\b[\w.\-]+@[\w.\-]+\.\w+\b", "[email-redacted]", cleaned)
    cleaned = re.sub(r"(?i)(cookie|authorization|token|password|secret|api[_-]?key)\s*[:=]\s*\S+", r"\1=[redacted]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def looks_like_complete_expression(text: str) -> bool:
    if not text:
        return False
    function_hits = sum(1 for pattern in EXPRESSION_PATTERNS[:1] if pattern.search(text))
    bracket_depth = text.count("(") >= 2 and text.count(")") >= 2
    operator_mix = bool(re.search(r"[+\-*/]", text))
    return function_hits > 0 and (bracket_depth or operator_mix)


def scan_text(text: str, *, path: str = "<memory>", max_quote_chars: int = 900) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    quote_run = 0
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        snippet = stripped[:180]
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(PrivacyFinding(path, index, "secret_or_credential", snippet))
                break
        for pattern in RAW_PAYLOAD_PATTERNS:
            if pattern.search(line):
                findings.append(PrivacyFinding(path, index, "raw_platform_payload", snippet))
                break
        if looks_like_complete_expression(line):
            findings.append(PrivacyFinding(path, index, "possible_alpha_expression", snippet))
        if len(stripped) > max_quote_chars:
            findings.append(PrivacyFinding(path, index, "long_forum_quote", snippet))
        if stripped.startswith(">"):
            quote_run += len(stripped)
            if quote_run > max_quote_chars:
                findings.append(PrivacyFinding(path, index, "long_forum_quote", snippet))
        else:
            quote_run = 0
    return findings


def scan_file(path: Path) -> list[PrivacyFinding]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [PrivacyFinding(str(path), 0, "binary_or_non_utf8", "non-utf8 file")]
    return scan_text(text, path=str(path))


def scan_tree(root: Path) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for path in root.rglob("*"):
        if path.is_file():
            findings.extend(scan_file(path))
    return findings


class PrivacyScanError(RuntimeError):
    def __init__(self, findings: list[PrivacyFinding]) -> None:
        self.findings = findings
        super().__init__(f"privacy scan failed with {len(findings)} finding(s)")
