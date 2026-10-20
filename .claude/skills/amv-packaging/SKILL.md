---
name: amv-packaging
description: Thumbnail, title, description and tags for a full AMV / anime edit on YouTube - the cinematic cover (./amv.sh amv-cover), the metadata writer (./amv.sh amv-meta), and the research behind both (what top edit channels do, title/description limits, credits and rights). Use whenever an AMV or edit is finished and needs publishing, or the user asks for a thumbnail, title, description or tags for one. Shorts have their own flow (amv-ops "YouTube Shorts").
---

# Packaging a full AMV (thumbnail, title, description, tags)

Research of 2026-10-20 (sources at the end). The owner pointed at **Toxic AMV**
(@Toxic404Team) and **Molob** (@Molob) as the channels to learn from; their real
metadata (yt-dlp, 12 videos) is summarised here. Shorts (yellow labels + arrows,
`short-thumb`) are a different style; see amv-thumbnails-and-titles for that one.

## Workflow

```bash
./amv.sh amv-cover --edit workspace/global/edits/NAME.json --out workspace/output/edits/NAME   # clean source frames, numbered
#   pick one -> write NAME.cover.json ({"frame": {"file", "at"}, "title", "style", "side", ...})
./amv.sh amv-cover workspace/output/edits/NAME.cover.json      # thumb.jpg + thumb_review.jpg (full + phone size)
./amv.sh amv-meta  workspace/output/edits/NAME.meta.json       # title.txt, titles.txt, description.txt, tags.txt
```

Read `thumb_review.jpg` before calling it done: the lower half is the 168x94 phone
size x3. If the words or the face don't read there, they don't read.

## Thumbnail (amv-cover)

What the reference channels do:
- **Molob (fits our tools):** ONE real frame from the edit, one character, heavily
  graded (bloom, glow, light rays, chromatic fringe, crushed blacks), and either no
  text or **1-2 huge words** in a metallic/3D style ("SICKO MODE", "STARK EDIT",
  "SHINRA"). Character close-ups or a strong pose.
- **Toxic AMV:** commissioned, illustrated key art with "TOXIC" branding, often
  sexualised characters. Not reproducible from frames and not a look to copy -
  don't.

Rules (research; the vidIQ study of 500 breakout videos is the best data):
- A **face** (69% of breakout thumbnails had one; 80% of the biggest), **high
  contrast** (56%). Expressive faces beat calm ones.
- **0-3 words** (median of thumbnails with text: 5; guides say 3-4 max). For an AMV:
  the song title or one emotional word, plus at most a small "RE:ZERO AMV" line.
- Design for **168x94** (phone): one subject, at most ~3 visual elements.
- Words go **beside** the face, never over it (`side`, capped at 48% of the width);
  keep the **bottom-right** clear (duration badge).
- Real frames only: from the SOURCE (`--edit`), not the finished render - a render
  frame carries glitch blocks, burned-in words and letterbox bars.
- Never a frame with fanservice involving a minor (amv-preferences per-show notes);
  don't sexualise.
- YouTube's Test & Compare (up to 3 thumbnails) beats any rule: make 2-3 covers
  (different frame / style) and let real viewers pick.

Cover spec keys: `frame` {file, at} | {video, t} | {image}, `zoom`, `center`, `flip`,
`title` ("\n" for two lines), `sub`, `style` chrome/gold/red/ice/violet (match the
edit's palette), `side` left/right/top/bottom, `size`, `max_width`, `y`, `grade`
{contrast, saturation, bloom, rays, rays_from [x, y], fringe, vignette, sharpen}.

## Title (amv-meta writes candidates; pick and adjust)

Real patterns:
- Toxic AMV: `Artist - Song (Toxic AMV)`, or with a story hook
  `AI GIRL IS BULLYING ME | angelhard - Cool (Hardtekk - Slowed) | Toxic AMV`,
  `Damn It, I Can't Move My Body... SWITCH! | isq - pursuit (super slowed) | Toxic AMV`.
  Remix tags in brackets: (Slowed), (Super Slowed), (Sped Up), (Hardtekk), (Jumpstyle).
- Molob: `Character - Song Edit`, `Anime – Song | Anime EDIT`, and curiosity titles
  for long-form ("This Infinity Castle EDIT Took Me 20+ Hours" - 297k views).

Rules:
- 100 characters max; **phones show ~40-60**: anime + song (or the hook) in the first ~55.
- Our default: `<Hook> | <Anime> AMV - <Song>` or `<Anime> AMV - <Song>`; a character
  edit: `<Character> - <Song> Edit | <Anime> AMV`.
- At most one `!`/`?`, no emoji, no clickbait the video doesn't deliver.
- Owner's titles follow what the DUB/scene actually says (amv-preferences).

## Description

Real patterns: both channels open with one line (Molob: a lowercase keyword line,
"stark FUNK SERENO amv"), then the song credit with links (Toxic: Spotify + the
artist's socials), the anime list (Toxic: "Re:ZERO (AMV)" one per line), their own
links, a rights block, and hashtags.

Rules (amv-meta follows them):
1. First ~150 characters say what it is - shown in search and before "Show more".
2. Song credit. **Never invent one.** Unknown artist = `<ARTIST>` placeholder and say
   so. An ACE-Step song is credited as an original AI-generated track (honest, and
   it explains why there is no Content ID claim).
3. Anime list, one per line, "(AMV)" after each (Toxic style; helps search).
4. Rights: "Anime footage © <owner or 'its respective owners'>. A non-commercial fan
   edit." Do NOT write "all under fair use" as if it were settled - crediting and
   disclaimers are not permission (YouTube says so); fair use is decided case by case.
5. 3 hashtags at the end (#amv #<anime> #animeedit): YouTube shows the first three
   above the title. 15 is the hard cap; more looks spammy.
6. Chapters only if there are 3+ real sections (00:00 first) - an AMV rarely needs them.
- Length: 200-500 words is plenty; 5000 is the hard limit.

## Tags
Under 500 characters, most specific first: `<anime> amv`, `<anime> edit`,
`<character> edit`, full anime names, `amv`, `anime edit`, `anime music video`,
style (`phonk edit`, `flow edit`), song. Toxic adds the full title as a tag and
each anime as "<Anime> (AMV)"; Molob adds popular-character tags of other shows
(gojo edits, luffy edit) - don't: tags about content that isn't in the video are
misleading metadata (YouTube spam policy).

## Rights and music
- Label songs (Content ID): the owner usually gets the monetisation, sometimes the
  video is blocked; credits don't change that. ACE-Step songs are ours (MIT model).
- AI disclosure: YouTube asks creators to label realistic altered/synthetic
  content. An AI-generated song is disclosed in the description anyway; tick the
  "altered or synthetic content" box if a voice imitates a real person (we never
  ask for a named singer's voice - amv-song-gen).

## Sources
- vidIQ breakout-thumbnail study: https://vidiq.com/blog/post/youtube-thumbnail-design-tips/
- Thumbnail guides (vendor blogs, weaker): https://awisee.com/blog/youtube-thumbnail-best-practices/ ·
  https://www.thumbmagic.co/blog/thumbnail-design-principles · https://notelm.ai/blog/youtube-thumbnail-design-tips
- Title length: https://www.10xcreator.dev/blog/best-youtube-title-length/ · https://fluxnote.io/guides/youtube-title-character-limit-2026
- Descriptions: https://wildandfreetools.com/blog/youtube-description-best-practices-length-format/ ·
  https://touhfa.art/blog/seo/youtube-description-guide/
- Rights: https://www.peepstune.com/how-to-make-an-anime-music-video-a-complete-amv-workflow/ ·
  https://www.animemusicvideos.org/forum/viewtopic.php?t=131167
- Channels: https://www.youtube.com/@Toxic404Team · https://www.youtube.com/@Molob (metadata via yt-dlp)

## Maintenance
New symptom -> cause -> rule lines go here, with the date.
