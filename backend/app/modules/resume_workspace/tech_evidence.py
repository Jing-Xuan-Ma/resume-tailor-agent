"""Phase 2-pre: extract objective technology-usage evidence from a code repo.

Zero-fabrication contract (see 0.1 in the execution plan): every entry must cite
a real file/dependency that exists on disk, and must never contain a
performance/quality judgment or number — those can only come from DEVLOG.md
evidence files or the user directly. Entries that fail either check are
rejected, never silently rewritten.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.core.llm_client import get_chat_openai

_MAX_README_CHARS = 6000
_MAX_TREE_LINES = 400
_MAX_DIGEST_FILES = 60
_MAX_IMPORTS_PER_FILE = 20

_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".next",
    "data", "artifacts", ".pytest_cache", "egg-info",
}

# Catches numbers/perf-quality language the LLM might slip in despite the
# system prompt — a code-level backstop, not just prompt-level trust.
_QUANT_PATTERN = re.compile(
    r"\d+\s*%|\d+\s*[xX]\b|\bfaster\b|\bslower\b|\bimprove[ds]?\b|\boptimiz\w*\b|"
    r"\befficient\w*\b|\brobust\w*\b|提升|加快|减少了|优化|倍|速度|性能",
    re.IGNORECASE,
)

_CORE_FILE_GLOBS = [
    "backend/app/main.py",
    "backend/app/modules/*/router.py",
    "backend/app/modules/*/service.py",
    "backend/app/modules/*/agent_loop.py",
    "backend/app/modules/*/agent_tools.py",
    "backend/app/core/*.py",
    "extensions/*/background.js",
    "extensions/*/content/*.js",
    "frontend/app/**/page.tsx",
]

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"(?:import .* from|require\()\s*['\"]([^'\"]+)['\"]")

_EXTRACT_SYSTEM_PROMPT = """You extract OBJECTIVE technology-usage facts from a codebase \
for a resume evidence table.

STRICT RULES:
1. Every entry must cite a real file path or dependency name that appears verbatim in the
   scan data given to you. Never invent a file or dependency.
2. For any entry citing a source file (.py/.ts/.tsx/.js) that appears in the "Import digest"
   section, the skill you name MUST correspond to one of the actual import tokens listed for
   THAT EXACT file. Do not cite a file just because it seems thematically related — if the
   import digest line for that file doesn't contain the technology, pick a different file
   that does, or omit the entry. Do NOT infer usage from the README's tech-stack table alone;
   the README is background context only, not evidence.
3. Only state WHAT technology/library/pattern is used and WHERE — never judge quality
   ("well-designed", "efficient", "robust", "clean").
4. NEVER include any number, percentage, "faster/slower", "improved", "reduced by", or any
   performance/quality claim. Those must come from separately verified benchmark logs, not
   from reading code.
5. If you are not confident a fact is directly verifiable from the given scan data, omit it
   rather than guess.
6. Output ONLY a JSON array, nothing else. Each item:
   {"skill": str, "evidence_file": str, "evidence_description": str}
   - evidence_file must be copied verbatim from the scan data (a listed file path from the
     import digest / directory tree, or a dependency name).
   - evidence_description is one factual sentence, no adjectives about quality/performance.
"""


_CONFIG_FILE_NAMES = {
    "readme.md", "pyproject.toml", "package.json", "tsconfig.json",
    "tailwind.config.ts", "next.config.mjs", "postcss.config.mjs",
    "manifest.json", "docker-compose.yml", "dockerfile",
}


@dataclass
class ScanBundle:
    repo_path: Path
    readme_excerpt: str
    python_deps: list[str]
    node_deps: list[str]
    directory_tree: str
    import_digest: str
    file_imports: dict[str, list[str]]


@dataclass
class VerifiedEntry:
    skill: str
    evidence_file: str
    evidence_description: str
    verified: bool
    reject_reason: str | None = None


def _strip_version(spec: str) -> str:
    return re.split(r"[><=\[; ]", spec, maxsplit=1)[0].strip()


def _read_readme(repo_path: Path) -> str:
    for name in ("README.md", "readme.md"):
        p = repo_path / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:_MAX_README_CHARS]
    return ""


def _parse_python_deps(repo_path: Path) -> list[str]:
    deps: list[str] = []
    for pyproject in repo_path.rglob("pyproject.toml"):
        if any(skip in pyproject.parts for skip in _SKIP_DIRS):
            continue
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        proj = data.get("project", {})
        deps.extend(_strip_version(d) for d in proj.get("dependencies", []))
        for group in proj.get("optional-dependencies", {}).values():
            deps.extend(_strip_version(d) for d in group)
    return sorted(set(deps))


def _parse_node_deps(repo_path: Path) -> list[str]:
    deps: list[str] = []
    for pkg in repo_path.rglob("package.json"):
        if any(skip in pkg.parts for skip in _SKIP_DIRS):
            continue
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        deps.extend(data.get("dependencies", {}).keys())
        deps.extend(data.get("devDependencies", {}).keys())
    return sorted(set(deps))


def _directory_tree(repo_path: Path) -> str:
    lines: list[str] = []

    def walk(path: Path, depth: int, prefix: str) -> None:
        if depth > 3 or len(lines) >= _MAX_TREE_LINES:
            return
        try:
            entries = sorted(
                (e for e in path.iterdir()
                 if e.name not in _SKIP_DIRS and not e.name.startswith(".")),
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except OSError:
            return
        for entry in entries:
            lines.append(f"{prefix}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                walk(entry, depth + 1, prefix + "  ")

    walk(repo_path, 0, "")
    return "\n".join(lines[:_MAX_TREE_LINES])


def _import_digest(repo_path: Path) -> tuple[str, dict[str, list[str]]]:
    lines: list[str] = []
    file_imports: dict[str, list[str]] = {}
    seen_files = 0
    for pattern in _CORE_FILE_GLOBS:
        if seen_files >= _MAX_DIGEST_FILES:
            break
        for f in sorted(repo_path.glob(pattern)):
            if seen_files >= _MAX_DIGEST_FILES:
                break
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(f.relative_to(repo_path))
            if f.suffix == ".py":
                imports = sorted(set(_IMPORT_RE.findall(text)))
            else:
                imports = sorted(set(_JS_IMPORT_RE.findall(text)))
            if imports:
                lines.append(f"{rel}: imports {', '.join(imports[:_MAX_IMPORTS_PER_FILE])}")
                file_imports[rel] = imports[:_MAX_IMPORTS_PER_FILE]
            seen_files += 1
    return "\n".join(lines), file_imports


def scan_repo(repo_path: Path) -> ScanBundle:
    digest_text, file_imports = _import_digest(repo_path)
    return ScanBundle(
        repo_path=repo_path,
        readme_excerpt=_read_readme(repo_path),
        python_deps=_parse_python_deps(repo_path),
        node_deps=_parse_node_deps(repo_path),
        directory_tree=_directory_tree(repo_path),
        import_digest=digest_text,
        file_imports=file_imports,
    )


def _parse_json_array(text: str) -> list[dict[str, str]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    required_keys = {"skill", "evidence_file", "evidence_description"}
    for item in data:
        if isinstance(item, dict) and required_keys <= item.keys():
            out.append({
                "skill": str(item["skill"]).strip(),
                "evidence_file": str(item["evidence_file"]).strip(),
                "evidence_description": str(item["evidence_description"]).strip(),
            })
    return out


def extract_tech_evidence(bundle: ScanBundle, *, max_items: int = 25) -> list[dict[str, str]]:
    # Reasoning models (e.g. glm-5.2) can spend the whole token budget on
    # internal reasoning before any output — give this call headroom so a
    # long scan digest doesn't silently truncate to an empty response.
    llm = get_chat_openai(temperature=0.0, max_tokens=8000)
    user_prompt = f"""README excerpt:
{bundle.readme_excerpt}

Python dependencies: {', '.join(bundle.python_deps) or '(none found)'}
Node dependencies: {', '.join(bundle.node_deps) or '(none found)'}

Directory tree:
{bundle.directory_tree}

Import digest (file: what it imports):
{bundle.import_digest}

Produce up to {max_items} technical evidence entries as a JSON array per the system rules.
Output JSON only."""
    response = llm.invoke([
        ("system", _EXTRACT_SYSTEM_PROMPT),
        ("human", user_prompt),
    ])
    return _parse_json_array(response.content)


def _normalize(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _skill_matches_imports(skill: str, imports: list[str]) -> bool:
    """Require the cited file's actual scanned imports to relate to the claimed skill.

    Pure substring match on normalized tokens — no LLM judgment call here, so a
    misattributed file (real path, wrong technology) gets caught mechanically
    instead of trusted on the model's word.
    """
    skill_tokens = [_normalize(w) for w in re.split(r"[\s/,_-]+", skill) if len(w) > 2]
    import_norms = [_normalize(imp) for imp in imports]
    for st in skill_tokens:
        for imp in import_norms:
            if st and imp and (st in imp or imp in st):
                return True
    return False


def verify_entries(bundle: ScanBundle, entries: list[dict[str, str]]) -> list[VerifiedEntry]:
    """Mechanical anti-hallucination gate — never trust the LLM's citation alone.

    Three independent checks, any failure rejects the entry outright (fail
    closed, no silent rewriting):
      1. No quantitative/performance language (0.1 zero-fabrication rule).
      2. Cited file/dependency must actually exist in the repo scan data.
      3. If the citation is a scanned source file, the claimed skill must
         correlate with that file's *actual* scanned imports — not just any
         file that exists somewhere in the repo (catches file-swap
         hallucinations like citing agent_loop.py for a langgraph import that
         really lives in agent.py).
    """
    known_deps = set(bundle.python_deps) | set(bundle.node_deps)
    repo_resolved = bundle.repo_path.resolve()
    out: list[VerifiedEntry] = []
    for e in entries:
        skill, ev_file, desc = e["skill"], e["evidence_file"], e["evidence_description"]
        if _QUANT_PATTERN.search(desc) or _QUANT_PATTERN.search(skill):
            out.append(VerifiedEntry(skill, ev_file, desc, False,
                                      "包含疑似量化/性能措辞,按零编造规则拒绝"))
            continue

        dep_match = ev_file in known_deps
        if dep_match:
            out.append(VerifiedEntry(skill, ev_file, desc, True, None))
            continue

        basename = Path(ev_file).name.lower()
        if basename in _CONFIG_FILE_NAMES:
            file_path = (bundle.repo_path / ev_file).resolve()
            if str(file_path).startswith(str(repo_resolved)) and file_path.exists():
                out.append(VerifiedEntry(skill, ev_file, desc, True, None))
            else:
                out.append(VerifiedEntry(skill, ev_file, desc, False,
                                          f"引用的配置文件 '{ev_file}' 不存在,拒绝"))
            continue

        digest_imports = bundle.file_imports.get(ev_file)
        if digest_imports is None:
            out.append(VerifiedEntry(skill, ev_file, desc, False,
                                      f"引用出处 '{ev_file}' 不在已扫描的核心文件/依赖清单中,拒绝"))
            continue
        if not _skill_matches_imports(skill, digest_imports):
            imports_str = ", ".join(digest_imports)
            reason = (
                f"'{ev_file}' 存在,但其实际 import 列表({imports_str}) "
                f"未检测到与技能 '{skill}' 相关的依据,可能是文件张冠李戴,拒绝"
            )
            out.append(VerifiedEntry(skill, ev_file, desc, False, reason))
            continue
        out.append(VerifiedEntry(skill, ev_file, desc, True, None))
    return out


def run_tech_evidence_scan(repo_path: Path, *, max_items: int = 25) -> list[VerifiedEntry]:
    bundle = scan_repo(repo_path)
    raw_entries = extract_tech_evidence(bundle, max_items=max_items)
    return verify_entries(bundle, raw_entries)
