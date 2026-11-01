import unittest

from vicode.vivado import messages, tcl

SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./:@%+=,-")


def unescape(word: str) -> str:
    """Minimal Tcl backslash substitution for a single bare word (test oracle)."""
    if word == '""':
        return ""
    out, i = [], 0
    while i < len(word):
        ch = word[i]
        if ch != "\\":
            assert ch in SAFE, f"unescaped special character {ch!r} in {word!r}"
            out.append(ch)
            i += 1
            continue
        nxt = word[i + 1]
        if nxt == "n":
            out.append("\n"); i += 2
        elif nxt == "r":
            out.append("\r"); i += 2
        elif nxt == "t":
            out.append("\t"); i += 2
        elif nxt == "x":
            out.append(chr(int(word[i + 2:i + 4], 16))); i += 4
        elif nxt == "u":
            out.append(chr(int(word[i + 2:i + 6], 16))); i += 6
        elif nxt == "U":
            out.append(chr(int(word[i + 2:i + 10], 16))); i += 10
        else:
            out.append(nxt); i += 2
    return "".join(out)


class TclQuoteTests(unittest.TestCase):
    HOSTILE = ['plain', 'a b', 'a;b', '[exec calc]', '$env(PATH)', '{braces}', '"quoted"', "it's", 'back\\slash',
               'line1\nline2', 'tab\there', 'cr\rlf', '#comment', 'ünïcode', 'emoji \U0001F600', 'ctl\x01\x7f',
               '-leading-dash', '', ' ', '}; exec calc; {', 'C:\\Users\\a b\\x.v']

    def test_round_trip_and_no_raw_specials(self):
        for value in self.HOSTILE:
            self.assertEqual(unescape(tcl.quote(value)), value, repr(value))

    def test_output_is_a_single_word(self):
        for value in self.HOSTILE:
            q = tcl.quote(value)
            if q == '""':  # the empty-string literal is a single word by definition
                continue
            for ch in " \t\n\r;[]$\"{}":
                # any special must be preceded by a backslash
                idx = q.find(ch)
                while idx != -1:
                    self.assertGreater(idx, 0, f"{value!r} -> {q!r}")
                    self.assertEqual(q[idx - 1], "\\")
                    idx = q.find(ch, idx + 1)

    def test_path_uses_forward_slashes(self):
        self.assertEqual(unescape(tcl.path("C:\\Users\\a b\\x.v")), "C:/Users/a b/x.v")

    def test_probe_script(self):
        text = tcl.probe_script()
        self.assertIn('puts "VICODE:begin"', text)
        self.assertIn("version -short", text)
        self.assertNotIn("get_parts", text)
        with_part = tcl.probe_script("xc7z020clg400-1")
        self.assertIn("get_parts -quiet xc7z020clg400-1", with_part)
        evil = tcl.probe_script("x]; exec calc; [y")
        self.assertNotIn("; exec", evil.replace("\\;", ""))
        self.assertIn("x\\]\\;\\ exec\\ calc\\;\\ \\[y", evil)

    def test_parse_probe_output(self):
        ok = ["noise", "VICODE:begin", "VICODE:version=2023.2", "VICODE:part_found=1", "VICODE:end"]
        self.assertEqual(tcl.parse_probe_output(ok), {"version": "2023.2", "part_found": "1"})
        self.assertIsNone(tcl.parse_probe_output(["VICODE:begin", "VICODE:version=1"]))  # no end marker
        self.assertIsNone(tcl.parse_probe_output(["nothing"]))


class MessageParserTests(unittest.TestCase):
    def test_warning_with_file_and_line(self):
        d = messages.parse_line("WARNING: [Synth 8-3332] Sequential element (q_reg) is unused. [C:/proj/rtl/top.sv:42]")
        self.assertEqual((d.severity, d.id, d.file, d.line), ("warning", "Synth 8-3332", "C:/proj/rtl/top.sv", 42))
        self.assertEqual(d.message, "Sequential element (q_reg) is unused.")

    def test_windows_backslash_paths_are_normalised(self):
        d = messages.parse_line(r"ERROR: [Synth 8-439] module 'foo' not found [C:\p\rtl\a.v:7]")
        self.assertEqual((d.severity, d.file, d.line), ("error", "C:/p/rtl/a.v", 7))

    def test_severities_and_ids_without_location(self):
        c = messages.parse_line("CRITICAL WARNING: [Vivado 12-4739] set_clock_groups: No valid object(s) found.")
        self.assertEqual((c.severity, c.id, c.file), ("critical_warning", "Vivado 12-4739", None))
        drc = messages.parse_line("WARNING: [DRC NSTD-1] Unspecified I/O Standard: 3 out of 8 logical ports")
        self.assertEqual(drc.id, "DRC NSTD-1")
        self.assertEqual(messages.parse_line("INFO: [Common 17-206] Exiting Vivado.").severity, "info")

    def test_bare_messages_and_noise(self):
        bare = messages.parse_line("ERROR: Tcl command failed")
        self.assertEqual((bare.severity, bare.id, bare.message), ("error", None, "Tcl command failed"))
        for noise in ("", "source x.tcl", "# comment", "Errors: 0", "error: lowercase is not a vivado message"):
            self.assertIsNone(messages.parse_line(noise), noise)

    def test_parse_lines_filters_dedupes_and_limits(self):
        lines = ["INFO: [Common 17-1] hi", "WARNING: [A 1-1] w", "WARNING: [A 1-1] w", "ERROR: [B 2-2] e [f.v:1]"]
        got = messages.parse_lines(lines)
        self.assertEqual([d.id for d in got], ["A 1-1", "B 2-2"])
        self.assertEqual(len(messages.parse_lines(lines, include_info=True)), 3)
        many = [f"WARNING: [A 1-{n}] w{n}" for n in range(100)]
        self.assertEqual(len(messages.parse_lines(many, limit=10)), 10)
