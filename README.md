# lecture2obsidian

Convert lecture recordings into structured Obsidian notes using local Whisper transcription and LLM summarization. Trigger it instantly from a Raycast keyboard shortcut — no terminal required.

## How It Works

**Live recording mode (primary):**
1. Hit a Raycast shortcut → recording starts from your Mac's mic in the background
2. Hit it again → recording stops; the pipeline runs automatically:
   - faster-whisper transcribes the audio locally (no API call)
   - GPT-4o-mini condenses the transcript into structured Markdown notes
   - Two files land in your Obsidian vault: a summary note and the raw transcript
   - A macOS notification tells you when it's ready

**Batch mode (for existing recordings):**
- Pass any audio file (mp3, m4a, wav, etc.) directly to the `process` command

## Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys) (for summarization)
- [ffmpeg](https://ffmpeg.org/) installed and on your PATH
- [Raycast](https://www.raycast.com/) (optional, for keyboard shortcut)

```bash
# macOS
brew install ffmpeg
```

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/yourname/lecture-to-obsidian.git
cd lecture-to-obsidian

# 2. Create a virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Add your OpenAI API key
echo "OPENAI_API_KEY=sk-..." > .env

# 4. Create your config
python -m app.cli init
```

On first use, faster-whisper will download the `base.en` model (~150 MB) to `~/.cache/huggingface/`. Subsequent runs use the cached model.

## Raycast Setup

1. Open Raycast → Settings → Extensions → Script Commands
2. Click **Add Directory** and select the `scripts/` folder in this repo
3. Assign a keyboard shortcut to **Toggle Lecture Recording**
4. Optionally assign one to **Lecture Recording Status**

That's it. The shortcut toggles recording on/off; you'll get a macOS notification when your notes are ready.

## CLI Reference

### Live recording

```bash
# Start or stop recording (detects course from your schedule automatically)
python -m app.cli toggle

# Override course and title
python -m app.cli toggle --course "CS 301" --title "Lecture 12 - Graph Theory"

# Check recording status and elapsed time
python -m app.cli status
```

### Batch processing

```bash
# Process an existing audio file
python -m app.cli process lecture.mp3 --title "Lecture 12 - Graph Theory" --course COMP182

# Optional: specify a date (defaults to today)
python -m app.cli process lecture.m4a --title "Midterm Review" --date 2026-02-20
```

### Setup

```bash
python -m app.cli init
```

## Example Output

**Raw transcript excerpt (input):**
```
okay so today we're going to be talking about um graph theory, specifically
shortest path algorithms. so, uh, last time we covered BFS which gives us
shortest paths in unweighted graphs but today we want to handle weighted
edges so we need Dijkstra's algorithm. so the idea is basically we maintain
a priority queue...
```

**Summary note (output):**
```markdown
2026-02-25

Status: #review

Tags: [[COMP182]]

Transcript: [[Lecture 12 - Graph Theory - Transcript]]

# Lecture 12 - Graph Theory

## Shortest Path Algorithms

- BFS finds shortest paths in unweighted graphs (covered previously)
- Weighted edges require a different approach

### Dijkstra's Algorithm

**Definition:** Dijkstra's Algorithm — a greedy algorithm that finds the shortest
path from a source vertex to all other vertices in a weighted graph with
non-negative edge weights.

**Key idea:** Maintain a min-priority queue of vertices ordered by their
current tentative distance from the source.
...
```

## Configuration

Copy `config.yaml.example` to `config.yaml` (or run `python -m app.cli init`):

```yaml
vault:
  path: "/path/to/your/obsidian/vault"
  inbox_folder: "1 - Inbox"
  source_folder: "2 - Source Materials/Lectures"

summarization:
  model: "gpt-4o-mini"
  max_section_length: 500

note_template:
  status: "#review"
  tag_style: "wikilink"  # or "hashtag"

transcription:
  backend: "local"       # "local" (faster-whisper) or "api" (OpenAI Whisper)
  local_model: "base.en" # tiny.en, base.en, small.en, medium.en

recording:
  archive_dir: "~/recordings"  # omit to delete WAV after processing

# Auto-detect course from your class schedule
schedule:
  Monday:
    - time: "09:00-10:15"
      course: "CS 301"
      title_prefix: "Data Structures"
  Tuesday:
    - time: "11:00-12:15"
      course: "CS 350"
      title_prefix: "Operating Systems"
default_course: "Lecture"
```

When `toggle` is called without `--course`, it checks the current day and time against your schedule (with a 15-minute buffer on each end) and fills in the course and title automatically.

## Cost Estimate

Transcription is free — it runs locally with faster-whisper. Only summarization hits the API.

| Step | Model | Cost |
|------|-------|------|
| Transcription | faster-whisper (local) | Free |
| Summarization | gpt-4o-mini | ~$0.01–0.05 per lecture |

A typical 50-minute lecture costs roughly **$0.02–0.05 total**.

To use the OpenAI Whisper API instead (e.g. if you don't want local model storage), set `transcription.backend: api` in `config.yaml`. That adds ~$0.006/minute for transcription.

## Troubleshooting

**`ffmpeg not found`** — Install ffmpeg: `brew install ffmpeg`

**`OPENAI_API_KEY is not set`** — Create a `.env` file: `echo "OPENAI_API_KEY=sk-..." > .env`

**`config.yaml not found`** — Run `python -m app.cli init` to generate it.

**Vault path doesn't exist** — The tool will warn you and write files to the current directory instead.

**Pipeline failed after recording** — Check `~/.lecture-to-obsidian/record.log` for the full traceback. The WAV file is preserved so you can reprocess it manually with `python -m app.cli process <wav_file>`.

**Raycast script hangs** — Make sure the scripts in `scripts/` are executable: `chmod +x scripts/*.sh`
