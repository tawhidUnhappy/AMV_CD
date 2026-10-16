---
name: amv-blender
description: Install Blender, connect Claude to it (blender-mcp), and guide the user through it; then build scenes, import free assets and keyframe music-synced or looping animation in their live Blender. Use whenever the user mentions Blender, 3D, a scene/model/render, animating to a song, or the Blender MCP tools (mcp__blender__*), or when Blender tools are missing or "not connected".
---

# Blender for Claude (amv-blender)

The user-facing guide is `BLENDER.md` (repo root). This skill covers what to
say, in which order, and how to use the tools. Pieces:
- `./amv.sh blender-setup` (`amv/blender/setup.py`): finds Blender, installs and
  turns on the MCP add-on, online access, 21 free extensions plus Node Wrangler
  and Rigify; `--keys` asks for asset keys with hidden input; `--check` reports
  only. It refuses to run while Blender is open.
- `./amv.sh blender-beats SONG --fps N` (`amv/blender/beats.py`) writes
  `workspace/tmp/blender/<song>.beats.json`.
- `.mcp.json` (repo root): `uvx blender-mcp` with telemetry switched off.

## Guiding the user

The user may be new to all of this. Talk plainly, and do every step you can do
yourself. Hand the user only the steps that need them:
- typing their password (`sudo snap install blender --classic`),
- clicking inside Blender (N → **MCP for Blender** → **Connect to Claude**),
- restarting Claude Code.

Give one step at a time when it needs their hands, and say what they should
see afterwards. When they send a screenshot, read it: say what it shows
("connected on port 9876") and give the next step.

Always start with `./amv.sh blender-setup --check`. It tells you what is done,
so you never re-teach a finished step. The order:

1. **No Blender:** give the install command for their OS (Linux snap / Windows
   winget / macOS brew; the table is in BLENDER.md). For an unusual install
   location, set config.json `"blender"`.
2. **Blender, no add-on:** ask them to close Blender, then run
   `./amv.sh blender-setup` yourself.
3. **Add-on on, not connected:** tell them to open Blender and click
   N → MCP for Blender → Connect to Claude.
4. **No `mcp__blender__*` tools in this session:** the tools only load at session
   start. Tell them to restart Claude Code (VS Code: Ctrl+Shift+P →
   "Developer: Reload Window", or a new chat) and approve the `blender` server.
   Before that, you can still prove the link with a raw socket:
   send `{"type":"get_scene_info","params":{}}` to localhost:9876; the reply is
   JSON.
5. **Connected:** call `get_addon_status`, then `get_scene_info`, make one small
   visible change, `look` at it, and show them.

**Asset keys.** Sketchfab (token at sketchfab.com/settings/password) and Poly
Pizza (poly.pizza/settings/api) are free accounts. Poly Haven needs none.
- Prefer `./amv.sh blender-setup --keys` (Blender closed), or the user pasting
  the keys into the panel.
- If they paste keys in chat: store them yourself, never in the repo or memory,
  and say once that they can regenerate the keys later.
- Store them in the add-on preferences, `sketchfab_api_key` and
  `polypizza_api_key`, then `bpy.ops.wm.save_userpref()`. Live session: through
  `execute_blender_code`. Blender closed: a headless `blender -b --python-expr`.
- Tell them to skip Hyper3D, Hunyuan and "Get Premium" (paid AI generators).

## Using the tools

- Start each session with `get_addon_status`. It shows which libraries are on.
- **Libraries are per file.** `scene.blendermcp_use_polyhaven`,
  `blendermcp_use_sketchfab` and `blendermcp_use_polypizza` are scene
  properties. A new or reopened file has them off, so set them with
  `execute_blender_code` before calling `search_assets`.
- Find shader nodes by type: `n.type == "BSDF_PRINCIPLED"`. Set colours on the
  node inputs; `diffuse_color` only changes the viewport.
- Blender 5.x API (checked on 5.2):
  - the sequencer is `scene.sequence_editor.strips`; `.sequences` is gone;
  - `action.fcurves` is gone. Use
    `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, obj.animation_data.action_slot).fcurves`.
    `keyframe_insert` still works as before.
- `look` after every visible change. Use small `max_size` for quick checks, and
  `mode="frames"` with `frames=[...]` at beat frames to check animation.
- Imported models arrive at arbitrary scale: pass `target_size`, then put them on
  the ground using the reported bounding box.
- Report licences: Sketchfab varies per model, Poly Pizza CC-BY needs credit.
- Before big changes, ask them to save (Ctrl+S). Small changes are fine on an
  unsaved scene.
- The user's viewport is usually in Solid mode. Tell them to press Z →
  Material Preview to see colours.

## Song-synced and repeating animation

1. `./amv.sh blender-beats SONG --fps <scene fps>`. Per beat it gives
   `t`, `frame` and `beat_in_bar` (1 = downbeat). It also lists `onsets`, gives
   `sections` (song structure), and per-frame `envelopes`
   rms/bass/mid/high from 0 to 1, where index i is frame i+1.
2. In Blender:
   - set `scene.render.fps` and `frame_end = frame_count`, and
     `sync_mode = 'AUDIO_SYNC'`;
   - add the song: `sequence_editor.strips.new_sound(name, path, channel, 1)`;
   - read the JSON with `json.load` inside `execute_blender_code`.
3. Pick the right part of the data:

   | Effect | Use |
   | --- | --- |
   | Hits and pulses | `beats` (bigger on `beat_in_bar == 1`): a key at frame−1 (rest), frame (peak), frame+6 to +8 (rest) |
   | Continuous motion | key every frame (or every 2nd) from `envelopes.bass` |
   | Camera cuts, colour changes | `sections` |
   | Drum detail | `onsets` |

4. Repeating loops: animate one bar, then either
   - add a Cycles F-modifier (`fcurve.modifiers.new('CYCLES')` on the channelbag
     fcurves, see above), or
   - push it to the NLA: `animation_data.nla_tracks.new().strips.new(name, start, action)`
     with `.repeat = N`.

   Use offsets between copies for waves (Commotion is installed).
5. Check with `look(mode="frames", frames=[a downbeat, a peak+3, an off-beat])`
   before saying it works. Tell them to press Space to watch with sound.

## Rendering without the GUI (effect edits)

`./amv.sh edit` runs `amv/edit/blender/*.py` with `blender -b --factory-startup
--python SCRIPT -- job.json` - no MCP connection needed. EEVEE works headless
on Linux (5.2: engine id `BLENDER_EEVEE`, ~1 s per 1080x1920 frame); footage
goes in as an image SEQUENCE on emission materials with the Standard view
transform, so the picture's colours stay 1:1. A new script gets the job dict
(in_dir, out_dir, fps, width, height, frames, at, params) and writes
out_dir/#####.png for frames 1..N.

## Traps that cost time before

- Extension sync says "Online access required" → Blender ships with it off → set
  `prefs.system.use_online_access = True` and save. For one CLI run, use
  `blender --online-mode -c extension ...`.
- Headless prefs edits get lost → a running Blender saves its prefs on quit and
  overwrites them → only change prefs headless when Blender is closed. With it
  open, use `execute_blender_code` + `save_userpref()`.
- `--factory-startup=0` made Blender try to open a file → it is a flag with no
  value → plain `blender -b --python-expr`.
- "Connection closed" / "Not connected to Blender" mid-task → Blender was closed,
  no crash log → check port 9876 and `pgrep -x blender` before guessing, then ask
  them to reopen it and Connect. Nothing unsaved survives, so redo the scene work.
- Beats landed on hi-hats → librosa's dB onset curve rates quiet hats like kicks
  → beats.py weights the rise in actual bass loudness ×3.
- One section boundary at 0.2 s → clustering per STFT hop → cluster per beat.
- 117 BPM on a 120 track → tempo bins quantised by the hop → use the median beat
  interval.
- First 2 s had no beats → `beat_track` trims the edges → `trim=False`.
- `AttributeError: 'Action' object has no attribute 'fcurves'` → Blender 5.0
  layered actions → go through the channelbag (Using the tools, above).

## Maintenance

When something new goes wrong here, add a symptom → cause → rule line under
Traps before ending the turn.
