"""
Chunked TTS generation utilities.

Splits long text into sentence-boundary chunks, generates audio per-chunk
via any TTSBackend, and concatenates with crossfade.  All logic is
engine-agnostic — it wraps the standard ``TTSBackend.generate()`` interface.

Short text (≤ max_chunk_chars) uses the single-shot fast path with zero
overhead.
"""

import asyncio
import logging
import os
import re
import tempfile
import threading
from typing import List, Tuple

import numpy as np

logger = logging.getLogger("voicebox.chunked-tts")

# Default chunk size in characters.  Can be overridden per-request via
# the ``max_chunk_chars`` field on GenerationRequest.
DEFAULT_MAX_CHUNK_CHARS = 800
MAX_RUNAWAY_RETRIES = 2
MIN_RUNAWAY_RETRY_CHARS = 100

# Common abbreviations that should NOT be treated as sentence endings.
# Lowercase for case-insensitive matching.
_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "ave",
        "blvd",
        "inc",
        "ltd",
        "corp",
        "dept",
        "est",
        "approx",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "a.m",
        "p.m",
        "u.s",
        "u.s.a",
        "u.k",
    }
)

# Paralinguistic tags used by Chatterbox Turbo.  The splitter must never
# cut inside one of these.
_PARA_TAG_RE = re.compile(r"\[[^\]]*\]")


def split_text_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> List[str]:
    """Split *text* at natural boundaries into chunks of at most *max_chars*.

    Priority: sentence-end (``.!?`` not preceded by an abbreviation and not
    inside brackets) → clause boundary (``;:,—``) → whitespace → hard cut.

    Paralinguistic tags like ``[laugh]`` are treated as atomic and will not
    be split across chunks.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        remaining = remaining.lstrip()
        if not remaining:
            break
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        segment = remaining[:max_chars]

        # Try to split at the last real sentence ending
        split_pos = _find_last_sentence_end(segment)
        if split_pos == -1:
            split_pos = _find_last_clause_boundary(segment)
        if split_pos == -1:
            split_pos = segment.rfind(" ")
        if split_pos == -1:
            # Absolute fallback: hard cut but avoid splitting inside a tag
            split_pos = _safe_hard_cut(segment, max_chars)

        chunk = remaining[: split_pos + 1].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos + 1 :]

    return chunks


def _find_last_sentence_end(text: str) -> int:
    """Return the index of the last sentence-ending punctuation in *text*.

    Skips periods that follow common abbreviations (``Dr.``, ``Mr.``, etc.)
    and periods inside bracket tags (``[laugh]``).  Also handles CJK
    sentence-ending punctuation (``。！？``).
    """
    best = -1
    # ASCII sentence ends
    for m in re.finditer(r"[.!?](?:\s|$)", text):
        pos = m.start()
        char = text[pos]
        # Skip periods after abbreviations
        if char == ".":
            # Walk backwards to find the preceding word
            word_start = pos - 1
            while word_start >= 0 and text[word_start].isalpha():
                word_start -= 1
            word = text[word_start + 1 : pos].lower()
            if word in _ABBREVIATIONS:
                continue
            # Skip decimal numbers (digit immediately before the period)
            if word_start >= 0 and text[word_start].isdigit():
                continue
        # Skip if we're inside a bracket tag
        if _inside_bracket_tag(text, pos):
            continue
        best = pos
    # CJK sentence-ending punctuation
    for m in re.finditer(r"[\u3002\uff01\uff1f]", text):
        if m.start() > best:
            best = m.start()
    return best


def _find_last_clause_boundary(text: str) -> int:
    """Return the index of the last clause-boundary punctuation."""
    best = -1
    for m in re.finditer(r"[;:,\u2014](?:\s|$)", text):
        pos = m.start()
        # Skip if inside a bracket tag
        if _inside_bracket_tag(text, pos):
            continue
        best = pos
    return best


def _inside_bracket_tag(text: str, pos: int) -> bool:
    """Return True if *pos* falls inside a ``[...]`` tag."""
    for m in _PARA_TAG_RE.finditer(text):
        if m.start() < pos < m.end():
            return True
    return False


def _safe_hard_cut(segment: str, max_chars: int) -> int:
    """Find a hard-cut position that doesn't split a ``[tag]``."""
    cut = max_chars - 1
    # Check if the cut falls inside a bracket tag; if so, move before it
    for m in _PARA_TAG_RE.finditer(segment):
        if m.start() < cut < m.end():
            return m.start() - 1 if m.start() > 0 else cut
    return cut


def concatenate_audio_chunks(
    chunks: List[np.ndarray],
    sample_rate: int,
    crossfade_ms: int = 50,
) -> np.ndarray:
    """Concatenate audio arrays with a short crossfade to eliminate clicks.

    Each chunk is expected to be a 1-D float32 ndarray at *sample_rate* Hz.
    """
    if not chunks:
        return np.array([], dtype=np.float32)
    if len(chunks) == 1:
        return chunks[0]

    crossfade_samples = int(sample_rate * crossfade_ms / 1000)
    result = np.array(chunks[0], dtype=np.float32, copy=True)

    for chunk in chunks[1:]:
        if len(chunk) == 0:
            continue
        overlap = min(crossfade_samples, len(result), len(chunk))
        if overlap > 0:
            fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            result[-overlap:] = result[-overlap:] * fade_out + chunk[:overlap] * fade_in
            result = np.concatenate([result, chunk[overlap:]])
        else:
            result = np.concatenate([result, chunk])

    return result


async def generate_chunked(
    backend,
    text: str,
    voice_prompt: dict,
    language: str = "en",
    seed: int | None = None,
    instruct: str | None = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    crossfade_ms: int = 50,
    trim_fn=None,
    runaway_detector=None,
) -> Tuple[np.ndarray, int]:
    """Generate audio with automatic chunking for long text.

    For text shorter than *max_chunk_chars* this is a thin wrapper around
    ``backend.generate()`` with zero overhead.

    For longer text the input is split at natural sentence boundaries,
    each chunk is generated independently, optionally trimmed (useful for
    Chatterbox engines that hallucinate trailing noise), and the results
    are concatenated with a crossfade (or hard cut if *crossfade_ms* is 0).

    Parameters
    ----------
    backend : TTSBackend
        Any backend implementing the ``generate()`` protocol.
    text : str
        Input text (may be arbitrarily long).
    voice_prompt, language, seed, instruct
        Forwarded to ``backend.generate()`` verbatim.
    max_chunk_chars : int
        Maximum characters per chunk (default 800).
    crossfade_ms : int
        Crossfade duration in milliseconds between chunks.  0 for a hard
        cut with no overlap (default 50).
    trim_fn : callable | None
        Optional ``(audio, sample_rate) -> audio`` post-processing
        function applied to each chunk before concatenation (e.g.
        ``trim_tts_output`` for Chatterbox engines).
    runaway_detector : callable | None
        Optional ``(audio, sample_rate) -> bool`` detector. When it flags
        unstable output, the affected text is split in half and retried.

    A backend may define ``continuation_voice_prompt(voice_prompt, instruct,
    chunk_text, chunk_audio, sample_rate, prompt_path) -> dict | None``. When the
    text needs more than one chunk it is called once, after the first chunk, in a
    worker thread, and a returned prompt replaces *voice_prompt* for every later
    chunk (so an engine can keep the speaker it sampled for chunk 0).
    ``prompt_path`` is an empty ``.wav`` file this function reserves before the
    hook runs; the hook may write its prompt audio there. The reserved file is
    always deleted once generation ends, and the backend's optional
    ``release_continuation_voice_prompt(prompt)`` is called for a returned
    prompt, successfully or not, even when the task is cancelled while the hook
    is still running (the worker thread then cleans up when it finishes).

    Returns
    -------
    (audio, sample_rate) : Tuple[np.ndarray, int]
    """
    async def generate_one(
        chunk_text: str,
        chunk_seed: int | None,
        chunk_prompt: dict,
        retry_depth: int = 0,
    ) -> tuple[np.ndarray, int]:
        chunk_audio, chunk_sr = await backend.generate(
            chunk_text,
            chunk_prompt,
            language,
            chunk_seed,
            instruct,
        )

        if runaway_detector is not None and runaway_detector(chunk_audio, chunk_sr):
            if retry_depth >= MAX_RUNAWAY_RETRIES or len(chunk_text) <= MIN_RUNAWAY_RETRY_CHARS:
                raise RuntimeError(
                    "TTS output remained unstable after retrying smaller text chunks"
                )

            retry_max_chars = max(MIN_RUNAWAY_RETRY_CHARS, len(chunk_text) // 2)
            retry_chunks = split_text_into_chunks(chunk_text, retry_max_chars)
            if len(retry_chunks) <= 1:
                raise RuntimeError("Unable to split unstable TTS output for retry")

            logger.warning(
                "Detected unstable TTS output for %d chars; retrying as %d smaller chunks",
                len(chunk_text),
                len(retry_chunks),
            )
            retry_audio: list[np.ndarray] = []
            for i, retry_text in enumerate(retry_chunks):
                retry_seed = (
                    chunk_seed + ((retry_depth + 1) * 1000) + i
                    if chunk_seed is not None
                    else None
                )
                audio, sample_rate = await generate_one(
                    retry_text,
                    retry_seed,
                    chunk_prompt,
                    retry_depth + 1,
                )
                retry_audio.append(np.asarray(audio, dtype=np.float32))

            return (
                concatenate_audio_chunks(
                    retry_audio,
                    sample_rate,
                    crossfade_ms=crossfade_ms,
                ),
                sample_rate,
            )

        if trim_fn is not None:
            chunk_audio = trim_fn(chunk_audio, chunk_sr)
        return np.asarray(chunk_audio, dtype=np.float32), chunk_sr

    chunks = split_text_into_chunks(text, max_chunk_chars)

    if len(chunks) <= 1:
        # Short text — single-shot fast path
        return await generate_one(text, seed, voice_prompt)

    # Long text — chunked generation
    logger.info(
        "Splitting %d chars into %d chunks (max %d chars each)",
        len(text),
        len(chunks),
        max_chunk_chars,
    )
    audio_chunks: List[np.ndarray] = []
    sample_rate: int | None = None
    chunk_prompt = voice_prompt
    continuation = _ContinuationPrompt(backend)

    try:
        for i, chunk_text in enumerate(chunks):
            logger.info(
                "Generating chunk %d/%d (%d chars)",
                i + 1,
                len(chunks),
                len(chunk_text),
            )
            # Vary the seed per chunk to avoid correlated RNG artefacts,
            # but keep it deterministic so the same (text, seed) pair
            # always produces the same output.
            chunk_seed = (seed + i) if seed is not None else None

            chunk_audio, chunk_sr = await generate_one(
                chunk_text,
                chunk_seed,
                chunk_prompt,
            )

            audio_chunks.append(chunk_audio)
            if sample_rate is None:
                sample_rate = chunk_sr

            if i == 0:
                continuation_prompt = await continuation.request(
                    voice_prompt, instruct, chunk_text, chunk_audio, chunk_sr
                )
                if continuation_prompt is not None:
                    chunk_prompt = continuation_prompt
    finally:
        await continuation.close()

    audio = concatenate_audio_chunks(audio_chunks, sample_rate, crossfade_ms=crossfade_ms)
    return audio, sample_rate


class _ContinuationPrompt:
    """One run's continuation prompt: its reserved temp file and its cleanup.

    The temp file is created on the event-loop side before the backend hook runs
    in a worker thread, so ``close()`` always knows what to delete. A worker
    thread cannot be cancelled: if the task is cancelled while the hook is still
    running, ``close()`` hands the cleanup to that thread, which runs it as soon
    as the hook returns. A lock makes exactly one side clean up.
    """

    def __init__(self, backend) -> None:
        self._backend = backend
        self._lock = threading.Lock()
        self._path: str | None = None
        self._prompt: dict | None = None
        self._started = False
        self._finished = False
        self._closed = False

    async def request(
        self,
        voice_prompt: dict,
        instruct: str | None,
        chunk_text: str,
        chunk_audio: np.ndarray,
        sample_rate: int,
    ) -> dict | None:
        """Ask the backend's optional hook for the prompt later chunks should use."""
        hook = getattr(self._backend, "continuation_voice_prompt", None)
        if not callable(hook):
            return None

        # Reserve the file here, synchronously, so close() can always release it.
        fd, self._path = tempfile.mkstemp(prefix="tts_continuation_", suffix=".wav")
        os.close(fd)
        path = self._path

        def run() -> dict | None:
            with self._lock:
                if self._closed:
                    return None
                self._started = True
            try:
                prompt = hook(voice_prompt, instruct, chunk_text, chunk_audio, sample_rate, path)
                self._prompt = prompt if isinstance(prompt, dict) else None
                return self._prompt
            finally:
                with self._lock:
                    self._finished = True
                    orphaned = self._closed
                if orphaned:
                    self._cleanup()

        # The hook writes a file, so it runs off the event loop.
        return await asyncio.to_thread(run)

    async def close(self) -> None:
        """Release the prompt and delete the reserved file, now or when the hook ends."""
        with self._lock:
            self._closed = True
            if self._started and not self._finished:
                return  # the worker thread cleans up when the hook returns
        if self._path is not None or self._prompt is not None:
            await asyncio.to_thread(self._cleanup)

    def _cleanup(self) -> None:
        prompt, self._prompt = self._prompt, None
        path, self._path = self._path, None
        try:
            release = getattr(self._backend, "release_continuation_voice_prompt", None)
            if prompt is not None and callable(release):
                release(prompt)
        finally:
            if path is not None:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logger.warning("Could not remove the continuation prompt file %s", path, exc_info=True)
