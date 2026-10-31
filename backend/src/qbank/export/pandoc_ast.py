"""QMD to a Pandoc JSON AST, from the same markdown-it parse the HTML renderer uses.

Building the AST directly (instead of emitting Pandoc Markdown) avoids re-escaping user text, keeps
``$...$`` semantics identical to the PDF (markdown-it ``dollarmath``), and never lets raw HTML or
TeX through: only the node types below are ever produced.
"""

import base64
import binascii
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_it.token import Token
from PIL import Image

from qbank.export.mhchem import convert_math
from qbank.export.qmd import FULL_BLANK, AssetResolver, parse_qmd

Node = dict[str, Any]
API_VERSION = [1, 23, 1]
NBSP = chr(0xA0)  # no-break space
BLANK_WIDTH = 14
IMAGE_DPI = 96
MAX_IMAGE_WIDTH_IN = 4.0  # about 60% of the 17 cm text width on A4 with 2 cm margins
BLANK_SPLIT = re.compile(r"(_{4,})")
SPACES = re.compile(r"( +)")
MISSING_FIGURE = "[figure]"
DATA_URI = re.compile(r"data:image/([a-z0-9.+-]+);base64,(.*)", re.DOTALL)
EXTENSIONS = {"jpeg": "jpg", "svg+xml": "svg"}


def node(tag: str, content: Any = None) -> Node:
    return {"t": tag} if content is None else {"t": tag, "c": content}


def attr(
    identifier: str = "", classes: list[str] | None = None, pairs: dict[str, str] | None = None
) -> list[Any]:
    return [identifier, classes or [], [[k, v] for k, v in (pairs or {}).items()]]


def text(value: str) -> list[Node]:
    """Words and spaces for one run of text (Pandoc ``Str`` cannot contain spaces)."""
    out: list[Node] = []
    for part in SPACES.split(value):
        if not part:
            continue
        out.append(node("Space") if part[0] == " " else node("Str", part))
    return out


def blank() -> Node:
    """A visible blank: underlined no-break spaces."""
    return node("Underline", [node("Str", NBSP * BLANK_WIDTH)])


def para(inlines: list[Node]) -> Node:
    return node("Para", inlines)


def div(blocks: list[Node], style: str | None = None, direction: str | None = None) -> Node:
    pairs: dict[str, str] = {}
    if style:
        pairs["custom-style"] = style
    if direction:
        pairs["dir"] = direction
    return node("Div", [attr(pairs=pairs), blocks])


def styled_span(inlines: list[Node], style: str) -> Node:
    return node("Span", [attr(pairs={"custom-style": style}), inlines])


def table(
    rows: list[list[list[Node]]],
    *,
    style: str,
    header: list[list[Node]] | None = None,
    footer: list[list[Node]] | None = None,
    widths: list[float] | None = None,
) -> Node:
    """A Pandoc table. Cells are lists of blocks; ``widths`` are fractions of the text width."""
    columns = len(header or rows[0])

    def row(cells: list[list[Node]]) -> list[Any]:
        padded = cells + [[] for _ in range(columns - len(cells))]
        return [
            attr(),
            [[attr(), node("AlignDefault"), 1, 1, cell or [node("Plain", [])]] for cell in padded],
        ]

    specs = [
        [node("AlignDefault"), node("ColWidth", w) if widths else node("ColWidthDefault")]
        for w in (widths or [0.0] * columns)
    ]
    return node(
        "Table",
        [
            attr(pairs={"custom-style": style}),
            [None, []],
            specs,
            [attr(), [row(header)] if header else []],
            [[attr(), 0, [], [row(r) for r in rows]]],
            [attr(), [row(footer)] if footer else []],
        ],
    )


@dataclass
class Context:
    """Per-document state: where images are written and how assets resolve."""

    media_dir: Path
    assets: AssetResolver | None = None
    written: dict[str, Path] = field(default_factory=dict)

    def image(self, asset_id: str) -> Path | None:
        """The file of ``asset:<id>``, or ``None`` when the asset is unknown."""
        return self.from_uri(self.assets(asset_id) if self.assets else None, asset_id)

    def from_uri(self, uri: str | None, key: str | None = None) -> Path | None:
        """Writes a ``data:image/...`` URI to the media directory (once per ``key``)."""
        key = key or uri or ""
        if key in self.written:
            return self.written[key]
        match = DATA_URI.fullmatch(uri) if uri else None
        if match is None:
            return None
        try:
            data = base64.b64decode(match.group(2), validate=False)
        except binascii.Error:
            return None
        kind = match.group(1)
        path = self.media_dir / f"figure-{len(self.written) + 1}.{EXTENSIONS.get(kind, kind)}"
        path.write_bytes(data)
        self.written[key] = path
        return path


def _image_width(path: Path) -> str:
    try:
        with Image.open(path) as image:
            natural = image.width / IMAGE_DPI
    except OSError:
        return f"{MAX_IMAGE_WIDTH_IN}in"
    return f"{min(natural, MAX_IMAGE_WIDTH_IN):.2f}in"


def _image(token: Token, ctx: Context) -> list[Node]:
    src = str(token.attrGet("src") or "")
    path = ctx.image(src.removeprefix("asset:").strip()) if src.startswith("asset:") else None
    if path is None:
        # External URLs are never fetched: exports must not depend on the network.
        return [node("Str", MISSING_FIGURE)]
    alt = text(token.content)
    return [node("Image", [attr(pairs={"width": _image_width(path)}), alt, [str(path), ""]])]


def _math(token: Token, kind: str) -> Node:
    return node("Math", [node(kind), convert_math(token.content.strip())])


def _text(content: str) -> list[Node]:
    out: list[Node] = []
    for part in BLANK_SPLIT.split(content):
        out.extend([blank()] if FULL_BLANK.fullmatch(part) else text(part))
    return out


WRAPPERS = {"em": "Emph", "strong": "Strong", "s": "Strikeout", "link": "Span"}


def inlines(children: list[Token], ctx: Context) -> list[Node]:
    stack: list[tuple[str, list[Node]]] = [("", [])]
    for token in children:
        kind = token.type
        if kind == "text":
            stack[-1][1].extend(_text(token.content))
        elif kind == "softbreak":
            stack[-1][1].append(node("SoftBreak"))
        elif kind == "hardbreak":
            stack[-1][1].append(node("LineBreak"))
        elif kind == "code_inline":
            stack[-1][1].append(node("Code", [attr(), token.content]))
        elif kind == "math_inline":
            stack[-1][1].append(_math(token, "InlineMath"))
        elif kind == "math_inline_double":
            stack[-1][1].append(_math(token, "DisplayMath"))
        elif kind == "image":
            stack[-1][1].extend(_image(token, ctx))
        elif kind.endswith("_open") and kind.removesuffix("_open") in WRAPPERS:
            stack.append((kind.removesuffix("_open"), []))
        elif kind.endswith("_close") and kind.removesuffix("_close") in WRAPPERS:
            name, content = stack.pop()
            # Links keep their text only: exports carry no live hyperlinks.
            stack[-1][1].extend(content if name == "link" else [node(WRAPPERS[name], content)])
    while len(stack) > 1:  # unbalanced markup: keep the text
        stack[-2][1].extend(stack.pop()[1])
    return stack[0][1]


def inline_qmd(source: str, ctx: Context) -> list[Node]:
    """Inlines of one QMD string with no wrapping paragraph (choices, answers)."""
    tokens = parse_qmd(source, inline=True)
    return inlines(tokens[0].children or [], ctx) if tokens else []


def blocks_qmd(source: str, ctx: Context) -> list[Node]:
    """Blocks of one QMD string."""
    tokens = parse_qmd(source)
    out, _ = _blocks(tokens, 0, len(tokens), ctx, source.splitlines())
    return out


def _close(tokens: list[Token], start: int) -> int:
    """Index of the token closing the one at ``start``."""
    depth = 0
    for i in range(start, len(tokens)):
        depth += tokens[i].nesting
        if depth == 0:
            return i
    return len(tokens) - 1


def _blocks(
    tokens: list[Token], start: int, end: int, ctx: Context, lines: list[str]
) -> tuple[list[Node], int]:
    out: list[Node] = []
    i = start
    while i < end:
        token = tokens[i]
        kind = token.type
        close = _close(tokens, i) if token.nesting == 1 else i
        if kind == "paragraph_open":
            out.append(para(inlines(tokens[i + 1].children or [], ctx)))
        elif kind == "heading_open":
            level = min(int(token.tag[1:]), 6)
            out.append(node("Header", [level, attr(), inlines(tokens[i + 1].children or [], ctx)]))
        elif kind in {"bullet_list_open", "ordered_list_open"}:
            items = _items(tokens, i, close, ctx, lines)
            if kind == "bullet_list_open":
                out.append(node("BulletList", items))
            else:
                first = int(token.attrGet("start") or 1)
                style = [first, node("Decimal"), node("Period")]
                out.append(node("OrderedList", [style, items]))
        elif kind == "blockquote_open":
            inner, _ = _blocks(tokens, i + 1, close, ctx, lines)
            out.append(node("BlockQuote", inner))
        elif kind == "table_open":
            out.append(_table(tokens, i, close, ctx))
        elif kind in {"fence", "code_block"}:
            out.append(node("CodeBlock", [attr(), token.content.rstrip("\n")]))
        elif kind == "math_block":
            out.append(para([_math(token, "DisplayMath")]))
        elif kind == "hr":
            source_map = token.map
            line = lines[source_map[0]] if source_map and source_map[0] < len(lines) else ""
            out.append(
                para([blank()]) if FULL_BLANK.fullmatch(line.strip()) else node("HorizontalRule")
            )
        i = close + 1
    return out, i


def _items(
    tokens: list[Token], start: int, end: int, ctx: Context, lines: list[str]
) -> list[list[Node]]:
    items: list[list[Node]] = []
    i = start + 1
    while i < end:
        if tokens[i].type == "list_item_open":
            close = _close(tokens, i)
            inner, _ = _blocks(tokens, i + 1, close, ctx, lines)
            items.append(inner)
            i = close
        i += 1
    return items


def _table(tokens: list[Token], start: int, end: int, ctx: Context) -> Node:
    header: list[list[Node]] = []
    rows: list[list[list[Node]]] = []
    current: list[list[Node]] = []
    in_head = False
    for i in range(start, end):
        token = tokens[i]
        if token.type == "thead_open":
            in_head = True
        elif token.type == "thead_close":
            in_head = False
        elif token.type == "tr_open":
            current = []
        elif token.type == "tr_close":
            if in_head:
                header = current
            else:
                rows.append(current)
        elif token.type in {"th_open", "td_open"}:
            cell = [node("Plain", inlines(tokens[i + 1].children or [], ctx))]
            current.append([node("Plain", [node("Strong", cell[0]["c"])])] if in_head else cell)
    if not rows:
        rows = [[[] for _ in header]]
    return table(rows, style="Table", header=header or None)


def document(blocks: list[Node], language: str) -> Node:
    return {
        "pandoc-api-version": API_VERSION,
        "meta": {"lang": node("MetaString", language)},
        "blocks": blocks,
    }
