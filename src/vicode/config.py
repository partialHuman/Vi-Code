"""Project (vicode.yaml) and user configuration: strict loading, validation, precedence and trust.

Design rules implemented here (Sections 9.3 and 9.4 of the design document):

* YAML is read with a safe loader that also rejects duplicate keys.
* Unknown keys are errors, never silently ignored.
* Precedence, highest first: command line, project file, user file, built-in defaults.
* Settings that select a program to execute (the Vivado executable) are honoured from a
  project file only when the user has explicitly trusted that project.
"""

from __future__ import annotations

import collections.abc
import difflib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

SCHEMA_VERSION = 1
PROJECT_FILE = "vicode.yaml"
MAX_CONFIG_BYTES = 1_000_000

HDLS = ("Verilog", "SystemVerilog", "VHDL")
MODES = ("project",)
SIMULATORS = ("xsim",)

# --- declarative specification (drives validation AND the published JSON Schema) ---------
# leaf kinds: type | ("enum", values) | ("int", minimum) | [item type]
PROJECT_SPEC: dict[str, Any] = {
    "schema_version": int,
    "project": {"name": str, "top_module": str, "hdl": ("enum", HDLS)},
    "target": {"part": str, "board": str},
    "vivado": {"executable": str, "mode": ("enum", MODES)},
    "sources": {"rtl": [str], "testbenches": [str], "constraints": [str]},
    "simulation": {"top": str, "simulator": ("enum", SIMULATORS)},
    "build": {
        "jobs": ("int", 1),
        "run_synthesis": bool,
        "run_implementation": bool,
        "generate_bitstream": bool,
    },
}
USER_SPEC: dict[str, Any] = {
    "schema_version": int,
    "vivado": {"executable": str, "search_paths": [str]},
    "trusted_projects": [str],
}
PROJECT_REQUIRED: dict[str, Any] = {"": ["schema_version", "project"], "project": ["name"]}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,127}$")
PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
BOARD_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
PATTERNS = {
    "project.name": NAME_RE.pattern,
    "project.top_module": IDENT_RE.pattern,
    "simulation.top": IDENT_RE.pattern,
    "target.part": PART_RE.pattern,
    "target.board": BOARD_RE.pattern,
}

DEFAULT_RTL = ("rtl/**/*.v", "rtl/**/*.sv", "rtl/**/*.vhd")
DEFAULT_TESTBENCHES = ("sim/**/*.sv", "sim/**/*.v", "sim/**/*.vhd")
DEFAULT_CONSTRAINTS = ("constraints/**/*.xdc",)


class ConfigError(Exception):
    """Raised when configuration cannot be produced (used by helpers such as ``vicode init``)."""

    def __init__(self, issues: list["ConfigIssue"]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


@dataclass(frozen=True)
class ConfigIssue:
    path: str  # dotted key path, or "" for the whole file
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = self.path or "<file>"
        return f"{where}: {self.message}"


# --- strict YAML loading ---------------------------------------------------------------
class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, collections.abc.Hashable):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "found an unhashable key", key_node.start_mark
            )
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml_file(path: Path) -> tuple[Any, list[ConfigIssue]]:
    """Read and parse a YAML file. Returns ``(data, issues)``; data is None on failure."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, [ConfigIssue("", f"cannot read {path}: {exc.strerror or exc}")]
    if size > MAX_CONFIG_BYTES:
        return None, [ConfigIssue("", f"file is larger than {MAX_CONFIG_BYTES} bytes")]
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [ConfigIssue("", f"cannot read {path} as UTF-8 text: {exc}")]
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - _StrictLoader is a SafeLoader
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 1 if mark is not None else None
        problem = exc.problem or "invalid YAML"
        return None, [ConfigIssue("", f"YAML error: {problem}", line)]
    except yaml.YAMLError as exc:
        return None, [ConfigIssue("", f"YAML error: {exc}")]
    if data is None:
        return None, [ConfigIssue("", "file is empty")]
    return data, []


# --- generic validation ------------------------------------------------------------------
def _validate(data: Any, spec: Mapping[str, Any], path: tuple[str, ...], issues: list[ConfigIssue]) -> None:
    dotted = ".".join(path)
    if not isinstance(data, dict):
        issues.append(ConfigIssue(dotted, "must be a mapping"))
        return
    for key in data:
        if key not in spec:
            hint = difflib.get_close_matches(str(key), list(spec), n=1)
            extra = f" (did you mean '{hint[0]}'?)" if hint else ""
            issues.append(ConfigIssue(".".join(path + (str(key),)), f"unknown key{extra}"))
    for key, kind in spec.items():
        if key not in data:
            continue
        value = data[key]
        here = path + (key,)
        name = ".".join(here)
        if isinstance(kind, dict):
            _validate(value, kind, here, issues)
        elif isinstance(kind, list):
            if not isinstance(value, list) or not all(isinstance(v, kind[0]) for v in value):
                issues.append(ConfigIssue(name, "must be a list of strings"))
            elif any(not v.strip() for v in value):
                issues.append(ConfigIssue(name, "entries must not be empty"))
        elif isinstance(kind, tuple) and kind[0] == "enum":
            if not isinstance(value, str) or value not in kind[1]:
                issues.append(ConfigIssue(name, f"must be one of: {', '.join(kind[1])}"))
        elif isinstance(kind, tuple) and kind[0] == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                issues.append(ConfigIssue(name, "must be an integer"))
            elif value < kind[1]:
                issues.append(ConfigIssue(name, f"must be >= {kind[1]}"))
        elif kind is bool:
            if not isinstance(value, bool):
                issues.append(ConfigIssue(name, "must be true or false"))
        elif kind is int:
            if isinstance(value, bool) or not isinstance(value, int):
                issues.append(ConfigIssue(name, "must be an integer"))
        elif kind is str:
            if not isinstance(value, str) or not value.strip():
                issues.append(ConfigIssue(name, "must be a non-empty string"))
            elif any(ord(c) < 32 for c in value):
                issues.append(ConfigIssue(name, "must not contain control characters"))


def _check_pattern(data: Mapping[str, Any], dotted: str, regex: re.Pattern, what: str,
                   issues: list[ConfigIssue]) -> None:
    node: Any = data
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, str) and node.strip() and not regex.match(node):
        issues.append(ConfigIssue(dotted, f"'{node}' is not a valid {what}"))


def _check_globs(data: Mapping[str, Any], issues: list[ConfigIssue]) -> None:
    sources = data.get("sources")
    if not isinstance(sources, dict):
        return
    for group, patterns in sources.items():
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            if not isinstance(pattern, str):
                continue
            where = f"sources.{group}"
            if "\\" in pattern:
                issues.append(ConfigIssue(where, f"'{pattern}': use forward slashes"))
            elif pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern):
                issues.append(ConfigIssue(where, f"'{pattern}': patterns must be relative to the project"))
            elif ".." in pattern.split("/"):
                issues.append(ConfigIssue(where, f"'{pattern}': '..' is not allowed"))


def validate_project_dict(data: Any) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    _validate(data, PROJECT_SPEC, (), issues)
    if not isinstance(data, dict):
        return issues
    for key in PROJECT_REQUIRED[""]:
        if key not in data:
            issues.append(ConfigIssue(key, "is required"))
    project = data.get("project")
    if isinstance(project, dict) and "name" not in project:
        issues.append(ConfigIssue("project.name", "is required"))
    version = data.get("schema_version")
    if isinstance(version, int) and not isinstance(version, bool) and version != SCHEMA_VERSION:
        issues.append(ConfigIssue("schema_version", f"unsupported version {version}; this vicode supports {SCHEMA_VERSION}"))
    _check_pattern(data, "project.name", NAME_RE, "project name (letters, digits, '_' and '-', starting with a letter)", issues)
    _check_pattern(data, "project.top_module", IDENT_RE, "module name", issues)
    _check_pattern(data, "simulation.top", IDENT_RE, "module name", issues)
    _check_pattern(data, "target.part", PART_RE, "part name", issues)
    _check_pattern(data, "target.board", BOARD_RE, "board identifier", issues)
    _check_globs(data, issues)
    return issues


def validate_user_dict(data: Any) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    _validate(data, USER_SPEC, (), issues)
    if isinstance(data, dict):
        version = data.get("schema_version", SCHEMA_VERSION)
        if isinstance(version, int) and not isinstance(version, bool) and version != SCHEMA_VERSION:
            issues.append(ConfigIssue("schema_version", f"unsupported version {version}"))
    return issues


# --- typed models ------------------------------------------------------------------------
@dataclass(frozen=True)
class ProjectConfig:
    name: str
    top_module: str | None = None
    hdl: str = "SystemVerilog"
    part: str | None = None
    board: str | None = None
    vivado_executable: str = "auto"
    vivado_mode: str = "project"
    rtl: tuple[str, ...] = DEFAULT_RTL
    testbenches: tuple[str, ...] = DEFAULT_TESTBENCHES
    constraints: tuple[str, ...] = DEFAULT_CONSTRAINTS
    sim_top: str | None = None
    simulator: str = "xsim"
    jobs: int = 4
    run_synthesis: bool = True
    run_implementation: bool = True
    generate_bitstream: bool = False
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectConfig":
        def get(*keys: str, default: Any = None) -> Any:
            node: Any = data
            for k in keys:
                if not isinstance(node, Mapping) or k not in node:
                    return default
                node = node[k]
            return node

        return cls(
            name=get("project", "name"),
            top_module=get("project", "top_module"),
            hdl=get("project", "hdl", default="SystemVerilog"),
            part=get("target", "part"),
            board=get("target", "board"),
            vivado_executable=get("vivado", "executable", default="auto"),
            vivado_mode=get("vivado", "mode", default="project"),
            rtl=tuple(get("sources", "rtl", default=DEFAULT_RTL)),
            testbenches=tuple(get("sources", "testbenches", default=DEFAULT_TESTBENCHES)),
            constraints=tuple(get("sources", "constraints", default=DEFAULT_CONSTRAINTS)),
            sim_top=get("simulation", "top"),
            simulator=get("simulation", "simulator", default="xsim"),
            jobs=get("build", "jobs", default=4),
            run_synthesis=get("build", "run_synthesis", default=True),
            run_implementation=get("build", "run_implementation", default=True),
            generate_bitstream=get("build", "generate_bitstream", default=False),
            schema_version=get("schema_version", default=SCHEMA_VERSION),
        )

    def resolved(self) -> dict[str, Any]:
        """Fully resolved configuration (defaults applied); used for hashing and build records."""
        return {
            "schema_version": self.schema_version,
            "project": {"name": self.name, "top_module": self.top_module, "hdl": self.hdl},
            "target": {"part": self.part, "board": self.board},
            "vivado": {"executable": self.vivado_executable, "mode": self.vivado_mode},
            "sources": {"rtl": list(self.rtl), "testbenches": list(self.testbenches),
                        "constraints": list(self.constraints)},
            "simulation": {"top": self.sim_top, "simulator": self.simulator},
            "build": {"jobs": self.jobs, "run_synthesis": self.run_synthesis,
                      "run_implementation": self.run_implementation,
                      "generate_bitstream": self.generate_bitstream},
        }


@dataclass(frozen=True)
class UserConfig:
    vivado_executable: str | None = None
    search_paths: tuple[str, ...] = ()
    trusted_projects: tuple[str, ...] = ()


@dataclass
class LoadedProject:
    path: Path
    config: ProjectConfig | None
    issues: list[ConfigIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.config is not None and not self.issues


@dataclass
class LoadedUser:
    path: Path
    exists: bool
    config: UserConfig
    issues: list[ConfigIssue] = field(default_factory=list)


def load_project(project_dir: Path) -> LoadedProject:
    path = Path(project_dir) / PROJECT_FILE
    data, issues = load_yaml_file(path)
    if data is None:
        return LoadedProject(path, None, issues)
    issues = validate_project_dict(data)
    if issues:
        return LoadedProject(path, None, issues)
    return LoadedProject(path, ProjectConfig.from_dict(data))


def user_config_path(env: Mapping[str, str] | None = None, windows: bool | None = None) -> Path:
    env = os.environ if env is None else env
    windows = (os.name == "nt") if windows is None else windows
    override = env.get("VICODE_USER_CONFIG")
    if override:
        return Path(override)
    if windows:
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "vicode" / "config.yaml"
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "vicode" / "config.yaml"


def load_user(path: Path) -> LoadedUser:
    if not path.exists():
        return LoadedUser(path, False, UserConfig())
    data, issues = load_yaml_file(path)
    if data is None:
        return LoadedUser(path, True, UserConfig(), issues)
    issues = validate_user_dict(data)
    if issues:
        return LoadedUser(path, True, UserConfig(), issues)
    vivado = data.get("vivado", {}) or {}
    cfg = UserConfig(
        vivado_executable=vivado.get("executable"),
        search_paths=tuple(vivado.get("search_paths", ())),
        trusted_projects=tuple(data.get("trusted_projects", ())),
    )
    return LoadedUser(path, True, cfg)


def find_project_root(start: Path) -> Path | None:
    """Walk upwards from ``start`` looking for vicode.yaml."""
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    return None


# --- trust and precedence ------------------------------------------------------------------
def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def is_trusted(project_dir: Path, user: UserConfig) -> bool:
    target = _norm(project_dir)
    return any(_norm(p) == target for p in user.trusted_projects)


def add_trusted_project(user_path: Path, project_dir: Path) -> None:
    """Record ``project_dir`` as trusted in the user configuration file."""
    data: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    if user_path.exists():
        loaded, issues = load_yaml_file(user_path)
        if loaded is None or issues or validate_user_dict(loaded):
            raise ConfigError(issues or validate_user_dict(loaded))
        data = loaded
    trusted = list(data.get("trusted_projects", []))
    entry = str(Path(project_dir).resolve())
    if not any(_norm(entry) == _norm(t) for t in trusted):
        trusted.append(entry)
    data["trusted_projects"] = trusted
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@dataclass
class ResolvedExecutable:
    executable: str | None  # None means: auto-discover
    source: str  # cli | project | user | auto
    notes: list[str] = field(default_factory=list)


def resolve_vivado_executable(
    cli_value: str | None,
    project: ProjectConfig | None,
    project_dir: Path | None,
    user: UserConfig,
) -> ResolvedExecutable:
    """Apply the precedence rules; a project file may only select a program if trusted."""
    if cli_value:
        return ResolvedExecutable(cli_value, "cli")
    notes: list[str] = []
    if project is not None and project.vivado_executable != "auto":
        if project_dir is not None and is_trusted(project_dir, user):
            return ResolvedExecutable(project.vivado_executable, "project")
        notes.append(
            "Ignored vivado.executable from vicode.yaml because this project is not trusted. "
            "Set it in your user configuration, pass --vivado, or run 'vicode project trust'."
        )
    if user.vivado_executable and user.vivado_executable != "auto":
        return ResolvedExecutable(user.vivado_executable, "user", notes)
    return ResolvedExecutable(None, "auto", notes)


# --- JSON Schema (published for editors) -----------------------------------------------------
def _schema_for(kind: Any, dotted: str) -> dict[str, Any]:
    if isinstance(kind, dict):
        return _object_schema(kind, dotted)
    if isinstance(kind, list):
        return {"type": "array", "items": {"type": "string", "minLength": 1}}
    if isinstance(kind, tuple) and kind[0] == "enum":
        return {"type": "string", "enum": list(kind[1])}
    if isinstance(kind, tuple) and kind[0] == "int":
        return {"type": "integer", "minimum": kind[1]}
    if kind is bool:
        return {"type": "boolean"}
    if kind is int:
        return {"type": "integer"}
    schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if dotted in PATTERNS:
        schema["pattern"] = PATTERNS[dotted]
    return schema


def _object_schema(spec: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key, kind in spec.items():
        dotted = f"{prefix}.{key}" if prefix else key
        props[key] = _schema_for(kind, dotted)
    schema: dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": props}
    required = PROJECT_REQUIRED.get(prefix) if spec is not USER_SPEC else None
    if required:
        schema["required"] = required
    return schema


def build_json_schema() -> dict[str, Any]:
    schema = _object_schema(PROJECT_SPEC, "")
    schema["properties"]["schema_version"] = {"type": "integer", "const": SCHEMA_VERSION}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Vi-Code project manifest (vicode.yaml)",
        **schema,
    }


def schema_json_text() -> str:
    return json.dumps(build_json_schema(), indent=2) + "\n"
