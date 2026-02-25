# lecture-to-obsidian

Convert lecture recordings into structured Obsidian notes using Whisper transcription and LLM summarization.

## How It Works

1. Feed it an audio file (mp3, m4a, wav, etc.)
2. OpenAI Whisper transcribes the audio
3. GPT-4o-mini condenses the transcript into structured Markdown notes (headings, definitions, LaTeX math)
4. Two files land in your Obsidian vault:
   - A summary note in your Inbox
   - The raw transcript in Source Materials

## Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- [ffmpeg](https://ffmpeg.org/) installed and on your PATH

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/yourname/lecture-to-obsidian.git
cd lecture-to-obsidian

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Add your OpenAI API key
echo "OPENAI_API_KEY=sk-..." > .env

# 4. Create your config
python cli.py init
```

## Quick Start

```bash
# Set up your config interactively (once)
python cli.py init

# Process a lecture recording
python cli.py process lecture.mp3 --title "Lecture 12 - Graph Theory" --course COMP182

# Optional: specify a date (defaults to today)
python cli.py process lecture.m4a --title "Midterm Review" --date 2026-02-20
```

After running, check your Obsidian vault — two new notes will be waiting.

## CLI Reference

### `python cli.py process <audio_file>`

| Option | Default | Description |
|--------|---------|-------------|
| `--title` | filename stem | Title of the note |
| `--course` | (none) | Course code/name added as a tag |
| `--date` | today | Date header in YYYY-MM-DD format |

### `python cli.py init`

Interactive setup wizard that writes `config.yaml`.

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
2026-02-24

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

Copy `config.yaml.example` to `config.yaml` (or run `python cli.py init`):

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
```

## Cost Estimate

| Step | Model | Cost |
|------|-------|------|
| Transcription | whisper-1 | ~$0.006 / minute of audio |
| Summarization | gpt-4o-mini | ~$0.01–0.05 per lecture |

A typical 50-minute lecture costs roughly **$0.35–0.40 total**.

## Large Files

Files over 25 MB (the Whisper API limit) are automatically split into chunks using `pydub`, transcribed in parts, and reassembled. No action needed on your part.

## Troubleshooting

**`ffmpeg not found`** — Install ffmpeg (see Prerequisites above).

**`OPENAI_API_KEY is not set`** — Create a `.env` file: `echo "OPENAI_API_KEY=sk-..." > .env`

**`config.yaml not found`** — Run `python cli.py init` to generate it.

**Vault path doesn't exist** — The tool will warn you and write files to the current directory instead. Move them to your vault manually, or correct the path in `config.yaml`.
