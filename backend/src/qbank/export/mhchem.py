"""Common mhchem ``\\ce{...}`` patterns to plain TeX, because Pandoc (OMML) has no mhchem.

Handled: subscripts (``H2O``), coefficients (``2H2``), charges (``SO4^2-``, ``Na+``, ``^{2-}``),
states (``(g)``, ``(aq)``), arrows (``->``, ``<-``, ``<->``, ``<=>``). Anything else falls back to
the raw text inside ``\\mathrm{}``.
"""

import re

ARROWS = (
    ("<=>", r"\rightleftharpoons "),
    ("<->", r"\leftrightarrow "),
    ("->", r"\rightarrow "),
    ("<-", r"\leftarrow "),
)
SCRIPT = re.compile(r"\{([^{}]*)\}|(\d*[+-]?)")
ALLOWED = re.compile(r"[A-Za-z0-9\s+\-=()\[\].,/*^_{}<>]*")
CE_OPEN = "\\ce{"
ESCAPES = {
    "\\": r"\backslash ",
    "{": r"\{",
    "}": r"\}",
    "_": r"\_",
    "^": r"\^{}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "$": r"\$",
    "~": r"\~{}",
}


class _UnsupportedError(Exception):
    """The ``\\ce`` body uses something this converter does not model."""


def _script(text: str, i: int, marker: str) -> tuple[str, int]:
    match = SCRIPT.match(text, i + 1)
    if match is None or not (match.group(1) or match.group(2)):
        raise _UnsupportedError
    return f"{marker}{{{match.group(1) or match.group(2)}}}", match.end()


def _convert(body: str) -> str:  # noqa: PLR0912 -- one flat scanner is clearer than split helpers
    if not ALLOWED.fullmatch(body) or "{" in body.replace("^{", "").replace("_{", ""):
        raise _UnsupportedError
    out: list[str] = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        arrow = next((a for a in ARROWS if body.startswith(a[0], i)), None)
        if arrow:
            out.append(arrow[1])
            i += len(arrow[0])
        elif c in "^_":
            piece, i = _script(body, i, c)
            out.append(piece)
        elif c.isspace():
            out.append(" ")
            i += 1
        elif c.isdigit():
            j = i
            while j < n and body[j].isdigit():
                j += 1
            run = body[i:j]
            after = body[j] if j < n else ""
            follows_species = i > 0 and (body[i - 1].isalpha() or body[i - 1] in ")]")
            ends = j + 1 >= n or body[j + 1].isspace() or body[j + 1] in ")]"
            if follows_species and after in "+-" and after and ends:
                out.append(f"^{{{run}{after}}}")
                j += 1
            elif follows_species:
                out.append(f"_{run}" if len(run) == 1 else f"_{{{run}}}")
            else:
                out.append(run)
            i = j
        elif c in "+-" and i > 0 and not body[i - 1].isspace():
            ends = i + 1 >= n or body[i + 1].isspace() or body[i + 1] in ")]"
            out.append(f"^{c}" if ends else c)
            i += 1
        elif c == "*":
            out.append(r"\cdot ")
            i += 1
        else:
            out.append(c)
            i += 1
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def ce_to_tex(body: str) -> str:
    """TeX for the body of one ``\\ce{...}``, wrapped in ``\\mathrm{}``."""
    try:
        return f"\\mathrm{{{_convert(body.strip())}}}"
    except _UnsupportedError:
        raw = "".join(ESCAPES.get(ch, ch) for ch in body.strip())
        return f"\\mathrm{{{raw}}}"


def convert_math(tex: str) -> str:
    """Replace every ``\\ce{...}`` (balanced braces) in a TeX math string."""
    out: list[str] = []
    i = 0
    while (start := tex.find(CE_OPEN, i)) != -1:
        depth, j = 1, start + len(CE_OPEN)
        while j < len(tex) and depth:
            depth += {"{": 1, "}": -1}.get(tex[j], 0)
            j += 1
        if depth:  # unbalanced: leave the rest as it is
            break
        out.append(tex[i:start])
        out.append(ce_to_tex(tex[start + len(CE_OPEN) : j - 1]))
        i = j
    out.append(tex[i:])
    return "".join(out)
