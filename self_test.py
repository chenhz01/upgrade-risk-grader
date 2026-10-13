# -*- coding: utf-8 -*-
"""self_test for upgrade-risk-grader — inherits v2 template four defenses:
SystemExit capture / Unicode-safe / Windows newline / SUMMARY last line."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

import upgrade_risk_grader as mod

TMP = tempfile.mkdtemp(prefix="urg_selftest_")
_n = [0]


def write_doc(obj):
    _n[0] += 1
    path = os.path.join(TMP, "up_%d.json" % _n[0])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = mod.main(argv) or 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def up(**kw):
    base = {"name": "lib", "from": "1.2.0", "to": "1.2.1", "signals": []}
    base.update(kw)
    return base


class TestAFunctional(unittest.TestCase):
    def test_patch_low_exit0(self):
        p = write_doc({"upgrades": [up()]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_text_contains_name_and_levels(self):
        p = write_doc({"upgrades": [up(name="requests", to="1.3.0")]})
        code, out, _ = run_cli([p])
        self.assertIn("requests", out)
        self.assertIn("minor", out)

    def test_json_format_parseable(self):
        p = write_doc({"upgrades": [up()]})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out), dict)

    def test_major_bump_base4(self):
        r = mod.grade_upgrade(up(to="2.0.0"), 0)
        self.assertEqual((r["bump"], r["score"]), ("major", 4))

    def test_minor_bump_base2(self):
        r = mod.grade_upgrade(up(to="1.3.0"), 0)
        self.assertEqual((r["bump"], r["score"]), ("minor", 2))

    def test_patch_bump_base1(self):
        r = mod.grade_upgrade(up(to="1.2.3"), 0)
        self.assertEqual((r["bump"], r["score"]), ("patch", 1))

    def test_breaking_signal_adds_three(self):
        r = mod.grade_upgrade(up(to="1.3.0", signals=["breaking-change-announced"]), 0)
        self.assertEqual(r["score"], 5)

    def test_removed_api_adds_three(self):
        r = mod.grade_upgrade(up(to="1.3.0", signals=["removed-public-api"]), 0)
        self.assertEqual(r["score"], 5)

    def test_security_fix_reduces_one_but_urgent(self):
        r = mod.grade_upgrade(up(to="1.2.2", signals=["security-fix"]), 0)
        self.assertEqual(r["score"], 0)
        self.assertIn("URGENT", r["action"])

    def test_major_plus_all_signals_critical(self):
        r = mod.grade_upgrade(up(to="2.0.0", signals=[
            "breaking-change-announced", "removed-public-api",
            "renamed-config-keys", "behavior-change-undocumented"]), 0)
        self.assertEqual(r["level"], "critical")  # 4+3+3+2+2=10 (clamped)

    def test_exit1_on_high(self):
        p = write_doc({"upgrades": [up(to="2.0.0",
                                       signals=["breaking-change-announced"])]})
        code, _, _ = run_cli([p])
        self.assertEqual(code, 1)

    def test_exit0_mixed_low_medium(self):
        p = write_doc({"upgrades": [up(), up(name="b", to="1.3.0")]})
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_summary_counts_and_blocking(self):
        p = write_doc({"upgrades": [up(), up(name="b", to="2.0.0",
                                             signals=["breaking-change-announced",
                                                      "removed-public-api"])]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(rep["summary"]["blocking"], 1)
        self.assertEqual(rep["summary"]["levels"]["low"], 1)

    def test_unknown_signal_warns_not_fails(self):
        r = mod.grade_upgrade(up(to="1.3.0", signals=["quantum-leap"]), 0)
        self.assertEqual(r["score"], 2)
        self.assertTrue(any("quantum-leap" in w for w in r["warnings"]))

    def test_prerelease_to_accepts(self):
        r = mod.grade_upgrade(up(to="2.0.0-rc.1"), 0)
        self.assertEqual(r["bump"], "major")

    def test_prerelease_build_metadata(self):
        self.assertIsNotNone(mod.parse_semver("1.2.3+build.5"))

    def test_action_present_all_levels(self):
        for lv in mod.LEVELS:
            self.assertIn(lv, mod.ACTIONS)


class TestBErrors(unittest.TestCase):
    def test_missing_file_exit2(self):
        code, _, err = run_cli([os.path.join(TMP, "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_bad_json_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "bad_%d.json" % _n[0])
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("[oops")
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)

    def test_missing_upgrades_key(self):
        p = write_doc({"items": []})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("upgrades", err)

    def test_upgrades_not_list(self):
        p = write_doc({"upgrades": "all"})
        self.assertEqual(run_cli([p])[0], 2)

    def test_upgrade_not_object(self):
        p = write_doc({"upgrades": [7]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_missing_name(self):
        p = write_doc({"upgrades": [{"from": "1.0.0", "to": "1.0.1"}]})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("name", err)

    def test_invalid_from_semver(self):
        p = write_doc({"upgrades": [{"name": "lib", "from": "v1", "to": "1.0.1"}]})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("semver", err)

    def test_invalid_to_semver(self):
        p = write_doc({"upgrades": [up(to="one.two.three")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_signals_not_list(self):
        p = write_doc({"upgrades": [up(signals="breaking-change-announced")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_signal_not_string(self):
        p = write_doc({"upgrades": [up(signals=[3])]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_empty_name_exit2(self):
        p = write_doc({"upgrades": [up(name=" ")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_unknown_format_exit2(self):
        p = write_doc({"upgrades": []})
        self.assertEqual(run_cli([p, "--format", "yaml"])[0], 2)

    def test_no_args_exit2(self):
        self.assertEqual(run_cli([])[0], 2)

    def test_empty_file_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "empty_%d.json" % _n[0])
        open(p, "w", encoding="utf-8", newline="").close()
        self.assertEqual(run_cli([p])[0], 2)

    def test_directory_input_exit2(self):
        self.assertEqual(run_cli([TMP])[0], 2)

    def test_top_level_list_exit2(self):
        p = write_doc([up()])
        self.assertEqual(run_cli([p])[0], 2)


class TestCEdge(unittest.TestCase):
    def test_empty_plan_exit0(self):
        p = write_doc({"upgrades": []})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual((code, json.loads(out)["summary"]["upgrades"]), (0, 0))

    def test_unicode_name(self):
        p = write_doc({"upgrades": [up(name="\u5347\u7ea7\u5305A")]})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("\u5347\u7ea7\u5305A", out)

    def test_very_long_name(self):
        p = write_doc({"upgrades": [up(name="x" * 8000)]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("x" * 100, out)

    def test_downgrade_detected(self):
        r = mod.grade_upgrade(up(to="1.1.9"), 0)
        self.assertEqual(r["bump"], "downgrade")

    def test_same_version_same(self):
        r = mod.grade_upgrade(up(to="1.2.0"), 0)
        self.assertEqual(r["bump"], "same")

    def test_huge_version_numbers(self):
        self.assertEqual(mod.parse_semver("999999.999999.999999")[:3],
                         (999999, 999999, 999999))

    def test_duplicate_names_kept(self):
        p = write_doc({"upgrades": [up(), up()]})
        _, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(len(json.loads(out)["upgrades"]), 2)

    def test_extra_fields_ignored(self):
        r = mod.grade_upgrade(up(note={"deep": [1, 2, 3]}), 0)
        self.assertEqual(r["level"], "low")

    def test_many_upgrades_performance_shape(self):
        p = write_doc({"upgrades": [up(name="l%d" % i, to="1.%d.0" % i)
                                    for i in range(60)]})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["upgrades"], 60)

    def test_clamp_at_zero(self):
        r = mod.grade_upgrade(up(to="1.2.2", signals=["security-fix",
                                                      "security-fix"]), 0)
        self.assertEqual(r["score"], 0)

    def test_bump_kind_invalid_inputs(self):
        self.assertEqual(mod.bump_kind("abc", "1.0.0"), "invalid")
        self.assertEqual(mod.bump_kind("1.0.0", None), "invalid")


CASES = [
    (up(to="1.2.2"), 1, "low"),
    (up(to="1.2.2", signals=["deprecation-notices"]), 2, "low"),
    (up(to="1.3.0"), 2, "low"),
    (up(to="1.3.0", signals=["deprecation-notices"]), 3, "medium"),
    (up(to="1.3.0", signals=["renamed-config-keys"]), 4, "medium"),
    (up(to="1.2.2", signals=["behavior-change-undocumented"]), 3, "medium"),
    (up(to="1.3.0", signals=["breaking-change-announced"]), 5, "high"),
    (up(to="1.3.0", signals=["removed-public-api"]), 5, "high"),
    (up(to="1.3.0", signals=["breaking-change-announced", "deprecation-notices"]), 6, "high"),
    (up(to="2.0.0"), 4, "medium"),
    (up(to="2.0.0", signals=["deprecation-notices"]), 5, "high"),
    (up(to="2.0.0", signals=["renamed-config-keys"]), 6, "high"),
    (up(to="2.0.0", signals=["breaking-change-announced"]), 7, "critical"),
    (up(to="2.0.0", signals=["removed-public-api"]), 7, "critical"),
    (up(to="2.0.0", signals=["breaking-change-announced", "renamed-config-keys"]), 9, "critical"),
    (up(to="2.0.0", signals=["security-fix"]), 3, "medium"),
    (up(to="1.2.2", signals=["deprecation-notices", "security-fix"]), 1, "low"),
    (up(to="1.3.1", signals=["behavior-change-undocumented", "renamed-config-keys"]), 6, "high"),
]


def _mk(case):
    u, score, level = case

    def test(self):
        r = mod.grade_upgrade(u, 0)
        self.assertEqual(r["score"], score)
        self.assertEqual(r["level"], level)
    return test


for _i, _c in enumerate(CASES):
    setattr(TestCEdge, "test_table_%02d" % _i, _mk(_c))

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))
    sys.exit(0 if fails == 0 else 1)
