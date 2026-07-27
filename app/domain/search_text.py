from __future__ import annotations

import re
import unicodedata


def normalize_search_text(value: str) -> str:
    """
    Normaliza texto para correspondência semântica determinística.

    A normalização remove acentos, aplica casefold, substitui pontuação
    por espaços e reduz sequências de espaços. Nenhum termo de negócio
    ou lista de palavras ignoradas é definido neste módulo.
    """

    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    casefolded = without_accents.casefold()
    alphanumeric_or_space = "".join(
        character
        if character.isalnum() or character.isspace()
        else " "
        for character in casefolded
    )
    return re.sub(r"\s+", " ", alphanumeric_or_space).strip()


def tokenize_search_text(value: str) -> list[str]:
    """
    Converte um texto em tokens usando a normalização canônica.
    """

    normalized = normalize_search_text(value)
    return normalized.split() if normalized else []
