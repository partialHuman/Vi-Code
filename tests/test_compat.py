from __future__ import annotations

import unittest
from unittest.mock import patch

from vicode import compat, platform_info


class CompatMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plat_win11 = platform_info.detect(system="windows", windows_build=22631, release="11")
        self.plat_linux = platform_info.detect(system="linux", release="6.5.0")

    def test_valid_matrix_parsing(self):
        raw = '{"schema_version": 1, "verified": [{"os": "windows-11", "vivado": "2018.2"}]}'
        data, err = compat.parse_matrix(raw)
        self.assertIsNone(err)
        self.assertEqual(len(data["verified"]), 1)

    def test_corrupt_json_string(self):
        data, err = compat.parse_matrix("{not valid json")
        self.assertIsNotNone(err)
        self.assertIn("corrupt compatibility matrix JSON", err)
        self.assertEqual(data["verified"], [])

    def test_list_root_rejected_gracefully(self):
        data, err = compat.parse_matrix('[{"os": "windows-11", "vivado": "2018.2"}]')
        self.assertIsNotNone(err)
        self.assertIn("must be a JSON object", err)
        self.assertEqual(data["verified"], [])

    def test_missing_or_non_list_verified_key(self):
        data, err = compat.parse_matrix('{"schema_version": 1}')
        self.assertIsNotNone(err)
        self.assertIn("missing 'verified' list", err)
        self.assertEqual(data["verified"], [])

        data2, err2 = compat.parse_matrix('{"schema_version": 1, "verified": "not-a-list"}')
        self.assertIsNotNone(err2)
        self.assertIn("missing 'verified' list", err2)
        self.assertEqual(data2["verified"], [])

    def test_entry_schema_validation(self):
        # Non-dict entry
        data, err = compat.parse_matrix('{"verified": ["not-a-dict"]}')
        self.assertIsNotNone(err)
        self.assertIn("entry 0 is not a JSON object", err)

        # Missing os field
        data, err = compat.parse_matrix('{"verified": [{"vivado": "2018.2"}]}')
        self.assertIsNotNone(err)
        self.assertIn("entry 0 missing valid 'os' field", err)

        # Missing vivado field
        data, err = compat.parse_matrix('{"verified": [{"os": "windows-11"}]}')
        self.assertIsNotNone(err)
        self.assertIn("entry 0 missing valid 'vivado' field", err)

    def test_load_matrix_always_returns_dict(self):
        matrix = compat.load_matrix("{invalid json")
        self.assertIsInstance(matrix, dict)
        self.assertIn("verified", matrix)

    def test_deep_copy_isolation_of_default_matrix(self):
        m1 = compat.load_matrix("{bad json")
        m1["verified"].append({"os": "evil", "vivado": "6.6.6"})
        m2 = compat.load_matrix("{another bad json")
        self.assertEqual(m2["verified"], [])
        self.assertEqual(compat.DEFAULT_MATRIX["verified"], [])

    def test_package_data_read_failure(self):
        with patch("importlib.resources.files", side_effect=OSError("disk read error")):
            data, err = compat.parse_matrix()
            self.assertIsNotNone(err)
            self.assertIn("could not load compat_matrix.json", err)
            self.assertEqual(data["verified"], [])

    def test_check_with_malformed_matrix_reports_diagnostics(self):
        # Non-dict matrix object
        status, msg = compat.check("2018.2", self.plat_win11, matrix=[])
        self.assertEqual(status, "untested")
        self.assertIn("compatibility matrix issue", msg)
        self.assertIn("matrix must be a dict", msg)

        # Corrupt JSON string
        status, msg = compat.check("2018.2", self.plat_win11, matrix="{not valid json")
        self.assertEqual(status, "untested")
        self.assertIn("compatibility matrix issue", msg)
        self.assertIn("corrupt compatibility matrix JSON", msg)

        # Missing verified list in dict
        status, msg = compat.check("2018.2", self.plat_win11, matrix={"verified": "invalid"})
        self.assertEqual(status, "untested")
        self.assertIn("compatibility matrix issue", msg)
        self.assertIn("missing 'verified' list", msg)

        # Malformed entries in passed dict
        status, msg = compat.check("2018.2", self.plat_win11, matrix={"verified": [123]})
        self.assertEqual(status, "untested")
        self.assertIn("compatibility matrix issue", msg)
        self.assertIn("entry 0 is not a JSON object", msg)

    def test_check_entry_with_non_verified_status(self):
        matrix = {"schema_version": 1, "verified": [{"os": "windows-11", "vivado": "2018.2", "status": "deprecated"}]}
        status, msg = compat.check("2018.2", self.plat_win11, matrix=matrix)
        self.assertEqual(status, "untested")
        self.assertIn("entry status is 'deprecated', not verified", msg)

    def test_check_verified_match(self):
        valid = {"schema_version": 1, "verified": [{"os": "windows-11", "vivado": "2018.2"}]}
        status, msg = compat.check("2018.2", self.plat_win11, matrix=valid)
        self.assertEqual(status, "verified")
        self.assertIn("is in the verified matrix", msg)

    def test_check_untested_version(self):
        valid = {"schema_version": 1, "verified": [{"os": "windows-11", "vivado": "2018.2"}]}
        status, msg = compat.check("2023.2", self.plat_win11, matrix=valid)
        self.assertEqual(status, "untested")
        self.assertIn("is not in the verified compatibility matrix yet", msg)
