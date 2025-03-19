def _remove_leading_whitespace(text: str) -> str:
    return "\n".join(line.lstrip() for line in text.splitlines())


def chunk_string(text: str, max_chunk_size=1800) -> list[str]:
    lines = text.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        words = line.split(" ")
        for word in words:
            word = word.strip()
            word = word.replace("\n", "")
            if word == "":
                continue
            if current_length + len(word) + 1 <= max_chunk_size:
                current_chunk.append(word)
                current_length += len(word) + 1
            else:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = len(word)

        if current_chunk:
            current_chunk[-1] += "  \n"
            current_length += 1

        if current_length > max_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return [_remove_leading_whitespace(chunk).replace("\n\n", "\n") for chunk in chunks]


def _fix_quotes(text: str) -> str:
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _format_text_for_discord(text: str) -> list[str]:
    """Format text for discord"""
    text = _fix_quotes(text)
    chunked_text = chunk_string(text)
    return chunked_text
