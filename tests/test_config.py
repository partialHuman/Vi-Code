import json
import os
import tomllib
from importlib import resources
from pathlib import Path

from vicode import __version__, config
from tests.support import TempDirTestCase, VALID_MANIFEST


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class ProjectConfigTests(TempDirTestCase):
    def load(self, text: str) -> config.LoadedProject:
        write(self.tmp / "vicode.yaml", text)
        return config.load_project(self.tmp)

    def paths(self, text: str) -> list[str]:
        return [i.path for i in self.load(text).issues]

    def test_valid_manifest_loads(self):
        loaded = self.load(VALID_MANIFEST)
        self.assertTrue(loaded.ok, loaded.issues)
        cfg = loaded.config
        self.assertEqual((cfg.name, cfg.part, cfg.board, cfg.sim_top), ("FlexRISC32", "xc7z020clg400-1", "pynq-z2", "tb_flexrisc32"))
        self.assertEqual(cfg.rtl, ("rtl/**/*.v", "rtl/**/*.sv"))
        self.assertFalse(cfg.generate_bitstream)

    def test_defaults_are_applied(self):
        cfg = self.load("schema_version: 1\nproject:\n  name: demo\n").config
        self.assertEqual((cfg.hdl, cfg.vivado_executable, cfg.vivado_mode, cfg.simulator), ("SystemVerilog", "auto", "project", "xsim"))
        self.assertEqual((cfg.jobs, cfg.run_synthesis, cfg.run_implementation, cfg.generate_bitstream), (4, True, True, False))
        self.assertEqual(cfg.constraints, config.DEFAULT_CONSTRAINTS)

    def test_schema_version_is_required_and_checked(self):
        self.assertIn("schema_version", self.paths("project:\n  name: demo\n"))
        self.assertIn("schema_version", self.paths("schema_version: 2\nproject:\n  name: demo\n"))

    def test_project_name_is_required(self):
        self.assertIn("project", self.paths("schema_version: 1\n"))
        self.assertIn("project.name", self.paths("schema_version: 1\nproject:\n  hdl: VHDL\n"))

    def test_unknown_keys_are_errors_with_suggestion(self):
        issues = self.load("schema_version: 1\nproject:\n  name: demo\nbild:\n  jobs: 2\n").issues
        self.assertEqual([i.path for i in issues], ["bild"])
        self.assertIn("did you mean 'build'", issues[0].message)
        self.assertIn("project.nmae", self.paths("schema_version: 1\nproject:\n  name: demo\n  nmae: x\n"))

    def test_type_errors(self):
        base = "schema_version: 1\nproject:\n  name: demo\nbuild:\n"
        self.assertIn("build.jobs", self.paths(base + '  jobs: "4"\n'))
        self.assertIn("build.jobs", self.paths(base + "  jobs: true\n"), "bool must not pass as int")
        self.assertIn("build.jobs", self.paths(base + "  jobs: 0\n"))
        self.assertIn("build.run_synthesis", self.paths(base + '  run_synthesis: "yes"\n'))
        self.assertIn("sources.rtl", self.paths("schema_version: 1\nproject:\n  name: demo\nsources:\n  rtl: rtl/a.v\n"))
        self.assertIn("target", self.paths("schema_version: 1\nproject:\n  name: demo\ntarget:\n"))

    def test_enums(self):
        self.assertIn("project.hdl", self.paths("schema_version: 1\nproject:\n  name: demo\n  hdl: Chisel\n"))
        self.assertIn("vivado.mode", self.paths("schema_version: 1\nproject:\n  name: demo\nvivado:\n  mode: non_project\n"))
        self.assertIn("simulation.simulator", self.paths("schema_version: 1\nproject:\n  name: demo\nsimulation:\n  simulator: questa\n"))

    def test_identifier_patterns(self):
        for bad in ("1demo", "has space", "a/b", "a;b", "x" * 80):
            self.assertIn("project.name", self.paths(f'schema_version: 1\nproject:\n  name: "{bad}"\n'), bad)
        self.assertIn("project.top_module", self.paths('schema_version: 1\nproject:\n  name: demo\n  top_module: "a b"\n'))
        self.assertIn("target.part", self.paths('schema_version: 1\nproject:\n  name: demo\ntarget:\n  part: "xc7 z"\n'))
        self.assertIn("target.board", self.paths('schema_version: 1\nproject:\n  name: demo\ntarget:\n  board: "a b"\n'))

    def test_glob_rules(self):
        def glob_paths(pattern):
            return self.paths(f'schema_version: 1\nproject:\n  name: demo\nsources:\n  rtl:\n    - "{pattern}"\n')
        self.assertEqual(glob_paths("rtl/**/*.v"), [])
        for bad in ("/etc/*.v", "C:/x/*.v", "../x/*.v", "rtl/../../x.v", "rtl\\\\*.v"):
            self.assertIn("sources.rtl", glob_paths(bad), bad)

    def test_control_characters_rejected(self):
        self.assertIn("vivado.executable", self.paths('schema_version: 1\nproject:\n  name: demo\nvivado:\n  executable: "a\\nb"\n'))

    def test_yaml_problems(self):
        self.assertTrue(any("duplicate key" in i.message for i in self.load("schema_version: 1\nschema_version: 1\n").issues))
        syntax = self.load("project: [unclosed\n").issues
        self.assertTrue(syntax and syntax[0].line is not None)
        self.assertEqual(self.load("").issues[0].message, "file is empty")
        self.assertIn("must be a mapping", self.load("- a\n- b\n").issues[0].message)
        self.assertTrue(config.load_project(self.tmp / "nope").issues)  # missing file
        # unsafe YAML tags must not execute or construct objects
        self.assertTrue(self.load("x: !!python/object/apply:os.system ['echo hi']\n").issues)

    def test_resolved_and_hash_are_stable(self):
        a = self.load(VALID_MANIFEST).config.resolved()
        b = self.load(VALID_MANIFEST).config.resolved()
        self.assertEqual(a, b)
        self.assertEqual(a["target"]["part"], "xc7z020clg400-1")

    def test_find_project_root(self):
        write(self.tmp / "vicode.yaml", VALID_MANIFEST)
        nested = self.tmp / "rtl" / "deep"
        nested.mkdir(parents=True)
        self.assertEqual(config.find_project_root(nested), self.tmp)
        other = self.tmp / "other"
        other.mkdir()
        (other / "vicode.yaml").write_text("x", encoding="utf-8")
        self.assertEqual(config.find_project_root(other), other)


class UserConfigAndTrustTests(TempDirTestCase):
    def test_user_config_path(self):
        self.assertEqual(config.user_config_path({"VICODE_USER_CONFIG": "/x/c.yaml"}, False), Path("/x/c.yaml"))
        self.assertEqual(config.user_config_path({"APPDATA": "/appdata"}, True), Path("/appdata") / "vicode" / "config.yaml")
        self.assertEqual(config.user_config_path({"XDG_CONFIG_HOME": "/xdg"}, False), Path("/xdg") / "vicode" / "config.yaml")

    def test_load_user(self):
        missing = config.load_user(self.tmp / "none.yaml")
        self.assertFalse(missing.exists)
        self.assertIsNone(missing.config.vivado_executable)
        good = write(self.tmp / "u.yaml", "schema_version: 1\nvivado:\n  executable: /x/vivado\n  search_paths: [/a, /b]\ntrusted_projects: [/p]\n")
        loaded = config.load_user(good)
        self.assertEqual((loaded.config.vivado_executable, loaded.config.search_paths, loaded.config.trusted_projects),
                         ("/x/vivado", ("/a", "/b"), ("/p",)))
        bad = write(self.tmp / "bad.yaml", "unknown: 1\n")
        self.assertTrue(config.load_user(bad).issues)

    def test_add_trusted_project_round_trip(self):
        user, proj = self.tmp / "cfg" / "user.yaml", self.tmp / "proj"
        proj.mkdir()
        config.add_trusted_project(user, proj)
        config.add_trusted_project(user, proj)  # idempotent
        loaded = config.load_user(user)
        self.assertEqual(len(loaded.config.trusted_projects), 1)
        self.assertTrue(config.is_trusted(proj, loaded.config))
        self.assertFalse(config.is_trusted(self.tmp, loaded.config))

    def test_add_trusted_project_refuses_invalid_user_file(self):
        user = write(self.tmp / "user.yaml", "bogus: 1\n")
        with self.assertRaises(config.ConfigError):
            config.add_trusted_project(user, self.tmp)
        self.assertEqual(user.read_text(encoding="utf-8"), "bogus: 1\n")

    def test_precedence_and_trust(self):
        proj_cfg = config.ProjectConfig(name="demo", vivado_executable="/repo/evil")
        auto_cfg = config.ProjectConfig(name="demo")
        user_plain = config.UserConfig(vivado_executable="/user/vivado")
        user_trusting = config.UserConfig(vivado_executable="/user/vivado", trusted_projects=(str(self.tmp),))

        r = config.resolve_vivado_executable("/cli/vivado", proj_cfg, self.tmp, user_trusting)
        self.assertEqual((r.executable, r.source), ("/cli/vivado", "cli"))
        r = config.resolve_vivado_executable(None, proj_cfg, self.tmp, user_trusting)
        self.assertEqual((r.executable, r.source), ("/repo/evil", "project"))
        r = config.resolve_vivado_executable(None, proj_cfg, self.tmp, user_plain)  # untrusted project
        self.assertEqual((r.executable, r.source), ("/user/vivado", "user"))
        self.assertTrue(r.notes and "not trusted" in r.notes[0])
        r = config.resolve_vivado_executable(None, auto_cfg, self.tmp, user_plain)
        self.assertEqual((r.executable, r.source, r.notes), ("/user/vivado", "user", []))
        r = config.resolve_vivado_executable(None, auto_cfg, self.tmp, config.UserConfig())
        self.assertEqual((r.executable, r.source), (None, "auto"))
        r = config.resolve_vivado_executable(None, proj_cfg, self.tmp, config.UserConfig())
        self.assertIsNone(r.executable)  # an untrusted repository can never choose the program


class SchemaTests(TempDirTestCase):
    def test_published_schema_matches_spec(self):
        packaged = resources.files("vicode").joinpath("data/vicode.schema.json").read_text(encoding="utf-8")
        self.assertEqual(packaged, config.schema_json_text(), "run scripts/gen_schema.py")

    def test_schema_covers_every_key(self):
        schema = json.loads(config.schema_json_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), set(config.PROJECT_SPEC))
        self.assertEqual(schema["properties"]["schema_version"]["const"], config.SCHEMA_VERSION)
        self.assertEqual(schema["required"], ["schema_version", "project"])
        self.assertEqual(schema["properties"]["project"]["required"], ["name"])
        self.assertIn("pattern", schema["properties"]["project"]["properties"]["name"])
        self.assertEqual(schema["properties"]["build"]["properties"]["jobs"]["minimum"], 1)


class MetadataTests(TempDirTestCase):
    def test_version_matches_pyproject(self):
        root = Path(__file__).resolve().parent.parent
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["version"], __version__)
