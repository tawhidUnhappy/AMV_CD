# AMV_CD

Load the `amv-ops` and `amv-preferences` skills first (.claude/skills/). amv-ops covers how to run
anything (`./amv.sh list`), the code map, the check tools (`regress`, `strip`,
`compare`) and the traps that cost time before. The stage skills (amv-lyric-video and
the ones it links) hold the details for each stage.

- Run commands through `./amv.sh`, not `uv run`. The project .venv is broken, and a
  full sync pulls torch.
- Refactoring: `./amv.sh regress snapshot` before the first edit, `./amv.sh regress
  check` after.
- Look at any footage you pick (`./amv.sh strip`) before calling it done.
- Code only in git. Everything a user makes lives in ONE gitignored folder,
  `workspace/` (+ `config.json`; see amv-ops "Where things live"); never hard-code a show, song
  or machine path in code. Anything with several flavours is a plug-in
  (`amv/plugins/`, drop-ins in `plugins/`).
- Commit and push to main after changes.
