import "katex/dist/katex.min.css";
import "katex/contrib/mhchem";

import { memo, useMemo } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown, {
  type Components,
  type Options as ReactMarkdownOptions,
} from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { cn } from "@/lib/utils";

const KATEX_ERROR_COLOR = "#dc2626";

export interface QmdRendererProps {
  source: string;
  resolveAsset?: ((id: string) => string | undefined) | undefined;
  lang?: "ar" | "en" | undefined;
  inline?: boolean | undefined;
  className?: string | undefined;
}

interface AstPositionPoint {
  offset?: number | undefined;
}

interface AstPosition {
  start?: AstPositionPoint | undefined;
  end?: AstPositionPoint | undefined;
}

interface AstNode {
  type: string;
  value?: string | undefined;
  children?: AstNode[] | undefined;
  position?: AstPosition | undefined;
  data?: Record<string, unknown> | undefined;
}

interface AstFile {
  value?: unknown;
}

function createBlankNode(ariaLabel: string): AstNode {
  return {
    type: "qmdBlank",
    data: {
      hName: "span",
      hProperties: {
        className: ["qmd-blank"],
        "aria-label": ariaLabel,
      },
      hChildren: [],
    },
  };
}

function createRemarkBlanks(blankAriaLabel: string) {
  return function remarkBlanks() {
    return (tree: AstNode, file: AstFile) => {
      const rawSource = typeof file.value === "string" ? file.value : "";

      function walk(node: AstNode): void {
        const children = node.children;
        if (!children) {
          return;
        }
        for (let i = 0; i < children.length; i += 1) {
          const child = children[i];
          if (!child) {
            continue;
          }

          if (child.type === "inlineMath" && child.position) {
            const startOffset = child.position.start?.offset;
            const endOffset = child.position.end?.offset;
            if (
              typeof startOffset === "number" &&
              typeof endOffset === "number" &&
              rawSource.slice(startOffset, endOffset).startsWith("$$")
            ) {
              child.data = {
                ...child.data,
                hProperties: { className: ["language-math", "math-display"] },
              };
            }
          }

          if (child.type === "thematicBreak" && child.position) {
            const startOffset = child.position.start?.offset;
            const endOffset = child.position.end?.offset;
            if (
              typeof startOffset === "number" &&
              typeof endOffset === "number"
            ) {
              const slice = rawSource.slice(startOffset, endOffset).trim();
              if (/^_{4,}$/.test(slice)) {
                children[i] = {
                  type: "paragraph",
                  children: [createBlankNode(blankAriaLabel)],
                };
                continue;
              }
            }
          }

          if (
            child.type === "text" &&
            typeof child.value === "string" &&
            /_{4,}/.test(child.value)
          ) {
            const parts = child.value.split(/(_{4,})/g);
            const replacement: AstNode[] = [];
            for (const part of parts) {
              if (!part) {
                continue;
              }
              if (/^_{4,}$/.test(part)) {
                replacement.push(createBlankNode(blankAriaLabel));
              } else {
                replacement.push({ type: "text", value: part });
              }
            }
            children.splice(i, 1, ...replacement);
            i += replacement.length - 1;
          } else {
            walk(child);
          }
        }
      }

      walk(tree);
    };
  };
}

function qmdUrlTransform(url: string, key: string): string {
  const trimmed = url.trim();
  if (key === "src" && trimmed.startsWith("asset:")) {
    return trimmed;
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  return "";
}

function omitMarkdownNode<T extends { node?: unknown }>(
  props: T,
): Omit<T, "node"> {
  const copy = { ...props };
  delete copy.node;
  return copy;
}

const rehypePlugins: NonNullable<ReactMarkdownOptions["rehypePlugins"]> = [
  [
    rehypeKatex,
    {
      throwOnError: false,
      errorColor: KATEX_ERROR_COLOR,
      strict: "ignore",
    } as Parameters<typeof rehypeKatex>[0],
  ],
];

export const QmdRenderer = memo(function QmdRenderer({
  source,
  resolveAsset,
  lang,
  inline = false,
  className,
}: QmdRendererProps) {
  const { t } = useTranslation();
  const missingAssetText = t("qmd.missingAsset");
  const blankAriaLabel = t("qmd.blankAriaLabel");

  const remarkPlugins = useMemo<
    NonNullable<ReactMarkdownOptions["remarkPlugins"]>
  >(
    () => [remarkGfm, remarkMath, createRemarkBlanks(blankAriaLabel)],
    [blankAriaLabel],
  );

  const components = useMemo<Components>(
    () => ({
      p: ({ children, ...props }) => {
        if (inline) {
          return <>{children}</>;
        }
        return (
          <p
            {...omitMarkdownNode(props)}
            dir="auto"
            className="my-2 leading-relaxed first:mt-0 last:mb-0"
          >
            {children}
          </p>
        );
      },
      h1: ({ children, ...props }) => (
        <h1
          {...omitMarkdownNode(props)}
          dir="auto"
          className="mt-4 mb-2 text-xl font-bold"
        >
          {children}
        </h1>
      ),
      h2: ({ children, ...props }) => (
        <h2
          {...omitMarkdownNode(props)}
          dir="auto"
          className="mt-3 mb-2 text-lg font-bold"
        >
          {children}
        </h2>
      ),
      h3: ({ children, ...props }) => (
        <h3
          {...omitMarkdownNode(props)}
          dir="auto"
          className="mt-3 mb-1.5 text-base font-semibold"
        >
          {children}
        </h3>
      ),
      h4: ({ children, ...props }) => (
        <h4
          {...omitMarkdownNode(props)}
          dir="auto"
          className="mt-2 mb-1 text-sm font-semibold"
        >
          {children}
        </h4>
      ),
      ul: ({ children, ...props }) => (
        <ul
          {...omitMarkdownNode(props)}
          dir="auto"
          className="my-2 list-disc ps-6"
        >
          {children}
        </ul>
      ),
      ol: ({ children, ...props }) => (
        <ol
          {...omitMarkdownNode(props)}
          dir="auto"
          className="my-2 list-decimal ps-6"
        >
          {children}
        </ol>
      ),
      li: ({ children, ...props }) => (
        <li {...omitMarkdownNode(props)} dir="auto" className="my-0.5">
          {children}
        </li>
      ),
      blockquote: ({ children, ...props }) => (
        <blockquote
          {...omitMarkdownNode(props)}
          dir="auto"
          className="border-border text-muted-foreground my-2 border-s-4 ps-4 italic"
        >
          {children}
        </blockquote>
      ),
      pre: ({ children, ...props }) => (
        <pre
          {...omitMarkdownNode(props)}
          dir="ltr"
          className="bg-muted my-2 overflow-x-auto rounded-md p-3 font-mono text-sm"
        >
          {children}
        </pre>
      ),
      a: ({ href, children, ...props }) => {
        const safeHref =
          typeof href === "string" && /^https?:\/\//i.test(href)
            ? href
            : undefined;
        if (!safeHref) {
          return <span>{children}</span>;
        }
        return (
          <a
            {...omitMarkdownNode(props)}
            href={safeHref}
            rel="noopener noreferrer"
            target="_blank"
            className="text-primary underline underline-offset-4"
          >
            {children}
          </a>
        );
      },
      img: ({ src, alt, ...props }) => {
        const rawSrc = typeof src === "string" ? src : "";
        const caption = typeof alt === "string" ? alt : "";

        let resolvedUrl: string | undefined;
        let assetId: string | undefined;

        if (rawSrc.startsWith("asset:")) {
          assetId = rawSrc.slice("asset:".length);
          resolvedUrl = resolveAsset?.(assetId);
        } else if (/^https?:\/\//i.test(rawSrc)) {
          resolvedUrl = rawSrc;
        }

        if (!resolvedUrl) {
          return (
            <span
              role="img"
              aria-label={
                caption ? `${missingAssetText}: ${caption}` : missingAssetText
              }
              data-missing-asset={assetId ?? rawSrc}
              className="border-destructive/50 bg-destructive/10 text-destructive inline-flex items-center gap-1.5 rounded-md border border-dashed px-3 py-1.5 text-sm"
            >
              <span>{missingAssetText}</span>
              {caption ? (
                <span className="text-muted-foreground text-xs">
                  ({caption})
                </span>
              ) : null}
            </span>
          );
        }

        return (
          <img
            {...omitMarkdownNode(props)}
            src={resolvedUrl}
            alt={caption}
            loading="lazy"
            className="my-2 max-w-full rounded-md"
          />
        );
      },
      table: ({ children, ...props }) => (
        <div dir="auto" className="my-3 overflow-x-auto">
          <table
            {...omitMarkdownNode(props)}
            dir="auto"
            className="border-border w-full border-collapse border text-start text-sm"
          >
            {children}
          </table>
        </div>
      ),
      thead: ({ children, ...props }) => (
        <thead {...omitMarkdownNode(props)} className="bg-muted/50">
          {children}
        </thead>
      ),
      th: ({ children, ...props }) => (
        <th
          {...omitMarkdownNode(props)}
          dir="auto"
          className="border-border border px-3 py-2 text-start font-semibold"
        >
          {children}
        </th>
      ),
      td: ({ children, ...props }) => (
        <td
          {...omitMarkdownNode(props)}
          dir="auto"
          className="border-border border px-3 py-2 text-start"
        >
          {children}
        </td>
      ),
      span: ({ className: spanClass, style, children, ...props }) => {
        const cleanProps = omitMarkdownNode(props);
        const cls = typeof spanClass === "string" ? spanClass : "";
        const isBlank = cls.includes("qmd-blank");
        const isKatexError =
          cls.includes("katex-error") ||
          (cls.includes("mord") &&
            !cls.includes("text") &&
            style !== undefined &&
            typeof style === "object" &&
            "color" in style &&
            style.color === KATEX_ERROR_COLOR);
        const isKatexMath =
          cls.includes("katex") ||
          cls.includes("katex-display") ||
          isKatexError;

        return (
          <span
            {...cleanProps}
            style={style}
            dir={isKatexMath ? "ltr" : cleanProps.dir}
            className={cn(
              cls,
              isBlank &&
                "mx-1 inline-block h-4 min-w-16 border-b-2 border-current align-baseline",
              isKatexError &&
                "katex-error inline-block rounded border border-red-500 bg-red-500/10 px-1 font-mono text-red-600",
            )}
          >
            {children}
          </span>
        );
      },
    }),
    [inline, missingAssetText, resolveAsset],
  );

  const markdownElement = (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
      urlTransform={qmdUrlTransform}
    >
      {source}
    </ReactMarkdown>
  );

  if (inline) {
    return (
      <span
        dir="auto"
        lang={lang}
        data-testid="qmd-renderer"
        data-inline="true"
        className={cn("qmd-renderer font-content", className)}
      >
        {markdownElement}
      </span>
    );
  }

  return (
    <div
      dir="auto"
      lang={lang}
      data-testid="qmd-renderer"
      data-inline="false"
      className={cn("qmd-renderer font-content", className)}
    >
      {markdownElement}
    </div>
  );
});
