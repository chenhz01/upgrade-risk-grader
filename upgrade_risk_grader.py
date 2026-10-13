# -*- coding: utf-8 -*-
"""upgrade-risk-grader — grade dependency upgrade risk from semver bump + signals.

Pure standard library. Input: JSON list of planned upgrades. Output: per-upgrade
risk level (low/medium/high/critical), score 0-10, recommended action.
Exit codes: 0 = no high/critical risk, 1 = high or critical present, 2 = input error.
"""
import argparse
import json
import re
import sys

SIGNAL_WEIGHTS = {
    "breaking-change-announced": 3,
    "removed-public-api": 3,
    "renamed-config-keys": 2,
    "behavior-change-undocumented": 2,
    "deprecation-notices": 1,
    "security-fix": -1,
}
BASE_RISK = {"patch": 1, "minor": 2, "major": 4, "downgrade": 0, "same": 0}
LEVELS = ("low", "medium", "high", "critical")
ACTIONS = {
    "low": "include in the routine update train",
    "medium": "apply with the full test suite green; review the diff",
    "high": "staged rollout with a canary and a pinned rollback version",
    "critical": "write a dedicated migration plan; rehearse rollback before applying",
}

_SEMVER = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def parse_semver(text):
    """Return (major, minor, patch, prerelease) or None if not valid semver."""
    m = _SEMVER.match(str(text).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))


def bump_kind(old, new):
    """Classify the version delta: patch/minor/major/downgrade/same/invalid."""
    a, b = parse_semver(old), parse_semver(new)
    if a is None or b is None:
        return "invalid"
    if b[:3] == a[:3]:
        return "same"
    if b < a:
        return "downgrade"
    if b[0] > a[0]:
        return "major"
    if b[1] > a[1]:
        return "minor"
    return "patch"


def validate_upgrade(up, index):
    if not isinstance(up, dict):
        raise ValueError("upgrade #%d must be a JSON object" % index)
    if not isinstance(up.get("name"), str) or not up["name"].strip():
        raise ValueError("upgrade #%d needs a non-empty string 'name'" % index)
    for key in ("from", "to"):
        if not isinstance(up.get(key), str) or not parse_semver(up[key]):
            raise ValueError("upgrade %r: %s=%r is not valid semver"
                             % (up["name"], key, up.get(key)))
    sigs = up.get("signals", [])
    if not isinstance(sigs, list) or not all(isinstance(s, str) for s in sigs):
        raise ValueError("upgrade %r: 'signals' must be a list of strings" % up["name"])
    return up


def grade_upgrade(up, index):
    validate_upgrade(up, index)
    warnings = []
    kind = bump_kind(up["from"], up["to"])
    if kind == "invalid":
        raise ValueError("upgrade %r: unparseable version pair" % up["name"])
    unknown = [s for s in up.get("signals", []) if s not in SIGNAL_WEIGHTS]
    for s in unknown:
        warnings.append("unknown signal %r ignored" % s)
    known = [s for s in up.get("signals", []) if s in SIGNAL_WEIGHTS]
    score = BASE_RISK[kind] + sum(SIGNAL_WEIGHTS[s] for s in known)
    score = max(0, min(10, score))
    if score <= 2:
        level = "low"
    elif score <= 4:
        level = "medium"
    elif score <= 6:
        level = "high"
    else:
        level = "critical"
    urgent = "security-fix" in known
    return {
        "name": up["name"],
        "from": up["from"],
        "to": up["to"],
        "bump": kind,
        "score": score,
        "level": level,
        "action": ("URGENT: security fix - apply now; then " + ACTIONS[level]
                   if urgent else ACTIONS[level]),
        "warnings": warnings,
    }


def analyze(doc):
    if not isinstance(doc, dict):
        raise ValueError("top-level JSON must be an object")
    ups = doc.get("upgrades")
    if not isinstance(ups, list):
        raise ValueError("top-level object needs an 'upgrades' array")
    results = [grade_upgrade(u, i) for i, u in enumerate(ups)]
    counts = {lv: sum(1 for r in results if r["level"] == lv) for lv in LEVELS}
    blocking = counts["high"] + counts["critical"]
    report = {
        "tool": "upgrade-risk-grader",
        "summary": {"upgrades": len(results), "levels": counts, "blocking": blocking},
        "upgrades": results,
        "verdict": ("blocked: %d high/critical upgrades" % blocking if blocking
                    else "upgrade plan within risk budget"),
    }
    return report


def render_text(report):
    lines = ["upgrade-risk-grader report", "=" * 28]
    for r in report["upgrades"]:
        lines.append("%s  %s -> %s  bump=%s  score=%d/10  level=%s"
                     % (r["name"], r["from"], r["to"], r["bump"], r["score"], r["level"]))
        lines.append("    action: %s" % r["action"])
        for w in r["warnings"]:
            lines.append("    warn: %s" % w)
    s = report["summary"]
    lines.append("summary: %d upgrades, levels %s, blocking %d"
                 % (s["upgrades"], "/".join("%s:%d" % (lv, s["levels"][lv]) for lv in LEVELS),
                    s["blocking"]))
    lines.append("verdict: %s" % report["verdict"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="upgrade-risk-grader",
        description="Grade dependency upgrade risk (semver bump x breaking signals).")
    parser.add_argument("file", help="upgrades JSON path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("error: invalid JSON in %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    try:
        report = analyze(doc)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 1 if report["summary"]["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
