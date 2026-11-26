#!/usr/bin/env python3
"""
Universal Enterprise Project Bootstrapper (init_project.py)
============================================================
Zero-dependency, production-grade scaffolding tool to clone and
customize the Universal Master Governance Framework (GEMINI.md,
Enterprise_Blueprint.md, and Blueprint_Debug_Log.md) for any new
enterprise project in seconds.

Runtime: Python 3.13+ Standard Library Only (pathlib, re, shutil, subprocess, sys, datetime, argparse)
Adheres strictly to GEMINI.md zero-bloat and zero-hallucination standards.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import keyword
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Final

# Canonical validation patterns
PROJECT_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9-]*[a-z0-9]$"
PACKAGE_NAME_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*$"
MCP_PREFIX_PATTERN: Final[str] = r"^[a-z][a-z0-9_-]*$"

UNREPLACED_TOKEN_PATTERN: Final[str] = r"\{\{[A-Z0-9_]+\}\}"
RESIDUAL_PROHIBITED_TOKENS: Final[tuple[str, ...]] = (
    "finops-sre-sentinel",
    "finops_sre_sentinel",
    "sentinel://",
)

# Deployment Target Profiles
DEPLOY_TARGET_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "aws-free-tier": {
        "label": "AWS Free Tier (t3.micro / t4g.small)",
        "guide": "AWS_Deployment_Guide.md",
        "max_memory_mb": 512,
        "memory_watch_mb": 450,
        "max_output_tokens": 4000,
    },
    "azure-free-tier": {
        "label": "Azure Free Tier (App Service F1 / Container Apps)",
        "guide": "Azure_Deployment_Guide.md",
        "max_memory_mb": 1024,
        "memory_watch_mb": 850,
        "max_output_tokens": 4000,
    },
    "standard-cloud": {
        "label": "Standard Enterprise Cloud (AWS / Azure / Kubernetes)",
        "guide": "Cloud_Deployment_Guide.md",
        "max_memory_mb": 2048,
        "memory_watch_mb": 1750,
        "max_output_tokens": 8192,
    },
}

# AI Orchestration Profiles
ORCHESTRATION_PROFILES: Final[dict[str, str]] = {
    "orchestrated": (
        "Permits any multi-agent, RAG, or MCP orchestration framework (including LangChain, LangGraph, LlamaIndex, "
        "CrewAI, AutoGen, Google ADK, or direct typed SDKs) provided that all inter-agent messages, retrieval chunks, "
        "state schemas, and data contracts strictly enforce Pydantic v2 validation (extra='forbid', frozen=True) "
        "and all external actions/tools are encapsulated inside deterministic GuardrailEngine wrappers."
    ),
    "rag-mcp": (
        "Optimized for Retrieval-Augmented Generation (RAG) and Model Context Protocol (MCP) servers using LangChain, "
        "LangGraph, LlamaIndex, CrewAI, AutoGen, or direct SDKs with vector stores (pgvector, FAISS, Chroma). "
        "Enforces bounded chunk ingestion (< 4,000 tokens/batch), citation/grounding verification, Pydantic v2 data "
        "contracts (extra='forbid', frozen=True), and deterministic GuardrailEngine tool execution."
    ),
    "zero-bloat": (
        "Strictly forbid heavy AI orchestrator frameworks (LangChain, LlamaIndex, crewAI, AutoGen). "
        "All agent reasoning, tool calling, and workflow dispatching must be executed via direct, typed SDK/REST calls."
    ),
}

GITIGNORE_TEMPLATE: Final[str] = """# ==============================================================================
# Baseline Git Ignore Configuration for Autonomous AI Coding Workflows
# ==============================================================================

# Python Runtime, Cache & Virtual Environments
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
env/
# Secrets & Environment Configurations
.env
.env.*
!.env.example
*.pem
*.key

# Packaging & Build Distribution
dist/
build/
*.egg-info/
*.egg

# Testing, Static Typing & Linting Caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Persistence, Audit Ledgers & Runtime State
data/
*.db
*.db-wal
*.db-shm
audit_logs/
*.log

# OS & IDE Metadata
.DS_Store
Thumbs.db
.idea/
.vscode/
*.swp
*.swo
"""


@dataclass(frozen=True)
class ProjectConfig:
    """Immutable project configuration parameters."""

    project_id: str
    project_title: str
    package_name: str
    cli_entrypoint: str
    mcp_prefix: str
    db_prefix: str
    env_prefix: str
    service_port: int
    primary_model: str
    webhook_secret: str
    target_dir: Path
    dry_run: bool
    force: bool
    git_init: bool
    scaffold_dirs: bool
    deploy_target: str
    deploy_target_label: str
    orchestrator: str
    orchestration_policy: str
    max_memory_mb: int
    memory_watch_mb: int
    max_output_tokens: int
    cloud_deployment_guide: str


def validate_project_id(project_id: str) -> None:
    """Validate project ID against kebab-case standards."""
    if not (3 <= len(project_id) <= 64):
        raise ValueError(f"Project ID must be between 3 and 64 characters (got {len(project_id)}).")
    if not re.match(PROJECT_ID_PATTERN, project_id):
        raise ValueError(
            f"Invalid Project ID '{project_id}'. Must be lowercase kebab-case (e.g., 'healthcare-claims-sentinel')."
        )


def validate_package_name(package_name: str) -> None:
    """Validate Python package name against PEP 8 standards."""
    if not re.match(PACKAGE_NAME_PATTERN, package_name):
        raise ValueError(
            f"Invalid Python package name '{package_name}'. Must be lowercase snake_case (e.g., 'healthcare_claims_sentinel')."
        )
    if keyword.iskeyword(package_name):
        raise ValueError(f"Package name '{package_name}' is a reserved Python keyword.")


def validate_port(port: int) -> None:
    """Validate network port range."""
    if not (1024 <= port <= 65535):
        raise ValueError(f"Port must be within non-privileged user range 1024-65535 (got {port}).")


def validate_mcp_prefix(prefix: str) -> None:
    """Validate MCP URI prefix."""
    clean = prefix.rstrip(":/")
    if not re.match(MCP_PREFIX_PATTERN, clean):
        raise ValueError(f"Invalid MCP prefix '{prefix}'. Must be alphanumeric with hyphens/underscores.")


def derive_defaults(project_id: str) -> tuple[str, str, str, str, str, str]:
    """Auto-derive smart defaults from a kebab-case project identifier."""
    words: list[str] = []
    for w in project_id.split("-"):
        if not w:
            continue
        if w.lower() in ("ai", "sre", "mcp", "api", "llm", "iam"):
            words.append(w.upper())
        else:
            words.append(w.capitalize())
    project_title = " ".join(words)

    package_name = re.sub(r"[^a-z0-9_]", "_", project_id.lower()).replace("-", "_").strip("_")
    cli_entrypoint = project_id.lower()

    tokens = [t for t in project_id.split("-") if t]
    mcp_prefix = tokens[0].lower() if tokens else "sentinel"
    db_prefix = mcp_prefix

    env_prefix = re.sub(r"[^A-Z0-9_]", "_", project_id.upper()).replace("-", "_").strip("_")

    return project_title, package_name, cli_entrypoint, mcp_prefix, db_prefix, env_prefix


def prompt_user(prompt_text: str, default: str) -> str:
    """Prompt the user interactively with a fallback default."""
    try:
        user_input = input(f"{prompt_text} [{default}]: ").strip()
        return user_input if user_input else default
    except (EOFError, KeyboardInterrupt):
        print("\n[!] Setup cancelled by user.")
        sys.exit(1)


def parse_arguments(repo_root: Path) -> ProjectConfig:
    """Parse CLI arguments or fallback to interactive mode."""
    parser = argparse.ArgumentParser(
        description="Scaffold and clone the Universal Master Governance Framework for a new enterprise project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project-id", type=str, help="Kebab-case project ID (e.g. 'healthcare-claims-sentinel')")
    parser.add_argument("--package-name", type=str, help="Python package name (e.g. 'healthcare_claims_sentinel')")
    parser.add_argument("--cli-entrypoint", type=str, help="CLI command name (e.g. 'healthcare-claims-sentinel')")
    parser.add_argument("--mcp-prefix", type=str, help="MCP protocol URI scheme prefix (e.g. 'healthcare')")
    parser.add_argument("--port", type=int, default=8080, help="Default service port (default: 8080)")
    parser.add_argument(
        "--primary-model", type=str, default="gemini-3.8-flash-high", help="Primary LLM engine model identifier"
    )
    parser.add_argument(
        "--deploy-target",
        type=str,
        choices=list(DEPLOY_TARGET_PROFILES.keys()),
        default=None,
        help="Deployment environment profile (choices: standard-cloud, aws-free-tier, azure-free-tier; default: standard-cloud)",
    )
    parser.add_argument(
        "--orchestrator",
        type=str,
        choices=list(ORCHESTRATION_PROFILES.keys()),
        default="orchestrated",
        help="AI orchestration architecture (choices: orchestrated, rag-mcp, zero-bloat; default: orchestrated)",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=".",
        help="Destination directory for cloned project (default: current directory)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview all transformations and replacements without writing to disk"
    )
    parser.add_argument("--force", action="store_true", help="Allow in-place modification of existing repository")
    parser.add_argument(
        "--git-init",
        action="store_true",
        help="Initialize a git repository (branch: main) with baseline .gitignore and stage initial files",
    )
    parser.add_argument(
        "--scaffold-dirs",
        action="store_true",
        help="Scaffold starter package and testing directories (src/<pkg>/, tests/, docs/, prompts/modules/)",
    )

    args = parser.parse_args()

    # Determine interactive vs non-interactive
    project_id = args.project_id
    interactive_mode = not project_id and sys.stdin.isatty()

    if not project_id:
        if not sys.stdin.isatty():
            parser.error("Non-interactive terminal requires --project-id flag.")
        print("\n=================================================================")
        print("  Enterprise Project Scaffolding & Governance Bootstrapper")
        print("=================================================================\n")
        project_id = prompt_user("Enter Project Identifier (kebab-case)", "custom-ai-sentinel")

    project_id = project_id.strip().lower()
    validate_project_id(project_id)

    default_title, default_pkg, default_cli, default_mcp, default_db, default_env = derive_defaults(project_id)

    # Resolve package name
    pkg_name = args.package_name
    if not pkg_name:
        if interactive_mode:
            pkg_name = prompt_user("Enter Python Package Name (snake_case)", default_pkg)
        else:
            pkg_name = default_pkg
    validate_package_name(pkg_name)

    # Resolve CLI entrypoint
    cli_cmd = args.cli_entrypoint or (
        prompt_user("Enter CLI Console Entrypoint", default_cli) if interactive_mode else default_cli
    )

    # Resolve MCP prefix
    mcp_prefix = args.mcp_prefix or (
        prompt_user("Enter MCP URI Scheme Prefix", default_mcp) if interactive_mode else default_mcp
    )
    mcp_prefix = mcp_prefix.rstrip(":/").lower()
    validate_mcp_prefix(mcp_prefix)

    port = args.port
    validate_port(port)

    # Target directory resolution
    target_str = args.target_dir
    if interactive_mode and target_str == ".":
        target_str = prompt_user("Enter Target Destination Directory", f"../{project_id}")

    target_path = Path(target_str).resolve()

    # Git init resolution
    git_init = args.git_init
    if not git_init and interactive_mode:
        git_choice = prompt_user("Initialize Git repository (branch: main) with baseline .gitignore? (y/n)", "y").lower()
        git_init = git_choice in ("y", "yes")

    # Directory scaffolding resolution
    scaffold_dirs = args.scaffold_dirs
    if not scaffold_dirs and interactive_mode:
        scaffold_choice = prompt_user(
            f"Scaffold starter directory skeleton (src/{pkg_name}/, tests/, docs/, prompts/modules/)? (y/n)", "y"
        ).lower()
        scaffold_dirs = scaffold_choice in ("y", "yes")

    # Deployment target profile resolution
    deploy_target = args.deploy_target
    if not deploy_target:
        if interactive_mode:
            print("\nSelect Deployment Target Profile:")
            print("  1) standard-cloud  - Standard Enterprise Cloud (2048MB RAM, 8192 tokens) [Default]")
            print("  2) aws-free-tier   - AWS Free Tier t3.micro/t4g.small (512MB RAM, 4000 tokens)")
            print("  3) azure-free-tier - Azure Free Tier App Service F1/Container Apps (1024MB RAM, 4000 tokens)")
            choice = prompt_user("Enter choice (standard-cloud/aws-free-tier/azure-free-tier)", "standard-cloud").strip().lower()
            deploy_target = choice if choice in DEPLOY_TARGET_PROFILES else "standard-cloud"
        else:
            deploy_target = "standard-cloud"

    # AI orchestration mode resolution
    orchestrator = args.orchestrator
    if interactive_mode and not any(arg.startswith("--orchestrator") for arg in sys.argv):
        print("\nSelect AI Orchestration Standard:")
        print("  1) orchestrated - Universal Multi-Agent / RAG / MCP (LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, direct SDKs) [Default]")
        print("  2) rag-mcp      - Optimized for RAG & MCP servers (pgvector, FAISS, Chroma, citations, bounded chunks < 4000 tokens)")
        print("  3) zero-bloat   - Zero-Bloat Direct SDK (Strictly forbid heavy orchestrators; 512MB RAM direct-SDK)")
        choice = prompt_user("Enter choice (orchestrated/rag-mcp/zero-bloat)", "orchestrated").strip().lower()
        orchestrator = choice if choice in ORCHESTRATION_PROFILES else "orchestrated"
    elif not orchestrator:
        orchestrator = "orchestrated"

    target_profile = DEPLOY_TARGET_PROFILES[deploy_target]
    orchestration_policy = ORCHESTRATION_PROFILES[orchestrator]

    webhook_secret = f"{default_env}_WEBHOOK_SECRET"

    return ProjectConfig(
        project_id=project_id,
        project_title=default_title,
        package_name=pkg_name,
        cli_entrypoint=cli_cmd,
        mcp_prefix=mcp_prefix,
        db_prefix=default_db,
        env_prefix=default_env,
        service_port=port,
        primary_model=args.primary_model,
        webhook_secret=webhook_secret,
        target_dir=target_path,
        dry_run=args.dry_run,
        force=args.force,
        git_init=git_init,
        scaffold_dirs=scaffold_dirs,
        deploy_target=deploy_target,
        deploy_target_label=str(target_profile["label"]),
        orchestrator=orchestrator,
        orchestration_policy=str(orchestration_policy),
        max_memory_mb=int(target_profile["max_memory_mb"]),
        memory_watch_mb=int(target_profile["memory_watch_mb"]),
        max_output_tokens=int(target_profile["max_output_tokens"]),
        cloud_deployment_guide=str(target_profile["guide"]),
    )


def clone_governance_files(source_root: Path, target_dir: Path, dry_run: bool) -> list[str]:
    """Clone master governance documents and blueprint files to target directory."""
    actions: list[str] = []

    if source_root == target_dir:
        actions.append(f"Operating in-place on existing repository: {target_dir}")
        return actions

    actions.append(f"Cloning governance template suite into destination: {target_dir}")

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    core_files = [
        "GEMINI.md",
        "Enterprise_Blueprint.md",
        "Blueprint_Debug_Log.md",
        "AUDIT_REMEDIATION_LOG.md",
        "README.md",
        "init_project.py",
    ]
    if (source_root / "PROJECT_MAP.md").exists():
        core_files.append("PROJECT_MAP.md")
    if (source_root / ".gitignore").exists():
        core_files.append(".gitignore")
    if (source_root / "modular_prompt.md").exists():
        core_files.append("modular_prompt.md")

    for f_name in core_files:
        src = source_root / f_name
        dst = target_dir / f_name
        if src.exists():
            actions.append(f"Copy: {f_name} -> {dst}")
            if not dry_run:
                shutil.copy2(src, dst)

    return actions


def replace_placeholder_tokens(text: str, config: ProjectConfig) -> tuple[str, int]:
    """Replace universal {{...}} placeholder tokens with project-specific values."""
    replacements = 0

    token_map = [
        ("{{PROJECT_ID}}", config.project_id),
        ("{{PACKAGE_NAME}}", config.package_name),
        ("{{PROJECT_TITLE}}", config.project_title),
        ("{{MCP_URI_PREFIX}}", config.mcp_prefix),
        ("{{DB_PREFIX}}", config.db_prefix),
        ("{{ENV_PREFIX}}", config.env_prefix),
        ("{{DEPLOY_TARGET_LABEL}}", config.deploy_target_label),
        ("{{MAX_MEMORY_MB}}", str(config.max_memory_mb)),
        ("{{MEMORY_WATCH_MB}}", str(config.memory_watch_mb)),
        ("{{MAX_OUTPUT_TOKENS}}", str(config.max_output_tokens)),
        ("{{ORCHESTRATION_POLICY}}", config.orchestration_policy),
        ("{{CLOUD_DEPLOYMENT_GUIDE}}", config.cloud_deployment_guide),
    ]

    for token, val in token_map:
        if token in text:
            count = text.count(token)
            text = text.replace(token, val)
            replacements += count

    # Also handle legacy token variants if migrating from finops template
    legacy_pairs = [
        (r"\bSENTINEL_WEBHOOK_SECRET\b", config.webhook_secret),
        (r"sentinel://", f"{config.mcp_prefix}://"),
        (r"\bsentinel_ledger\.db\b", f"{config.db_prefix}_ledger.db"),
        (r"\bfinops-sre-sentinel\b", config.project_id),
        (r"\bfinops_sre_sentinel\b", config.package_name),
    ]
    for pattern, repl in legacy_pairs:
        text, count = re.subn(pattern, repl, text)
        replacements += count

    return text, replacements


def reconfigure_gemini_md(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reconfigure GEMINI.md project configuration and identifiers."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)

    if config.service_port != 8080:
        text, count = re.subn(r"Default Service Port:\s+\d+", f"Default Service Port:      {config.service_port}", text)
        replacements += count

    if config.primary_model != "gemini-3.8-flash-high":
        text, count = re.subn(r"default: gemini-3\.8-flash-high", f"default: {config.primary_model}", text)
        replacements += count

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements, f"{action_label} {file_path.name} ({replacements} replacements)", text


def reconfigure_blueprint_md(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reconfigure Enterprise_Blueprint.md, reset checklist boxes, and update paths."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)

    # Reset checklist checkboxes [x] -> [ ]
    text, checkbox_matches = re.subn(r"- \[x\]", "- [ ]", text)
    replacements += checkbox_matches

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return (
        replacements,
        f"{action_label} {file_path.name} ({replacements} replacements; {checkbox_matches} tasks reset)",
        text,
    )


def reconfigure_readme(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reconfigure README.md with new project details."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements, f"{action_label} {file_path.name} ({replacements} replacements)", text


def reconfigure_debug_log(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reset Section 2 incident log while permanently preserving Section 3 historical loopholes."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Locate Section 2 boundary
    sec2_header = "## 2. Structured Incident & Debugging Log"
    sec3_header = "## 3. Historical Architectural Delta & Forensic Loophole Registry"

    if sec2_header in text and sec3_header in text:
        before_sec2 = text.split(sec2_header)[0]
        after_sec3 = text.split(sec3_header)[1]

        clean_sec2_table = (
            f"{sec2_header}\n\n"
            "| Date/Phase | Module / File | Error / Symptom | Root Cause | Verified Fix & Regression Test |\n"
            "|---|---|---|---|---|\n"
            f"| {today_str} / Phase 0.0 (Project Initialized) | `GEMINI.md`, `Enterprise_Blueprint.md` | "
            f"Initialized project governance suite from universal template for `{config.project_id}`. | "
            "Fresh project initialization via `init_project.py`. | "
            "Master constitutional invariants and 12-phase roadmap seeded; ready for Phase 0.1 Forensic Audit. |\n\n"
            "---\n\n"
            f"{sec3_header}"
        )

        text = before_sec2 + clean_sec2_table + after_sec3

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements + 1, f"{action_label} {file_path.name} (Section 2 reset; Section 3 universal loopholes preserved)", text


def reconfigure_audit_remediation_log(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reset Section 2 feature/remediation log to a clean baseline initialization entry."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sec2_header = "## 2. Chronological Feature & Remediation Ledger"
    if sec2_header in text:
        before_sec2 = text.split(sec2_header)[0]
        clean_sec2_table = (
            f"{sec2_header}\n\n"
            "| Date / Version | Phase / Audit ID | Feature / Remediation Added | Files Modified | Verification Proof (Tests / CI / Commit) |\n"
            "|---|---|---|---|---|\n"
            f"| {today_str} / `v1.0.0` | Phase 0.0 (Project Initialized) | "
            f"Initialized project governance suite from universal template for `{config.project_id}`. | "
            "`GEMINI.md`, `Enterprise_Blueprint.md`, `README.md` | "
            "Master constitutional invariants, 12-phase roadmap, and remediation ledger seeded; ready for Phase 0.1 Forensic Audit. |\n"
        )
        text = before_sec2 + clean_sec2_table

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements + 1, f"{action_label} {file_path.name} (Section 2 reset to baseline initialization entry)", text


def reconfigure_project_map(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reconfigure PROJECT_MAP.md with new project details if present."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements, f"{action_label} {file_path.name} ({replacements} replacements)", text


def reconfigure_modular_prompt(file_path: Path, config: ProjectConfig, source_path: Path) -> tuple[int, str, str]:
    """Reconfigure modular_prompt.md with new project details if present."""
    read_path = source_path if source_path.exists() else file_path
    if not read_path.exists():
        return 0, f"File not found: {read_path}", ""

    text = read_path.read_text(encoding="utf-8")
    text, replacements = replace_placeholder_tokens(text, config)

    if not config.dry_run:
        file_path.write_text(text, encoding="utf-8")

    action_label = "[DRY-RUN] Previewed" if config.dry_run else "Reconfigured"
    return replacements, f"{action_label} {file_path.name} ({replacements} replacements)", text


def purge_old_audit_reports(target_dir: Path, dry_run: bool) -> list[str]:
    """Purge project-specific audit deliverables in the new target so Phase 0.1 starts clean."""
    reports_to_purge = [
        target_dir / "Blueprint_Repo_Baseline_AuditReport.md",
        target_dir / "Blueprint_Production_Readiness_Report.md",
    ]
    actions: list[str] = []
    for report in reports_to_purge:
        if report.exists():
            if dry_run:
                actions.append(f"[DRY-RUN] Would remove prior project audit report: {report.name}")
            else:
                report.unlink()
                actions.append(f"Removed prior project audit report: {report.name}")
    return actions


def scaffold_directory_skeleton(config: ProjectConfig) -> list[str]:
    """Scaffold starter package, test, documentation, and prompt directories."""
    actions: list[str] = []
    pkg_dir = config.target_dir / "src" / config.package_name
    pkg_init = pkg_dir / "__init__.py"
    tests_dir = config.target_dir / "tests"
    tests_init = tests_dir / "__init__.py"
    docs_dir = config.target_dir / "docs"
    prompts_dir = config.target_dir / "prompts" / "modules"

    project_map_file = config.target_dir / "PROJECT_MAP.md"
    project_map_content = f"""# Project Map — {config.project_title} (`{config.project_id}`)

> Compact repository index for targeted reads (< 60 lines).
> Runtime: Python 3.13+ | Architecture: Clean Modular Hexagonal

## Core Source Tree (`src/{config.package_name}/`)
- `config.py` - Pydantic settings, model identifiers, memory/token thresholds, secrets.
- `models/` - Pydantic v2 data contracts, ActionType Enum, telemetry, plans.
- `guardrails/` - Safety scoring, quarantine patterns, deterministic IAM/rollback synthesis.
- `heuristics/` - Offline deterministic rule engines, pricing catalog lookups.
- `reasoner/` - Gemini client (thinkingBudget, responseSchema), OpenRouter fallback.
- `ledger/` - SQLite WAL persistent audit store with per-operation FileLock.
- `mcp/` - Dual-transport MCP server (stdio JSON-RPC & Starlette SSE).
- `observability.py` - OpenTelemetry spans, metrics, and structured logging.
- `cli.py` - Click console entrypoint commands (`{config.project_id}`).

## Test Suite (`tests/`)
- `test_schemas.py` - Contract validation, ActionType enum allowlist tests.
- `test_heuristics.py` - Heuristic rule coverage, catalog fallback verification.
- `test_reasoner.py` - LLM reasoning, responseSchema sanitization, cascade tests.
- `test_mcp.py` - stdio and SSE transport protocols, 10MB limits, auth verification.
- `test_ledger.py` - SQLite WAL concurrency, MVCC read-bypass, migration tests.
- `test_phase9_hardening.py` - Cryptographic HMAC, anti-replay, Unicode normalization.

## Governance & Specifications
- `GEMINI.md` - Master constitution, security invariants, operational rules.
- `Enterprise_Blueprint.md` - 12-phase master engineering plan and active backlog.
- `Blueprint_Debug_Log.md` - Incident tracking and historical loophole registry.
- `README.md` - Root navigation hub, architecture summary, and operational manual.
"""
    scaffold_plan = [
        (pkg_dir, pkg_init, f'"""{config.project_title} package root."""\n\n__version__ = "0.1.0"\n'),
        (tests_dir, tests_init, f'"""Test suite for {config.project_title}."""\n'),
        (docs_dir, None, None),
        (prompts_dir, None, None),
        (config.target_dir, project_map_file, project_map_content),
    ]

    for d_path, f_path, content in scaffold_plan:
        rel_d = d_path.relative_to(config.target_dir)
        if config.dry_run:
            actions.append(f"[DRY-RUN] Would scaffold directory: {rel_d}/")
            if f_path is not None:
                rel_f = f_path.relative_to(config.target_dir)
                if not f_path.exists():
                    actions.append(f"[DRY-RUN] Would scaffold starter file: {rel_f}")
                else:
                    actions.append(f"[DRY-RUN] File already exists (will not overwrite): {rel_f}")
        else:
            d_path.mkdir(parents=True, exist_ok=True)
            actions.append(f"Scaffolded directory: {rel_d}/")
            if f_path is not None:
                rel_f = f_path.relative_to(config.target_dir)
                if not f_path.exists():
                    f_path.write_text(content or "", encoding="utf-8")
                    actions.append(f"Scaffolded starter file: {rel_f}")
                else:
                    actions.append(f"Retained existing file: {rel_f}")

    return actions


def initialize_git_repository(config: ProjectConfig) -> list[str]:
    """Initialize a git repository with baseline .gitignore and staged files."""
    actions: list[str] = []
    gitignore_path = config.target_dir / ".gitignore"

    # 1. Baseline .gitignore
    if config.dry_run:
        actions.append(f"[DRY-RUN] Would create baseline .gitignore: {gitignore_path.name}")
    else:
        if not gitignore_path.exists():
            gitignore_path.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
            actions.append(f"Created baseline .gitignore: {gitignore_path.name}")
        else:
            actions.append(f"Baseline .gitignore already present: {gitignore_path.name}")

    # 2. Check git binary availability
    git_bin = shutil.which("git")
    if not git_bin:
        actions.append("[!] WARNING: 'git' CLI executable not found on system PATH. Skipped repository init.")
        return actions

    # 3. Initialize Git repository & stage files
    if config.dry_run:
        actions.append(f"[DRY-RUN] Would initialize Git repository (branch: main) in: {config.target_dir}")
        actions.append("[DRY-RUN] Would stage initial governance files (git add .)")
        return actions

    try:
        git_dir = config.target_dir / ".git"
        if not git_dir.exists():
            init_cmd = [git_bin, "init", "-b", "main"]
            res = subprocess.run(init_cmd, cwd=config.target_dir, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                # Fallback for legacy git versions lacking -b
                subprocess.run([git_bin, "init"], cwd=config.target_dir, capture_output=True, text=True, check=False)
                subprocess.run([git_bin, "checkout", "-b", "main"], cwd=config.target_dir, capture_output=True, text=True, check=False)
            actions.append("Initialized Git repository on branch 'main'")
        else:
            actions.append("Existing Git repository detected; retaining active history")

        # 4. Stage files
        add_res = subprocess.run([git_bin, "add", "."], cwd=config.target_dir, capture_output=True, text=True, check=False)
        if add_res.returncode == 0:
            actions.append("Staged initial governance and configuration files (git add .)")
        else:
            actions.append(f"[!] Warning during 'git add .': {add_res.stderr.strip()}")
    except (subprocess.SubprocessError, OSError) as e:
        actions.append(f"[!] Warning: Git operation encountered an error ({e}); bootstrap completed with files in place.")

    return actions


def audit_generated_files(
    files_to_check: dict[str, str], config: ProjectConfig
) -> tuple[bool, list[str]]:
    """
    Audit generated content to guarantee zero unreplaced {{...}} placeholder tokens
    and zero residual legacy template identifiers.
    """
    findings: list[str] = []

    for file_name, content in files_to_check.items():
        lines = content.splitlines()
        for line_num, line in enumerate(lines, start=1):
            # 1. Check for unreplaced {{...}} placeholders
            unreplaced = re.findall(UNREPLACED_TOKEN_PATTERN, line)
            if unreplaced:
                snippet = line.strip()[:100]
                for tok in unreplaced:
                    findings.append(f"  [!] Unreplaced token '{tok}' in {file_name}:{line_num} -> {snippet}")

            # 2. Check for prohibited legacy template tokens (if new project ID)
            if config.project_id != "finops-sre-sentinel":
                for token in RESIDUAL_PROHIBITED_TOKENS:
                    if token in line:
                        snippet = line.strip()[:100]
                        findings.append(f"  [!] Residual template token '{token}' in {file_name}:{line_num} -> {snippet}")

    messages: list[str] = []
    if not findings:
        messages.append(f"[PASS] Zero unreplaced {{{{...}}}} placeholder tokens found across {len(files_to_check)} files.")
        messages.append(f"[PASS] Zero residual template strings found across {len(files_to_check)} files.")
        return True, messages

    fail_msgs = [f"[FAIL] Found {len(findings)} token/residual defect(s):"] + findings
    return False, fail_msgs


def main() -> None:
    """Execute the project bootstrapper."""
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent

    config = parse_arguments(repo_root)

    print("\n-----------------------------------------------------------------")
    print("  Bootstrapping Enterprise Project Governance Suite")
    print("-----------------------------------------------------------------")
    print(f"  Project Identifier:      {config.project_id}")
    print(f"  Project Title:           {config.project_title}")
    print(f"  Target Package Name:     {config.package_name}")
    print(f"  CLI Console Entrypoint:  {config.cli_entrypoint}")
    print(f"  MCP Protocol URI Prefix: {config.mcp_prefix}://")
    print(f"  Deployment Target:       {config.deploy_target} ({config.deploy_target_label})")
    print(f"  Deployment Guide:        docs/{config.cloud_deployment_guide}")
    print(f"  Container RAM Ceiling:   {config.max_memory_mb}MB (Watchdog: {config.memory_watch_mb}MB)")
    print(f"  Max Output Token Cap:    {config.max_output_tokens} tokens")
    print(f"  AI Orchestration Mode:   {config.orchestrator}")
    print(f"  Default Service Port:    {config.service_port}")
    print(f"  Primary LLM Engine:      {config.primary_model}")
    print(f"  Webhook Signing Secret:  {config.webhook_secret}")
    print(f"  Target Destination Path: {config.target_dir}")
    print(f"  Initialize Git Repo:     {'Yes (branch: main)' if config.git_init else 'No'}")
    print(f"  Scaffold Skeleton Dirs:  {'Yes (src/, tests/, docs/, prompts/)' if config.scaffold_dirs else 'No'}")
    print(f"  Execution Mode:          {'[DRY-RUN PREVIEW]' if config.dry_run else '[LIVE APPLICATION]'}")
    print("-----------------------------------------------------------------\n")

    # Safety check for in-place modification
    if config.target_dir == repo_root and not config.dry_run and not config.force:
        print("[!] ERROR: Target directory is the master template repository root.")
        print("    To modify the repository in-place, pass the --force flag.")
        sys.exit(1)

    # 1. Clone files if destination is different
    clone_actions = clone_governance_files(repo_root, config.target_dir, config.dry_run)
    for act in clone_actions:
        print(f"  [+] {act}")

    # 2. Reconfigure governance documents
    print("\n  Reconfiguring governance suite:")
    gemini_file = config.target_dir / "GEMINI.md"
    blueprint_file = config.target_dir / "Enterprise_Blueprint.md"
    readme_file = config.target_dir / "README.md"
    debug_log_file = config.target_dir / "Blueprint_Debug_Log.md"
    modular_prompt_file = config.target_dir / "modular_prompt.md"

    targets = [
        (reconfigure_gemini_md, gemini_file, repo_root / "GEMINI.md"),
        (reconfigure_blueprint_md, blueprint_file, repo_root / "Enterprise_Blueprint.md"),
        (reconfigure_readme, readme_file, repo_root / "README.md"),
        (reconfigure_debug_log, debug_log_file, repo_root / "Blueprint_Debug_Log.md"),
    ]

    audit_log_file = config.target_dir / "AUDIT_REMEDIATION_LOG.md"
    if (repo_root / "AUDIT_REMEDIATION_LOG.md").exists():
        targets.append((reconfigure_audit_remediation_log, audit_log_file, repo_root / "AUDIT_REMEDIATION_LOG.md"))

    project_map_file = config.target_dir / "PROJECT_MAP.md"
    if (repo_root / "PROJECT_MAP.md").exists():
        targets.append((reconfigure_project_map, project_map_file, repo_root / "PROJECT_MAP.md"))

    if (repo_root / "modular_prompt.md").exists():
        targets.append((reconfigure_modular_prompt, modular_prompt_file, repo_root / "modular_prompt.md"))

    reconfigured_texts: dict[str, str] = {}
    for func, f_path, src_path in targets:
        _, msg, processed_text = func(f_path, config, src_path)
        print(f"  [*] {msg}")
        reconfigured_texts[f_path.name] = processed_text

    # 3. Purge old audit deliverables if cloning
    if config.target_dir != repo_root or config.force:
        purge_actions = purge_old_audit_reports(config.target_dir, config.dry_run)
        for p_act in purge_actions:
            print(f"  [-] {p_act}")

    # 4. Optional directory scaffolding
    if config.scaffold_dirs:
        print("\n  Scaffolding starter directory skeleton:")
        scaffold_actions = scaffold_directory_skeleton(config)
        for s_act in scaffold_actions:
            print(f"  [+] {s_act}")

    # 5. Optional git repository initialization
    if config.git_init:
        print("\n  Initializing Git repository and staging files:")
        git_actions = initialize_git_repository(config)
        for g_act in git_actions:
            print(f"  [+] {g_act}")

    # 6. Automated post-run residual string and placeholder token audit
    print("\n  Running post-run token and residual string audit:")
    files_to_audit: dict[str, str] = {}
    if config.dry_run:
        files_to_audit = reconfigured_texts
    else:
        for _, f_path, _ in targets:
            if f_path.exists():
                files_to_audit[f_path.name] = f_path.read_text(encoding="utf-8")
            elif f_path.name in reconfigured_texts:
                files_to_audit[f_path.name] = reconfigured_texts[f_path.name]

    audit_passed, audit_messages = audit_generated_files(files_to_audit, config)
    for a_msg in audit_messages:
        print(f"  {a_msg}")

    if not audit_passed:
        print("\n[!] FATAL: Post-run token/residual audit failed!")
        sys.exit(1)

    print("\n=================================================================")
    print("  Bootstrap Scaffolding Completed Successfully!")
    print("=================================================================")
    print("\nNext Immediate Steps for Domain Engineers:")
    print("  1. Customize Domain Safeguards in GEMINI.md:")
    print("     - Section 3.1: Define canonical `ActionType` Literal Enum allowlist.")
    print("     - Section 3.2: Map actions to deterministic IAM policies & CLI templates.")
    print("     - Section 3.8: Replace FinOps reference rules with domain invariants.")
    print("     - Section 4:   Review registered MCP resource URIs.")
    print("  2. Customize Domain Milestones in Enterprise_Blueprint.md:")
    print(f"     - Phase 2.1: Define submodules under src/{config.package_name}/.")
    print("     - Phase 4.1-4.8: Implement domain-specific heuristics and guardrails.")
    print("     - Phase 5.5-5.7: Implement domain-specific MCP tools and prompts.")
    print("  3. Run Phase 0.1 Forensic Baseline Audit:")
    print(f"     - Execute Phase 0.1 and author Blueprint_Repo_Baseline_AuditReport.md.")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
