import sys
from textwrap import dedent

import openai

# Tokens / words per chunk when splitting long transcripts
_CHUNK_WORDS = 8_000
_OVERLAP_WORDS = 500

_SYSTEM_PROMPT = dedent("""\
    You are an expert note-taker converting a raw lecture transcript into clean, structured study notes.

    Follow these rules exactly:
    - Organize content under clear Markdown headings (##, ###) that mirror the lecture's logical flow.
    - Write definitions using the pattern: **Definition:** <term> — <concise explanation>
    - Convert ALL mathematical expressions to LaTeX: use $...$ for inline math and $$...$$ for display equations.
    - Use bullet points for key ideas, kept concise — capture the concept, not the lecturer's wording.
    - Include important examples but only if they illuminate a concept; skip trivial or repetitive ones.
    - Remove filler words, digressions, repeated explanations, and off-topic remarks entirely.
    - Preserve the logical ordering of topics as they were introduced.
    - Output clean Markdown only. No preamble, no "Here are your notes:", no explanation.
    - Target roughly 20–30% of the original transcript length.
""")

_MERGE_SYSTEM_PROMPT = dedent("""\
    You are merging several partial lecture note summaries into a single coherent set of notes.

    Follow these rules:
    - Merge all sections into one unified document with consistent Markdown headings.
    - Remove any duplicate content — keep the clearest version of each concept.
    - Ensure logical flow matches the original lecture order (earlier chunks come first).
    - Maintain all LaTeX math expressions, bold definitions, and bullet formatting.
    - Output clean Markdown only. No preamble or explanation.
""")


def _word_count(text: str) -> int:
    return len(text.split())


def _chunk_transcript(transcript: str) -> list[str]:
    """Split transcript into overlapping word-level chunks."""
    words = transcript.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + _CHUNK_WORDS
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - _OVERLAP_WORDS
    return chunks


def _call_llm(system: str, user: str, model: str) -> str:
    """Make a single chat completion call and return the assistant content."""
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content.strip()
    except openai.AuthenticationError:
        print("Error: Invalid OpenAI API key. Check OPENAI_API_KEY in your .env file.")
        sys.exit(1)
    except openai.OpenAIError as e:
        print(f"Error: LLM API call failed — {e}")
        sys.exit(1)


def summarize_transcript(
    transcript: str,
    title: str,
    course: str | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    """Convert a raw lecture transcript into a condensed, structured Markdown summary.

    For transcripts over 10,000 words, the text is split into overlapping chunks,
    each chunk is summarized independently, then a final merge pass produces the
    unified note.

    Args:
        transcript: Full plain-text transcript.
        title: Lecture title (used as context for the LLM).
        course: Optional course name/code for additional context.
        model: OpenAI chat model to use.

    Returns:
        Structured Markdown summary as a string.
    """
    context_header = f"Lecture: {title}"
    if course:
        context_header += f"\nCourse: {course}"

    word_count = _word_count(transcript)

    if word_count <= 10_000:
        user_msg = f"{context_header}\n\n---\n\n{transcript}"
        return _call_llm(_SYSTEM_PROMPT, user_msg, model)

    # Long transcript: chunk → summarize each → merge
    chunks = _chunk_transcript(transcript)
    print(f"  Transcript is {word_count:,} words — summarizing in {len(chunks)} chunks...")

    partial_summaries: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Summarizing chunk {i}/{len(chunks)}...")
        user_msg = (
            f"{context_header}\n"
            f"(Part {i} of {len(chunks)})\n\n"
            "---\n\n"
            f"{chunk}"
        )
        partial_summaries.append(_call_llm(_SYSTEM_PROMPT, user_msg, model))

    print("  Merging chunk summaries into final notes...")
    merge_input = "\n\n---\n\n".join(
        f"## Chunk {i}\n\n{s}" for i, s in enumerate(partial_summaries, 1)
    )
    merge_user_msg = f"{context_header}\n\n---\n\n{merge_input}"
    return _call_llm(_MERGE_SYSTEM_PROMPT, merge_user_msg, model)
