"""HTML to PDF with Chromium (Playwright sync API).

Playwright's sync API is bound to the thread that started it, while Dramatiq runs several worker
threads per process. All browser work therefore runs on one dedicated thread that owns a lazily
started browser (one per process, reused); every export gets a fresh browser context.

Known limitation: Chromium fills the footer's page numbers (``pageNumber`` / ``totalPages``)
itself, always with Western digits, even for Arabic exams.
"""

import atexit
import base64
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from html import escape
from pathlib import Path

from playwright.sync_api import Browser, PdfMargins, Playwright, sync_playwright

from qbank.config import get_settings
from qbank.export.render import VENDOR

MARGIN: PdfMargins = {"top": "14mm", "bottom": "18mm", "left": "14mm", "right": "14mm"}
LAUNCH_ARGS = ["--disable-dev-shm-usage", "--font-render-hinting=none"]
FOOTER_FONT = VENDOR / "fonts" / "noto-naskh-arabic-arabic-400-normal.woff2"
FOOTER_WORDS = {"ar": ("صفحة", "من"), "en": ("Page", "of")}


class PdfError(RuntimeError):
    """The PDF could not be produced (browser failure or timeout)."""


def footer_template(title: str, version_label: str, language: str) -> str:
    """Chromium footer: title and version on one side, "Page X of Y" on the other."""
    page, of = FOOTER_WORDS[language]
    font = base64.b64encode(FOOTER_FONT.read_bytes()).decode()
    return (
        "<style>"
        "@font-face{font-family:'FooterNaskh';"
        f"src:url(data:font/woff2;base64,{font}) format('woff2')}}"
        "</style>"
        f'<div dir="{"rtl" if language == "ar" else "ltr"}" style="width:100%;padding:0 14mm;'
        "font-family:'FooterNaskh','Noto Naskh Arabic',sans-serif;font-size:9px;color:#444;"
        'display:flex;justify-content:space-between;align-items:center;">'
        f"<span>{escape(title)} - {escape(version_label)}</span>"
        f'<span>{page} <span class="pageNumber"></span> {of} '
        '<span class="totalPages"></span></span>'
        "</div>"
    )


class _Renderer:
    """Owns the browser; every method must run on the dedicated thread."""

    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None

    def _browser(self) -> Browser:
        if self.browser is not None and self.browser.is_connected():
            return self.browser
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        settings = get_settings()
        args = LAUNCH_ARGS if settings.export_chromium_sandbox else [*LAUNCH_ARGS, "--no-sandbox"]
        self.browser = self.playwright.chromium.launch(
            executable_path=settings.export_chromium_path or None, args=args
        )
        return self.browser

    def render(self, html: str, footer: str, timeout_ms: int) -> bytes:
        with tempfile.TemporaryDirectory(prefix="qbank-export-") as directory:
            page_file = Path(directory) / "page.html"
            page_file.write_text(html, encoding="utf-8")
            context = self._browser().new_context(java_script_enabled=True)
            try:
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(page_file.as_uri(), wait_until="load")
                page.wait_for_function("window.__qbankReady === true", timeout=timeout_ms)
                return page.pdf(
                    format="A4",
                    print_background=True,
                    margin=MARGIN,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template=footer,
                )
            finally:
                context.close()

    def close(self) -> None:
        try:
            if self.browser is not None:
                self.browser.close()
            if self.playwright is not None:
                self.playwright.stop()
        finally:
            self.browser = None
            self.playwright = None


_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_renderer = _Renderer()


def _pool() -> ThreadPoolExecutor:
    global _executor  # noqa: PLW0603 -- lazy process-wide singleton
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qbank-pdf")
        return _executor


def render_pdf(
    html: str, *, title: str, version_label: str, language: str, timeout_s: float | None = None
) -> bytes:
    """A4 PDF bytes for a self-contained HTML document. Raises ``PdfError`` on failure."""
    timeout = timeout_s if timeout_s is not None else get_settings().export_timeout_s
    footer = footer_template(title, version_label, language)
    future: Future[bytes] = _pool().submit(_renderer.render, html, footer, int(timeout * 1000))
    try:
        return future.result(timeout=timeout + 15)
    except Exception as exc:
        raise PdfError(f"{type(exc).__name__}: {exc}"[:500]) from exc


def shutdown() -> None:
    """Close the browser and stop the thread (idempotent; also runs at interpreter exit)."""
    global _executor
    with _lock:
        pool, _executor = _executor, None
    if pool is not None:
        pool.submit(_renderer.close).result(timeout=30)
        pool.shutdown(wait=True)


atexit.register(shutdown)
