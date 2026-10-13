# upgrade-risk-grader

Grade how risky a dependency upgrade is *before* you run it. The CLI reads a
JSON upgrade plan, classifies each semver bump, weighs breaking-change signals,
and returns a 0–10 score with a level (low/medium/high/critical) and a
recommended action. If you review dependency bumps in CI, this is for you. If
you already run full canary deploys on every commit, you probably don't need it.

<p align="center"><img src="docs/demo.gif" alt="demo" width="720"></p>

## Problem

"Should we take this upgrade?" gets answered by vibes. A `2.0.0` bump with an
announced breaking change and a `1.2.3` patch ride the same merge queue, and
the rollback decision happens during the incident. Release notes, deprecation
notices, and removed-API reports exist, but nothing turns them into a
comparable, defensible number per upgrade.

## How it works

1. **Bump classification** — strict semver parsing of `from`/`to` (prerelease
   and build metadata accepted). Base risk: patch = 1, minor = 2, major = 4.
   Downgrades and same-version entries classify but add no base risk.
2. **Signal weighting** — each declared signal adds a fixed weight:
   `breaking-change-announced` +3, `removed-public-api` +3,
   `renamed-config-keys` +2, `behavior-change-undocumented` +2,
   `deprecation-notices` +1, `security-fix` −1 (it lowers risk *and* raises
   urgency). Unknown signals are reported as warnings, never silently dropped.
3. **Grading** — score is clamped to 0–10: ≤2 low, ≤4 medium, ≤6 high,
   ≤7+ critical. High/critical make the CLI exit 1 for CI gates. A
   `security-fix` signal prefixes the action with `URGENT:` regardless of level.

## Quickstart (~2 min)

```bash
# 30 s: grade one scary major bump (exit 1, critical)
cat > /tmp/plan.json <<'EOF'
{"upgrades": [{"name": "webframework", "from": "1.4.2", "to": "2.0.0",
  "signals": ["breaking-change-announced", "removed-public-api"]}]}
EOF
python upgrade_risk_grader.py /tmp/plan.json

# 30 s: JSON for CI gating
python upgrade_risk_grader.py plan.json --format json

# 1 min: grade a whole 60-upgrade batch
python upgrade_risk_grader.py batch.json
```

## Why not X?

- **Dependabot / Renovate**: they *find and propose* upgrades and read
  release notes as text. They do not emit a per-upgrade risk grade you can
  gate a merge queue on, and their config cannot encode "renamed-config-keys
  in this vendor's minors".
- **k8s-upgrade-assessment** (srinivassrinu842): a strong CLI that connects to
  a live Kubernetes cluster via `kubectl` and uses an LLM to write a
  readiness report. Different layer: it needs a cluster and an LLM key and
  targets one platform's upgrade; this tool is deterministic, offline, and
  works for any semver-versioned dependency.
- **CVE scanners** (osv-scanner, dependency-audit tools): they answer "is
  this version vulnerable?", not "how likely does this upgrade break me?".
  A security fix here is one input signal, not the whole model.

## How this differs from k8s-upgrade-assessment

That project performs an AI-driven Kubernetes upgrade feasibility assessment:
it connects to a real cluster through `kubectl`, collects live state, and
prompts an LLM (provider-agnostic) to generate a Markdown risk report. This
repo inverts the mechanism: no cluster access, no LLM, no API keys — a pure
function of (semver bump, declared signals) so the same plan always yields
the same grade, runnable in a hermetic CI job. The scope is any dependency
with semver versions, not Kubernetes cluster upgrades specifically.

## Performance

[Measured] On the reference laptop (Windows 10, Python 3.13, 2026-10-13):
grading a 300-upgrade plan took **5.3 ms** in-process (warm, median of 50
runs). Cold start adds ~300 ms of interpreter startup. Parsing and grading
are O(n) in upgrade count.

Reproduce:

```bash
python - <<'EOF'
import io, json, time, contextlib, tempfile, os
import upgrade_risk_grader as m
ups=[{"name":"lib-%04d"%i,"from":"1.%d.0"%(i%9),
      "to":"%d.%d.0"%(i%9,(i%9)+1),
      "signals":["deprecation-notices"] if i%3 else []} for i in range(300)]
p=os.path.join(tempfile.mkdtemp(),"up.json")
json.dump({"upgrades":ups},open(p,"w",encoding="utf-8",newline=""))
t=time.perf_counter()
for _ in range(50):
    with contextlib.redirect_stdout(io.StringIO()):
        m.main([p,"--format","json"])
print("warm_ms=%.1f"%((time.perf_counter()-t)/50*1000))
EOF
```

## Minimal Fallback

No Python? Print the two tables from `BASE_RISK` and `SIGNAL_WEIGHTS` (they
fit on an index card), score upgrades by hand, and use the clamp rule
"≥7 = don't merge today". The grading rubric is fully specified in this
README; the CLI only automates the arithmetic.

## Design Trade-offs

Priority order: **explainability > recall of signals > precision**. Fixed
integer weights beat a trained model because a rejected merge must be
justifiable to the author ("your bump is major +2 breaking signals = 7"),
and because signals come from humans reading release notes — the model treats
their input as ground truth. The cost: `security-fix` reducing risk may look
odd (it reflects *confidence in the change*, while urgency is handled
separately). We chose two channels over one confusing number.

## Limits & Second-order Effects

- Signal quality is human-dependent: an unnoticed removed API is invisible
  here. The grader can only be as good as the release notes read into it.
- CI gates on this will bias teams toward minor bumps even when the major
  upgrade is the safer long-term move — pair it with an explicit
  "tech-debt budget", not as the sole gate.
- Teams may stop reading release notes and just tick signal boxes, degrading
  the input over time. Rotate who declares signals.

## FAQ

**Q: Why not let an LLM read the release notes?**
A: You can — have it emit the `signals` array, keep this tool as the
deterministic scorer. Splitting extraction (fuzzy) from grading (fixed)
keeps both auditable.

**Q: Does it install or fetch anything?**
A: No. No network, no keys, stdlib only.

**Q: When NOT to use this?**
A: Unversioned or moving-target dependencies (`master` pins, git URLs), or
environments where every upgrade ships behind a full canary anyway — the
grade adds process without adding information there.

## [Core Assumptions]

1. Semver bump magnitude is a meaningful prior for breakage probability.
2. Breaking-change signals are declared by a human or tool that actually
   read the release notes; the grader does not verify them.
3. 0–10 integer scores with four named levels match how merge queues are
   gated; finer granularity would imply false precision.
4. Security fixes carry higher change confidence, justifying the −1 risk
   weight plus a separate urgency channel.

Confidence: **High (≥80%)** that the bump-base ordering (patch < minor <
major) matches industry intuition. **Medium (60–79%)** on the exact signal
weights — they are defensible defaults, not empirical fits; adjust the
dict to your incident history.

*Data and measurements as of 2026-10-13.*

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [cli-help-spec](https://github.com/chenhz01/cli-help-spec) · [code-block-lang-check](https://github.com/chenhz01/code-block-lang-check) · [dependency-depth-budget](https://github.com/chenhz01/dependency-depth-budget)
