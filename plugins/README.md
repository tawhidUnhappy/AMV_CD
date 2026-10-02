# Your own plug-ins

Every `*.py` file or package (a folder with `__init__.py`) in this folder is
loaded when `./amv.sh` starts. Names starting with `_` or `.` are skipped.
`./amv.sh plugins` lists everything that loaded, and anything that failed (a
broken plug-in is reported and skipped, never fatal). `$AMV_PLUGINS` points
the loader at another folder.

A plug-in registers itself on import:

```python
from amv.plugins import register, Command
register("command", Command("my-tool", "my_package.my_tool", "what it does", group="extras"))
```

The kinds, and what each one describes (full field list in
`amv/plugins/_kinds.py`):

| kind          | object        | built-in examples                                  |
|---------------|---------------|----------------------------------------------------|
| `command`     | `Command`     | `amv/plugins/commands/` (every `./amv.sh` command) |
| `tool`        | `Tool`        | an isolated uv env per worker: `demucs`, `faster_whisper` |
| `separator`   | `Separator`   | `amv/plugins/demucs/` - voices out of dialogue     |
| `transcriber` | `Transcriber` | `amv/plugins/faster_whisper/` - dub word timings   |
| `song_fx`     | `SongFx`      | `amv/plugins/song_fx/` - slowed_reverb, nightcore  |
| `video_fx`    | `VideoFx`     | `amv/plugins/video_fx/` - outline, glow, grain     |

A plug-in with the same kind and name as a built-in replaces it. One shipped
as its own Python package registers through an entry point in the
`amv.plugins` group instead of living here:

```toml
[project.entry-points."amv.plugins"]
my_plugin = "my_package.amv_plugin"
```

`_example_video_fx.py` is a complete example - rename it without the `_` to
try it.

**Engines.** config.json picks which `separator` / `transcriber` runs
(`"separator": "demucs"`; empty = the first installed) and holds each one's
settings under `separators` / `transcribers` by name. A new engine that needs
heavy packages brings a `tool`: its packages are installed into their own
`uv run --with ...` environment on first use, never into the project's, and
its worker script runs there (see `amv/plugins/demucs/`).
