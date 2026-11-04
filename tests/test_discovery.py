import os
from pathlib import Path

from vicode.vivado import discovery
from tests.support import TempDirTestCase


def make_launcher(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


class DiscoveryHelperTests(TempDirTestCase):
    def test_version_from_path(self):
        f = discovery.version_from_path
        self.assertEqual(f("C:\\Xilinx\\Vivado\\2023.2\\bin\\vivado.bat"), "2023.2")
        self.assertEqual(f("/tools/Xilinx/Vivado/2024.1/bin/vivado"), "2024.1")
        self.assertEqual(f("C:\\AMD\\2025.1\\Vivado\\bin\\vivado.bat"), "2025.1")
        self.assertEqual(f("C:\\AMD\\2025.1.1\\Vivado"), "2025.1.1")
        self.assertIsNone(f("/usr/local/bin/vivado"))

    def test_version_ordering(self):
        versions = ["2022.2", "2024.1", "2023.2", None]
        ordered = sorted(versions, key=discovery.version_key, reverse=True)
        self.assertEqual(ordered, ["2024.1", "2023.2", "2022.2", None])

    def test_default_roots(self):
        roots = discovery.default_roots(True, {"SystemDrive": "D:"})
        self.assertEqual(roots[0], "D:\\Xilinx\\Vivado")
        for expected in ("C:\\Xilinx\\Vivado", "C:\\AMD\\Vivado", "C:\\AMD", "C:\\Xilinx"):
            self.assertIn(expected, roots)
        self.assertEqual(len(roots), len(set(roots)))
        posix = discovery.default_roots(False, {"HOME": "/home/u"})
        self.assertIn("/opt/Xilinx/Vivado", posix)
        self.assertIn(os.path.join("/home/u", "Xilinx", "Vivado"), posix)

    def test_launcher_names(self):
        self.assertEqual(discovery.launcher_names(True), ("vivado.bat",))
        self.assertEqual(discovery.launcher_names(False), ("vivado",))


class DiscoverTests(TempDirTestCase):
    def test_roots_sorted_newest_first_both_layouts(self):
        make_launcher(self.tmp / "Vivado" / "2022.2" / "bin" / "vivado.bat")
        make_launcher(self.tmp / "Vivado" / "2024.1" / "bin" / "vivado.bat")
        make_launcher(self.tmp / "2023.2" / "Vivado" / "bin" / "vivado.bat")  # AMD style layout
        found = discovery.discover({}, True, extra_roots=[str(self.tmp / "Vivado"), str(self.tmp)],
                                   which=lambda n: None, include_default_roots=False)
        self.assertEqual([i.version for i in found], ["2024.1", "2023.2", "2022.2"])
        self.assertTrue(all(i.launcher.endswith("vivado.bat") for i in found))

    def test_posix_launcher_name(self):
        make_launcher(self.tmp / "Vivado" / "2023.2" / "bin" / "vivado")
        make_launcher(self.tmp / "Vivado" / "2024.1" / "bin" / "vivado.bat")  # ignored on posix
        found = discovery.discover({}, False, extra_roots=[str(self.tmp / "Vivado")], which=lambda n: None,
                                   include_default_roots=False)
        self.assertEqual([i.version for i in found], ["2023.2"])

    def test_priority_configured_env_path_then_roots(self):
        configured = make_launcher(self.tmp / "custom" / "bin" / "vivado")
        env_root = self.tmp / "env" / "2022.1"
        env_launcher = make_launcher(env_root / "bin" / "vivado")
        path_launcher = make_launcher(self.tmp / "onpath" / "2021.2" / "bin" / "vivado")
        make_launcher(self.tmp / "Vivado" / "2024.1" / "bin" / "vivado")
        found = discovery.discover({"XILINX_VIVADO": str(env_root)}, False, configured=str(configured),
                                   extra_roots=[str(self.tmp / "Vivado")], which=lambda n: str(path_launcher),
                                   include_default_roots=False)
        self.assertEqual([i.source for i in found], ["configured", "XILINX_VIVADO", "PATH", "extra-root"])
        self.assertEqual(found[1].launcher, str(env_launcher))
        self.assertEqual(found[2].version, "2021.2")

    def test_duplicates_are_removed_first_source_wins(self):
        root = self.tmp / "Vivado" / "2023.2"
        launcher = make_launcher(root / "bin" / "vivado")
        found = discovery.discover({"XILINX_VIVADO": str(root)}, False, extra_roots=[str(self.tmp / "Vivado")],
                                   which=lambda n: str(launcher), include_default_roots=False)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "XILINX_VIVADO")

    def test_nothing_found(self):
        self.assertEqual(discovery.discover({}, False, extra_roots=[str(self.tmp / "none")], which=lambda n: None,
                                            include_default_roots=False), [])

    def test_resolve_path_variants(self):
        launcher = make_launcher(self.tmp / "Vivado" / "2023.2" / "bin" / "vivado")
        install = launcher.parent.parent
        for given in (launcher, install, launcher.parent):
            inst = discovery.resolve_path(str(given), False)
            self.assertIsNotNone(inst, given)
            self.assertEqual(inst.launcher, str(launcher))
            self.assertEqual(inst.version, "2023.2")
            self.assertEqual(inst.source, "configured")
        self.assertIsNone(discovery.resolve_path(str(self.tmp / "missing"), False))
        self.assertIsNone(discovery.resolve_path(str(self.tmp), False))

    def test_install_root_property(self):
        launcher = make_launcher(self.tmp / "Vivado" / "2023.2" / "bin" / "vivado")
        inst = discovery.resolve_path(str(launcher), False)
        self.assertEqual(Path(inst.root), launcher.parent.parent)

    def test_planted_cwd_launcher_is_ignored_by_which(self):
        planted = make_launcher(self.tmp / "vivado.bat")
        found = discovery.discover({}, True, which=lambda n: str(planted),
                                   include_default_roots=False, cwd=self.tmp)
        self.assertEqual(found, [])

    def test_planted_project_dir_launcher_is_ignored_by_which(self):
        proj_dir = self.tmp / "proj"
        planted = make_launcher(proj_dir / "bin" / "vivado.bat")
        found = discovery.discover({}, True, which=lambda n: str(planted),
                                   include_default_roots=False, project_dir=proj_dir,
                                   cwd=self.tmp / "other")
        self.assertEqual(found, [])

    def test_explicit_configured_launcher_in_cwd_is_honored(self):
        planted = make_launcher(self.tmp / "vivado.bat")
        found = discovery.discover({}, True, configured=str(planted),
                                   include_default_roots=False, cwd=self.tmp)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "configured")
        self.assertEqual(Path(found[0].launcher), planted)

    def test_legitimate_path_tool_beneath_cwd_is_not_rejected(self):
        # Tools in nested folders beneath CWD (e.g. tools/ or .local/) must not be falsely rejected
        legit = make_launcher(self.tmp / "tools" / "Vivado" / "2023.2" / "bin" / "vivado.bat")
        found = discovery.discover({}, True, which=lambda n: str(legit),
                                   include_default_roots=False, cwd=self.tmp)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source, "PATH")
        self.assertEqual(Path(found[0].launcher), legit)
