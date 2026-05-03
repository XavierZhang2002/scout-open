"""
Scout — File Operation Tools

- count_tokens: Retained as internal function, no longer exposed as MCP tool (merged into get_file_info call chain)
- get_file_info: Added reading_strategy field, auto-recommends reading strategy
- normalize_file_lines: Unchanged
- Added _suggest_reading_strategy: Recommends reading strategy based on file characteristics

"""

import os
import re
import shutil
from typing import Dict, Any, Optional

from loguru import logger


# ── Constants ──────────────────────────────────────────────────────────────

LINE_MAX_LENGTH = 2000  # Maximum characters per line

# Token thresholds (for strategy recommendation)
SMALL_FILE_TOKEN_THRESHOLD = 30000  # Small file: can be read in full
LARGE_FILE_TOKEN_THRESHOLD = 100000  # Large file: only Grep search recommended

# Encoder cache
_encoder_cache: Dict[str, Any] = {}


# ── Internal Function: Token Counting (no longer exposed as MCP tool) ────────


def _get_encoder(model: str = "deepseek-chat"):
    """Get and cache the tokenizer encoder."""
    if model not in _encoder_cache:
        import tiktoken

        try:
            _encoder_cache[model] = tiktoken.encoding_for_model(model)
            logger.debug(f"Using {model} encoding.")
        except Exception:
            _encoder_cache[model] = tiktoken.get_encoding("cl100k_base")
            logger.debug(f"Model {model} not found, using cl100k_base encoding.")
    return _encoder_cache[model]


def count_tokens(text: str, model: str = "deepseek-chat") -> int:
    """Internal function: Count tokens.

    Called internally by get_file_info, workspace, etc.; no longer registered as MCP tool.
    Uses encoder caching for improved performance.
    """
    enc = _get_encoder(model)
    return len(enc.encode(text, disallowed_special=()))


# ── File Metadata ────────────────────────────────────────────────────────────


def get_file_metadata(file_path: str) -> Dict[str, Any]:
    """Get file metadata (size and basic statistics).

    Returns:
        dict: Contains file_size_bytes, exists, etc.
    """
    if not os.path.exists(file_path):
        return {
            "exists": False,
            "file_path": file_path,
            "error": "File does not exist",
        }

    file_size = os.path.getsize(file_path)

    return {
        "exists": True,
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_kb": file_size / 1024,
        "file_size_mb": file_size / (1024 * 1024),
    }


# ── Long Line Detection ──────────────────────────────────────────────────


def check_long_lines(
    file_path: str,
    max_length: int = LINE_MAX_LENGTH,
    max_lines_to_check: int = 10000,
) -> bool:
    """Detect whether a file contains excessively long lines.

    Args:
        file_path: Path to the file
        max_length: Maximum line length threshold
        max_lines_to_check: Maximum number of lines to check (performance safeguard)

    Returns:
        bool: True indicates excessively long lines exist
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if len(line) > max_length:
                    return True
                if i >= max_lines_to_check:
                    break
        return False
    except Exception as e:
        logger.error(f"Error checking long lines in {file_path}: {e}")
        return False


# ── File Normalization (Long Line Splitting) ────────────────────────────────


def normalize_file_lines(
    source_path: str, max_len: int = LINE_MAX_LENGTH
) -> Dict[str, Any]:
    """Split excessively long lines in a file into reasonable lengths (in-place modification).

    Splitting strategy:
    1. Prefer breaking at sentence separators
    2. Then at spaces/commas
    3. Finally hard-split

    Args:
        source_path: Path to the file
        max_len: Maximum length per line

    Returns:
        dict: Operation result
    """
    if not os.path.exists(source_path):
        return {"success": False, "error": f"File {source_path} not found"}

    temp_path = source_path + ".tmp_normalized"
    modified = False

    try:
        with (
            open(source_path, "r", encoding="utf-8", errors="replace") as f_in,
            open(temp_path, "w", encoding="utf-8") as f_out,
        ):
            for line in f_in:
                line = line.rstrip()
                if not line:
                    f_out.write("\n")
                    continue

                if len(line) <= max_len:
                    f_out.write(line + "\n")
                else:
                    modified = True
                    current_pos = 0
                    total_len = len(line)

                    while current_pos < total_len:
                        end_pos = min(current_pos + max_len, total_len)
                        chunk = line[current_pos:end_pos]

                        if end_pos == total_len:
                            f_out.write(chunk + "\n")
                            break

                        # Search for a natural break point in the last 20% region
                        lookback_limit = int(max_len * 0.2)
                        search_area = chunk[-lookback_limit:]

                        split_offset = -1

                        # Priority 1: Sentence separators
                        match = re.search(r"[.!?。？！](\s|$)", search_area)
                        if match:
                            split_offset = (len(chunk) - lookback_limit) + match.end()
                        else:
                            # Priority 2: Spaces or commas
                            match_space = re.search(r"[,\s]", search_area)
                            if match_space:
                                split_offset = (
                                    len(chunk) - lookback_limit
                                ) + match_space.end()

                        if split_offset != -1:
                            actual_end = current_pos + split_offset
                            f_out.write(line[current_pos:actual_end].strip() + "\n")
                            current_pos = actual_end
                        else:
                            f_out.write(chunk + "\n")
                            current_pos += max_len

        if not modified:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {
                "success": True,
                "modified": False,
                "message": f"File did not contain lines exceeding {max_len} chars. No normalization needed.",
            }

        shutil.move(temp_path, source_path)
        return {
            "success": True,
            "modified": True,
            "file_path": source_path,
            "message": "Successfully normalized file in-place.",
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error(f"Error normalizing file {source_path}: {e}")
        return {"success": False, "error": str(e)}


# ── Token Estimation ────────────────────────────────────────────────────────


def estimate_tokens_from_sample(
    file_path: str,
    token_counter_func=None,
    sample_size: int = 10000,
) -> int:
    """Estimate total file tokens through sampling.

    Args:
        file_path: Path to the file
        token_counter_func: Token counting function (defaults to internal count_tokens)
        sample_size: Sample size in bytes

    Returns:
        int: Estimated total token count
    """
    if token_counter_func is None:
        token_counter_func = count_tokens

    try:
        file_size = os.path.getsize(file_path)
        sample_size = min(sample_size, file_size)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(sample_size)

        sample_tokens = token_counter_func(sample)
        sample_bytes = len(sample.encode("utf-8"))

        if sample_bytes > 0:
            return int((file_size / sample_bytes) * sample_tokens)
        else:
            return 0
    except Exception as e:
        logger.error(f"Error estimating tokens for {file_path}: {e}")
        return 0


# ── Reading Strategy Recommendation ─────────────────────────


def suggest_reading_strategy(
    estimated_tokens: int,
    needs_norm: bool,
    small_threshold: int = SMALL_FILE_TOKEN_THRESHOLD,
    large_threshold: int = LARGE_FILE_TOKEN_THRESHOLD,
) -> Dict[str, Any]:
    """Recommend a reading strategy based on file characteristics.

    Args:
        estimated_tokens: Estimated token count
        needs_norm: Whether normalization is needed
        small_threshold: Small file threshold (below this, full read is acceptable)
        large_threshold: Large file threshold (above this, only Grep is recommended)

    Returns:
        dict: Contains approach, warnings, recommended_steps

    """
    strategy: Dict[str, Any] = {
        "approach": "",
        "warnings": [],
        "recommended_steps": [],
    }

    if needs_norm:
        strategy["warnings"].append("File contains excessively long lines, must normalize first")
        strategy["recommended_steps"].append("1. Call normalize_document")

    if estimated_tokens < small_threshold:
        strategy["approach"] = "full_read"
        strategy["recommended_steps"].append("Can Read the full file directly (low token count)")
    elif estimated_tokens < large_threshold:
        strategy["approach"] = "grep_then_read"
        strategy["recommended_steps"].append(
            "Recommended: Grep to locate -> Read(offset, limit) for targeted reading"
        )
    else:
        strategy["approach"] = "grep_only"
        strategy["recommended_steps"].append("File too large, strongly recommend using only Grep search")
        strategy["warnings"].append(
            f"Estimated {estimated_tokens} tokens; full-file reading will consume significant quota"
        )

    return strategy
