#!/usr/bin/env python3
"""Accueil de session pour un projet Claude Code (hook SessionStart)."""
import json
import os
import re
import sys


def read_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None, None
    match = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    block = match.group(1) if match else ""
    name = description = None
    for line in block.splitlines():
        if name is None and line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif description is None and line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    if description is None:
        heading = re.search(r"^#\s+(.*)", text, re.M)
        if heading:
            title = heading.group(1).strip()
            description = title.split("—", 1)[1].strip() if "—" in title else title
    return name, description


def collect_skills(skills_dir):
    entries = []
    if not os.path.isdir(skills_dir):
        return entries
    for slug in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, slug, "SKILL.md")
        if os.path.isfile(skill_md):
            name, description = read_frontmatter(skill_md)
            entries.append((name or slug, description or ""))
    return entries


def collect_agents(agents_dir):
    entries = []
    if not os.path.isdir(agents_dir):
        return entries
    for filename in sorted(os.listdir(agents_dir)):
        if filename.endswith(".md"):
            name, description = read_frontmatter(os.path.join(agents_dir, filename))
            entries.append((name or filename[:-3], description or ""))
    return entries


def collect_mcp_servers(project_dir):
    mcp_path = os.path.join(project_dir, ".mcp.json")
    if not os.path.isfile(mcp_path):
        return []
    try:
        with open(mcp_path, encoding="utf-8") as handle:
            return sorted(json.load(handle).get("mcpServers", {}).keys())
    except (OSError, ValueError):
        return []


def collect_master_commands(skills_dir, master):
    master_md = os.path.join(skills_dir, master, "SKILL.md")
    try:
        with open(master_md, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    commands = []
    in_section = False
    for line in lines:
        heading = re.match(r"^#{1,6}\s+(.*)", line)
        if heading:
            in_section = "commande" in heading.group(1).lower()
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if commands:
                break
            continue
        if "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in ("commande", "command"):
            continue
        commands.append((cells[0].strip("`"), cells[1]))
    return commands


def build_context(master, skills, agents, mcp_servers, commands):
    lines = [f"[ACCUEIL DE SESSION — projet/agent : {master}]"]
    if skills:
        lines.append("Skills disponibles :")
        lines += [f"- {name} — {desc}" if desc else f"- {name}" for name, desc in skills]
    if agents:
        lines.append("Sous-agents disponibles :")
        lines += [f"- {name} — {desc}" if desc else f"- {name}" for name, desc in agents]
    if mcp_servers:
        lines.append("Serveurs MCP actifs : " + ", ".join(mcp_servers))
    if commands:
        lines.append(f"Commandes du skill maître /{master} (helper) :")
        lines += [f"- {cmd} — {action}" if action else f"- {cmd}" for cmd, action in commands]
    lines.append(
        "Consigne : commence ta toute première réponse de la session par un message "
        "de bienvenue chaleureux rappelant de façon synthétique ces possibilités "
        "(skills, sous-agents, MCP, commandes). Une seule fois, en tête de réponse."
    )
    return "\n".join(lines)


def gather(project_dir):
    master = os.path.basename(os.path.normpath(project_dir))
    claude_dir = os.path.join(project_dir, ".claude")
    skills_dir = os.path.join(claude_dir, "skills")
    return (
        master,
        collect_skills(skills_dir),
        collect_agents(os.path.join(claude_dir, "agents")),
        collect_mcp_servers(project_dir),
        collect_master_commands(skills_dir, master),
    )


def read_stdin_json():
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def resolve_project_dir(stdin_json):
    from_stdin = (stdin_json.get("workspace") or {}).get("current_dir") or stdin_json.get("cwd")
    return from_stdin or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def main():
    stdin_json = read_stdin_json()
    project_dir = resolve_project_dir(stdin_json)
    master, skills, agents, mcp_servers, commands = gather(project_dir)
    context = build_context(master, skills, agents, mcp_servers, commands)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
