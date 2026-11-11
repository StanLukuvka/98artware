# CLAUDE.md

Read [AGENTS.md](AGENTS.md) before working here. It has the layout, the shell setup, the test
and lint commands, and the house rules. The ones most easily broken:

- Never copy anything from `work/` into the repo, commit it or upload it. Windows 98 product
  keys are public, not secrets; `work/` stays out because it holds installed copies of Windows.
- Don't change prep or the `ready` snapshot without asking.
- Ask before committing. Never push, switch branches, stash or reset unless asked.
- No AI attribution in commits, PRs, code or docs.
- Only base Windows 98 SE programs are in scope; audio is deferred.

Why things are built as they are: [docs/design/decisions.md](docs/design/decisions.md).
What is built and what is next: [docs/status.md](docs/status.md).
