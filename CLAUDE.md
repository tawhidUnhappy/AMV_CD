# AMV_CD

Load the `amv-ops` skill first (.claude/skills/amv-ops/SKILL.md). It covers how to run
anything (`./amv.sh list`), the code map, the check tools (`regress`, `strip`,
`compare`) and the traps that cost time before. The stage skills (amv-lyric-video and
the ones it links) hold the details for each stage.

- Run commands through `./amv.sh`, not `uv run`. The project .venv is broken, and a
  full sync pulls torch.
- Refactoring: `./amv.sh regress snapshot` before the first edit, `./amv.sh regress
  check` after.
- Look at any footage you pick (`./amv.sh strip`) before calling it done.
- Commit and push to main after changes.
