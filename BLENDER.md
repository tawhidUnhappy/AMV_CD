# Blender + Claude

Let Claude build 3D scenes and animation in your own Blender. You describe what
you want; Claude looks at your scene, builds and changes things, imports free
assets, and keyframes animation to a song's beats.

It works through [blender-mcp](https://github.com/ahujasid/blender-mcp), a free
open-source add-on that lets Claude Code talk to a running Blender on your own
computer (port 9876, never over the internet).

You need: [Claude Code](https://claude.com/claude-code), [uv](https://docs.astral.sh/uv/),
and this repo. About 10 minutes.

## 1. Install Blender

| System | Command |
| --- | --- |
| Linux (Ubuntu etc.) | `sudo snap install blender --classic` |
| Windows | `winget install BlenderFoundation.Blender` (or the installer from blender.org) |
| macOS | `brew install --cask blender` (or the .dmg from blender.org) |

Any Blender 4.2 or newer works. If Blender is somewhere unusual, put its path in
`config.json` as `"blender": "/path/to/blender"`.

## 2. Run the setup (Blender closed)

```bash
./amv.sh blender-setup
```

On Windows, run it from Git Bash. **Close Blender first**: Blender saves its
settings when it quits, and would undo the setup. The script refuses to run
while Blender is open.

What it does:
- downloads the MCP add-on and switches it on,
- turns on Blender's online access (needed to download extensions and assets),
- installs 21 free extensions from extensions.blender.org and turns on two
  built-in ones (list at the bottom).

Run `./amv.sh blender-setup --check` at any time to see where you stand. That
one is safe with Blender open.

## 3. Connect Blender

1. Open Blender.
2. In the 3D view, press **N** to open the side panel.
3. Click the **MCP for Blender** tab, then **Connect to Claude**.
   It should say *Connected on port 9876*.

Do this every time you open Blender and want Claude to use it.

## 4. Start Claude Code in this folder

The repo's `.mcp.json` tells Claude Code how to reach Blender. Start (or
restart) Claude Code inside this folder and approve the **blender** server
when asked. The Blender tools only appear in a session that starts after
this, so if Claude says it can't see Blender, restart it.

Check: ask Claude *"what's in my Blender scene?"*. A fresh scene has a Cube,
a Light and a Camera.

## 5. Free asset libraries (optional accounts)

| Library | What | Account |
| --- | --- | --- |
| Poly Haven | HDRI skies/studios, textures, realistic models. All CC0 (free for anything) | none |
| AmbientCG | materials (extension, in Blender) | none |
| Sketchfab | the biggest model library. Licence varies per model, Claude tells you | free: sketchfab.com/signup, token at sketchfab.com/settings/password |
| Poly Pizza | low-poly / cartoon models, CC0 or CC-BY (credit the creator) | free: poly.pizza, key at poly.pizza/settings/api |

To add the keys, close Blender and run `./amv.sh blender-setup --keys`. It asks
for each key with hidden input. Or paste them into the MCP for Blender panel in
Blender. Keys stay in Blender's own settings, never in this repo.

Leave **Hyper3D Rodin**, **Tencent Hunyuan 3D** and **Get Premium** off: those
are AI model generators that mostly cost money.

## 6. Animating to a song

```bash
./amv.sh blender-beats path/to/song.mp3 --fps 30
```

This finds the tempo, every beat (which one is beat 1 of the bar), the drum
hits, where the song changes section, and how loud the bass, mids and highs are
on every frame. Claude reads that file and keyframes from it, so you can just
ask:

- *"Speakers that pump with the bass, lights that flash on every beat, and a
  new camera angle at each section."*
- *"A loop of dancing cubes, 4 bars long, repeating for the whole song."*

Press **Space** in Blender to play it back with the song.

## Privacy

The MCP tool can collect prompts, code and screenshots, but only if you tick
**Allow Telemetry** in its panel. It is off by default, and `.mcp.json` also
switches it off on the server side. Leave it unticked.

Claude runs Python inside your Blender, so it can do anything Blender can.
**Save your file before asking for big changes**, and use Ctrl+Z to undo.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Claude can't see any Blender tools | Restart Claude Code in this folder; approve the `blender` server |
| "Not connected to Blender" | Blender was closed, or Connect wasn't clicked. Open it, N → MCP for Blender → Connect to Claude |
| Extensions / assets won't download | Edit → Preferences → System → **Allow Online Access** (setup turns it on) |
| Setup says "Close Blender first" | Quit Blender completely, run it again |
| Cube colours look grey | Press **Z** in the 3D view → **Material Preview** |
| Sketchfab / Poly Pizza say no key | `./amv.sh blender-setup --keys` with Blender closed |

## Without the script

1. Download `addon.py` from github.com/ahujasid/blender-mcp.
2. Blender → Edit → Preferences → Add-ons → **⌄** (top right) → *Install from
   Disk…* → pick it → tick **MCP for Blender**.
3. Preferences → System → tick **Allow Online Access**. Get Extensions → search
   and install any from the list below.
4. Steps 3–4 above.

## The extensions it installs

All free, from extensions.blender.org.

- **Assets + building:** AmbientCG Material Importer, Extra Mesh Objects, Extra
  Curve Objects, Bagapie (scatter, ivy, random arrays), Place Helper, Bool Tool,
  LoopTools, Dynamic Sky, A.N.T. Landscape.
- **Music timing:** Audio Trigger Lite (drive anything from a BPM grid), Frames
  Per Beat (beat markers), NLA MIDI Copier (sync to MIDI), Simple Audio
  Visualizer, Timeline Audio Visualizer.
- **Motion + loops:** Commotion (staggered offsets), AnimAll, Camera Shakify,
  Handheld Loop, Easeit, Momentum, Randomize Noise Offset.
- **Built in, switched on:** Node Wrangler, Rigify.

Choose your own with `./amv.sh blender-setup --extensions id1,id2`. The ids are
in `amv/blender/setup.py`.
