#!/usr/bin/env python3
"""Migrate a JaKooLit/Hyprland-Dots Hyprlang tree to the Lua layout.

The converter is intentionally conservative: a directive without a safe Lua
equivalent is recorded as a blocker and the generated tree is never activated.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "config" / "hypr"
USER_MODULES = {
    "01-UserDefaults", "ENVariables", "LaptopDisplay", "Laptops",
    "Startup_Apps", "UserAnimations", "UserDecorations", "UserKeybinds",
    "UserSettings", "WindowRules",
}
CONFIG_MODULES = {"ENVariables", "Keybinds", "Laptops", "Startup_Apps", "SystemSettings", "WindowRules"}
KEEP_CONF = {"hypridle.conf", "hyprlock.conf", "hyprlock-2k.conf", "wallust-hyprland.conf"}


class Report:
    def __init__(self) -> None:
        self.converted: list[str] = []
        self.warnings: list[str] = []
        self.blockers: list[str] = []

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2) + "\n")


def q(value: str) -> str:
    return json.dumps(value)


def strip_comment(line: str) -> str:
    quote = None
    escaped = False
    for i, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in "\"'":
            quote = None if quote == char else (char if quote is None else quote)
        elif char == "#" and quote is None:
            return line[:i]
    return line


def lua_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else f"[{q(key)}]"


def lua_value(value: str, variables: dict[str, str]) -> str:
    value = value.strip()
    if value in {"true", "false", "nil"} or re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return value
    if value.startswith("$") and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", value):
        return variables.get(value[1:], q(value))
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return q(value[1:-1])
    return q(value)


def split_csv(value: str) -> list[str]:
    result, current, quote, depth = [], [], None, 0
    for char in value:
        if char in "\"'" and (not current or current[-1] != "\\"):
            quote = None if quote == char else (char if quote is None else quote)
        elif quote is None and char == "(":
            depth += 1
        elif quote is None and char == ")":
            depth -= 1
        if char == "," and quote is None and depth == 0:
            result.append("".join(current).strip()); current = []
        else:
            current.append(char)
    result.append("".join(current).strip())
    return result


def parse_blocks(lines: list[str], report: Report, origin: str) -> tuple[dict, list[tuple[str, str]]]:
    root: dict = {}
    directives: list[tuple[str, str]] = []
    stack: list[dict] = [root]
    for number, raw in enumerate(lines, 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.endswith("{"):
            name = line[:-1].strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name):
                report.blockers.append(f"{origin}:{number}: bloco não suportado: {name}")
                continue
            node = stack[-1].setdefault(name, {})
            if not isinstance(node, dict):
                report.blockers.append(f"{origin}:{number}: conflito de bloco: {name}")
                continue
            stack.append(node)
            continue
        if line == "}":
            if len(stack) == 1:
                report.blockers.append(f"{origin}:{number}: }} sem bloco aberto")
            else:
                stack.pop()
            continue
        if "=" not in line:
            report.blockers.append(f"{origin}:{number}: sintaxe não reconhecida: {line}")
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in {"env", "exec-once", "monitor", "workspace", "windowrule", "windowrulev2", "layerrule", "animation", "gesture", "unbind"} or key.startswith("bind"):
            directives.append((key, value)); continue
        if key == "source":
            # Module sources are represented by the Lua entrypoint; arbitrary
            # sources cannot safely be imported into Lua.
            continue
        if key.startswith("$"):
            root.setdefault("__variables__", {})[key[1:]] = value
        else:
            stack[-1][key] = value
    if len(stack) != 1:
        report.blockers.append(f"{origin}: bloco não fechado")
    return root, directives


def emit_table(node: dict, variables: dict[str, str], indent: str = "    ") -> list[str]:
    out: list[str] = ["hl.config({"]
    def walk(values: dict, depth: int) -> None:
        pad = indent * depth
        for key, value in values.items():
            if key == "__variables__":
                continue
            if isinstance(value, dict):
                out.append(f"{pad}{lua_key(key)} = {{")
                walk(value, depth + 1)
                out.append(f"{pad}}},")
            else:
                out.append(f"{pad}{lua_key(key)} = {lua_value(value, variables)},")
    walk(node, 1)
    out.append("})")
    return out


def bind_dispatch(dispatcher: str, arg: str, report: Report, origin: str) -> str | None:
    if dispatcher == "exec": return f"hl.dsp.exec_cmd({q(arg)})"
    if dispatcher == "workspace": return f"hl.dsp.focus({{ workspace = {q(arg)} }})"
    if dispatcher == "focusworkspaceoncurrentmonitor": return f"hl.dsp.focus({{ workspace = {q(arg)}, on_current_monitor = true }})"
    if dispatcher == "fullscreen": return "hl.dsp.window.fullscreen()"
    if dispatcher == "togglefloating": return "hl.dsp.window.float()"
    if dispatcher == "killactive": return "hl.dsp.window.kill()"
    if dispatcher == "closewindow": return "hl.dsp.window.close()"
    if dispatcher == "movetoworkspace": return f"hl.dsp.window.move({{ workspace = {q(arg)} }})"
    if dispatcher == "togglespecialworkspace": return f"hl.dsp.workspace.toggle_special({q(arg)})" if arg else "hl.dsp.workspace.toggle_special()"
    report.blockers.append(f"{origin}: dispatcher de bind não suportado: {dispatcher}")
    return None


def key_combo(mods: str, binding: str, raw_vars: dict[str, str]) -> str:
    """Resolve Hyprlang's modifier field to the key syntax expected by hl.bind."""
    parts: list[str] = []
    for part in mods.split():
        if part.startswith("$") and part[1:] in raw_vars:
            parts.append(raw_vars[part[1:]].strip().strip("\"'"))
        elif part:
            parts.append(part)
    if binding:
        parts.append(binding)
    return q(" + ".join(parts))


def emit_window_rule(value: str, report: Report, origin: str) -> str | None:
    """Convert the common v1 rule form used by the fork and user overrides."""
    fields = split_csv(value)
    if len(fields) < 2:
        report.blockers.append(f"{origin}: windowrule inválida: {value}")
        return None
    matcher, effect = fields[0].strip(), fields[1].strip()
    if not matcher.startswith("match:"):
        report.blockers.append(f"{origin}: windowrule sem match: explícito: {value}")
        return None
    match_key, _, match_value = matcher[6:].partition(" ")
    aliases = {"class": "class", "title": "title", "initial_class": "initial_class", "initial_title": "initial_title", "tag": "tag"}
    if match_key not in aliases or not match_value:
        report.blockers.append(f"{origin}: match de windowrule não suportado: {matcher}")
        return None
    rule = ["hl.window_rule({", "  match = {", f"    {aliases[match_key]} = {q(match_value)},", "  },"]
    if effect.startswith("opacity "):
        rule.append(f"  opacity = {q(effect[8:].strip())},")
    elif effect in {"float", "fullscreen", "maximize", "center", "pin", "no_border", "no_shadow", "no_blur", "dim_around"}:
        rule.append(f"  {effect} = true,")
    elif effect.startswith("workspace "):
        rule.append(f"  workspace = {q(effect[10:].strip())},")
    else:
        report.blockers.append(f"{origin}: efeito de windowrule não suportado: {effect}")
        return None
    rule.append("})")
    return "\n".join(rule)


def emit_directives(directives: list[tuple[str, str]], variables: dict[str, str], report: Report, origin: str) -> list[str]:
    out: list[str] = []
    startup: list[str] = []
    for key, value in directives:
        if key == "env":
            fields = split_csv(value)
            if len(fields) == 2: out.append(f"hl.env({q(fields[0])}, {lua_value(fields[1], variables)})")
            else: report.blockers.append(f"{origin}: env inválido: {value}")
        elif key == "exec-once":
            startup.append(value)
        elif key == "monitor":
            fields = split_csv(value)
            if len(fields) >= 4:
                out.append("hl.monitor({ output = %s, mode = %s, position = %s, scale = %s })" % tuple(q(x) for x in fields[:4]))
            else: report.blockers.append(f"{origin}: monitor inválido: {value}")
        elif key == "unbind":
            fields = split_csv(value)
            if len(fields) != 2:
                report.blockers.append(f"{origin}: unbind inválido: {value}"); continue
            out.append(f"hl.unbind({key_combo(fields[0], fields[1], variables)})")
        elif key.startswith("bind"):
            fields = split_csv(value)
            dispatcher_index = 3 if key == "bindd" else 2
            if len(fields) <= dispatcher_index:
                report.blockers.append(f"{origin}: bind inválido: {value}"); continue
            mods, binding = fields[:2]
            dispatcher = fields[dispatcher_index]
            arg = ",".join(fields[dispatcher_index + 1:]).strip()
            lua_dispatcher = bind_dispatch(dispatcher, arg, report, origin)
            if lua_dispatcher:
                out.append(f"hl.bind({key_combo(mods, binding, variables)}, {lua_dispatcher})")
        elif key == "windowrule":
            rule = emit_window_rule(value, report, origin)
            if rule: out.append(rule)
        elif key in {"windowrulev2", "layerrule", "workspace", "animation", "gesture"}:
            report.blockers.append(f"{origin}: {key} requer conversão manual: {value}")
    if startup:
        out.extend(["hl.on(\"hyprland.start\", function()"] + [f"    hl.exec_cmd({q(cmd)})" for cmd in startup] + ["end)"])
    return out


def convert_file(source: Path, destination: Path, report: Report) -> None:
    tree, directives = parse_blocks(source.read_text(errors="replace").splitlines(), report, str(source))
    raw_vars = tree.pop("__variables__", {})
    variables = {name: lua_value(value, {}) for name, value in raw_vars.items()}
    lines = ["-- Generated by Hyprland-Dots migration. Review migration-report.json.", "---@module 'hl'", ""]
    for name, value in raw_vars.items(): lines.append(f"local {name} = {lua_value(value, variables)}")
    if raw_vars: lines.append("")
    if tree: lines.extend(emit_table(tree, variables)); lines.append("")
    lines.extend(emit_directives(directives, variables, report, str(source)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip() + "\n")
    report.converted.append(str(source))


def is_supported_tree(config: Path) -> bool:
    entry = config / "hyprland.conf"
    return entry.exists() and (config / "UserConfigs").is_dir() and (config / "configs").is_dir()


def copy_template(template: Path, stage: Path) -> None:
    def ignore(_: str, names: list[str]) -> set[str]:
        return {name for name in names if name == "hyprland.conf" or name == "hyprland.conf.legacy"}
    shutil.copytree(template, stage, ignore=ignore)


def matches_shipped_legacy(source: Path, source_root: Path, template: Path) -> bool:
    """Do not re-convert an unchanged vendor module over the reviewed Lua one."""
    candidate = template / source.relative_to(source_root)
    return candidate.is_file() and candidate.read_bytes() == source.read_bytes()


def run_check(stage: Path, report: Report) -> None:
    for lua in stage.rglob("*.lua"):
        result = subprocess.run(["luac", "-p", str(lua)], text=True, capture_output=True)
        if result.returncode: report.blockers.append(f"{lua}: luac: {result.stderr.strip()}")
    result = subprocess.run(["Hyprland", "--verify-config", "--config", str(stage / "hyprland.lua")], text=True, capture_output=True)
    if result.returncode or "config ok" not in result.stdout + result.stderr:
        report.blockers.append("Hyprland --verify-config falhou: " + (result.stdout + result.stderr).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".config" / "hypr")
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--experimental", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-target-backup", action="store_true")
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    source = args.config_dir.expanduser().resolve()
    target = (args.target_dir or source).expanduser().resolve()
    if args.rollback:
        if target.exists(): shutil.rmtree(target)
        shutil.copytree(args.rollback.expanduser(), target)
        print(f"Rollback restaurado em {target}"); return 0
    if not source.is_dir() or not args.template_dir.is_dir():
        parser.error("config-dir e template-dir devem existir")
    if not is_supported_tree(source) and not args.experimental:
        parser.error("config não reconhecida; use --experimental para uma conversão sem garantia")
    report = Report()
    with tempfile.TemporaryDirectory(prefix="hypr-lua-migration-", dir=target.parent) as tmp:
        stage = Path(tmp) / "hypr"
        copy_template(args.template_dir, stage)
        for rel in [Path("monitors.conf"), Path("workspaces.conf")]:
            legacy = source / rel
            if legacy.exists() and not matches_shipped_legacy(legacy, source, args.template_dir):
                convert_file(legacy, stage / rel.with_suffix(".lua"), report)
            elif legacy.exists():
                report.warnings.append(f"{legacy}: default do fork; mantido o módulo Lua revisado")
        for directory, allowed in [("UserConfigs", USER_MODULES), ("configs", CONFIG_MODULES)]:
            for conf in (source / directory).glob("*.conf") if (source / directory).is_dir() else []:
                if conf.stem in allowed and not matches_shipped_legacy(conf, source, args.template_dir):
                    convert_file(conf, stage / directory / f"{conf.stem}.lua", report)
                elif conf.stem in allowed:
                    report.warnings.append(f"{conf}: default do fork; mantido o módulo Lua revisado")
                else: report.warnings.append(f"{conf}: módulo legado mantido fora do entrypoint Lua")
        run_check(stage, report)
        report.write(stage / "migration-report.json")
        print(json.dumps(report.__dict__, indent=2))
        if args.dry_run or report.blockers:
            return 0 if not report.blockers else 2
        if not args.yes:
            answer = input("Ativar a árvore Lua validada? [y/N] ").strip().lower()
            if answer not in {"y", "yes", "s", "sim"}: return 0
        if target.exists() and not args.no_target_backup:
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target.with_name(f"{target.name}-pre-lua-{stamp}")
            shutil.move(target, backup)
            print(f"Backup: {backup}")
        elif target.exists():
            shutil.rmtree(target)
        shutil.move(stage, target)
    print(f"Lua ativada em {target}. Saia e entre novamente no Hyprland.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
