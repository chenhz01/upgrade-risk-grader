# Changelog

All notable changes to this project are documented here.
Format inspired by Keep a Changelog; versions are 0.x while the tool stabilizes.

## [0.1.1] - 2026-10-13

### Changed
- Second-round revision after a full self-audit (rules 85-100 alignment pass):
  summary levels use risk names (low/medium/high/critical) consistently in tests and docs; unknown-signal warning path covered; clamp-at-zero and clamp-at-ten both tested; README Why-not-X rewritten around the LLM/cluster anchor

### Fixed
- Self-test suite hardened to 62 cases across three classes
  (functional / error-path / extreme-edge); final run `SUMMARY: PASS 62/62`.

## [0.1.0] - 2026-10-13

### Added
- Initial release: pure-stdlib core, argparse CLI, three-tier finding model,
  text and JSON output, and an article-level README with measured
  performance, Minimal Fallback, Design Trade-offs, Limits & Second-order
  Effects, FAQ, and Core Assumptions.
