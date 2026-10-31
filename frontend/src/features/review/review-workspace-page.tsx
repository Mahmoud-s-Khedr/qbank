import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Crop,
  HelpCircle,
  ImagePlus,
  RefreshCw,
  ScanSearch,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import {
  assetImageUrl,
  type DraftQuestion,
  type IssueOut,
  isQuestionOut,
  type QuestionOut,
  type QueueFilters,
  assetKey,
  prefetchQuestion,
  questionKey,
  useAddFigure,
  useApproveQuestion,
  useAssets,
  useBulkQuestions,
  useDeleteFigure,
  useExtractRegion,
  useMergeQuestions,
  usePageDetail,
  usePatchQuestion,
  usePatchStimulus,
  useQuestion,
  useRecropFigure,
  useRejectQuestion,
  useReopenQuestion,
  useReviewQueue,
  useSetIssueResolved,
  useSourceQuestions,
  useSourceStimuli,
  useSplitQuestion,
} from "@/api/hooks/review";
import {
  getPageImageUrl,
  useSourceDetail,
  useSourcePages,
} from "@/api/hooks/sources";
import {
  type Box,
  PageCanvas,
  type PageCanvasMode,
  type Region,
} from "@/components/page-canvas/PageCanvas";
import { QmdEditor } from "@/components/qmd/QmdEditor";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  ApproveBlockedDialog,
  BulkMetadataDialog,
  ConfirmDialog,
  ConflictDialog,
  ReasonDialog,
  ShortcutsDialog,
} from "./dialogs";
import { EditorPane } from "./editor-pane";
import { MissedQuestionDialog } from "./missed-question-dialog";
import { QueuePane } from "./queue-pane";
import { ReextractDialog } from "./reextract-dialog";
import {
  buildPatch,
  type Draft,
  draftFromQuestion,
  assetIdsOf,
  isQuestionType,
  pageIdsOf,
  parseExtraction,
  parseRegions,
  pickNextId,
  regionStatus,
  stimulusRegions,
  suggestedFix,
  unresolvedIssues,
} from "./review-model";
import { useReviewShortcuts } from "./use-shortcuts";

type Pane = "queue" | "page" | "editor";
type Tool = "figure" | "missed" | null;

interface Conflict {
  current: QuestionOut;
  patch: NonNullable<ReturnType<typeof buildPatch>>;
}

interface Blocked {
  message: string;
  questionId: string;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function ReviewWorkspacePage() {
  const { t } = useTranslation();
  const { id: sourceId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const me = useMe();
  const selectedId = params.get("q") ?? undefined;

  const source = useSourceDetail(sourceId);
  const pagesQuery = useSourcePages(sourceId);
  const [filters, setFilters] = useState<QueueFilters>({
    status: "",
    severity: "",
    sort: "page",
  });
  const queue = useReviewQueue(sourceId, filters);
  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const questionQuery = useQuestion(selectedId);
  const question = questionQuery.data;
  const sourceQuestions = useSourceQuestions(sourceId);
  const stimuli = useSourceStimuli(sourceId);

  const patchMut = usePatchQuestion();
  const approveMut = useApproveQuestion();
  const rejectMut = useRejectQuestion();
  const reopenMut = useReopenQuestion();
  const bulkMut = useBulkQuestions();
  const splitMut = useSplitQuestion();
  const mergeMut = useMergeQuestions();
  const resolveMut = useSetIssueResolved();
  const addFigureMut = useAddFigure();
  const recropMut = useRecropFigure();
  const deleteFigureMut = useDeleteFigure();
  const stimulusMut = usePatchStimulus();
  const extractMut = useExtractRegion();

  const [pane, setPane] = useState<Pane>("page");
  const [tool, setTool] = useState<Tool>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftBase, setDraftBase] = useState<{
    id: string;
    version: number;
  } | null>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [blocked, setBlocked] = useState<Blocked | null>(null);
  const [rejectTarget, setRejectTarget] = useState<"one" | "bulk" | null>(null);
  const [bulkMetaOpen, setBulkMetaOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [removeAsset, setRemoveAsset] = useState<string | null>(null);
  const [reextractOpen, setReextractOpen] = useState(false);
  const [stimulusOpen, setStimulusOpen] = useState(false);
  const [missed, setMissed] = useState<{
    draft: DraftQuestion;
    box: Box;
    pageId: string;
  } | null>(null);
  const [pageSel, setPageSel] = useState<{ qid: string; idx: number }>({
    qid: "",
    idx: 0,
  });
  const [regionSel, setRegionSel] = useState<{ qid: string; id: string }>({
    qid: "",
    id: "",
  });
  const [figureBoxes, setFigureBoxes] = useState<
    Record<string, { pageId: string; box: Box }>
  >({});

  const stemRef = useRef<HTMLTextAreaElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const focusQueueRef = useRef(false);
  const savingRef = useRef<Promise<QuestionOut | undefined> | null>(null);
  const draftRef = useRef<Draft | null>(null);
  const baseRef = useRef(draftBase);
  useEffect(() => {
    draftRef.current = draft;
    baseRef.current = draftBase;
  });

  // --- selection ----------------------------------------------------------------------------
  const select = useCallback(
    (id: string | undefined, focusQueue = false) => {
      focusQueueRef.current = focusQueue;
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id) next.set("q", id);
          else next.delete("q");
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );

  useEffect(() => {
    if (!selectedId && items[0]) {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("q", items[0]?.id ?? "");
          return next;
        },
        { replace: true },
      );
    }
  }, [selectedId, items, setParams]);

  const selectedIndex = items.findIndex((item) => item.id === selectedId);
  useEffect(() => {
    const next = items[selectedIndex + 1];
    if (selectedIndex >= 0 && next) prefetchQuestion(queryClient, next.id);
  }, [items, selectedIndex, queryClient]);

  useEffect(() => {
    if (!focusQueueRef.current || !selectedId) return;
    focusQueueRef.current = false;
    const option = document.getElementById(`queue-option-${selectedId}`);
    (option ?? listRef.current)?.focus();
  }, [selectedId, items]);

  const move = useCallback(
    (delta: number) => {
      if (items.length === 0) return;
      const index = selectedIndex < 0 ? 0 : selectedIndex + delta;
      const target = items[Math.max(0, Math.min(items.length - 1, index))];
      if (target) select(target.id);
    },
    [items, selectedIndex, select],
  );

  // --- draft --------------------------------------------------------------------------------
  const dirty = Boolean(
    question && draft && buildPatch(question, draft) !== null,
  );

  useEffect(() => {
    if (!question) return;
    const base = baseRef.current;
    const current = draftRef.current;
    const isDirty =
      base?.id === question.id && current
        ? buildPatch(question, current) !== null
        : false;
    if (
      base?.id !== question.id ||
      (base.version !== question.version && !isDirty)
    ) {
      setDraft(draftFromQuestion(question));
      setDraftBase({ id: question.id, version: question.version });
    }
  }, [question]);

  const save = useCallback(
    async (nextDraft?: Draft): Promise<QuestionOut | undefined> => {
      if (savingRef.current) return savingRef.current;
      const q = question;
      const d = nextDraft ?? draftRef.current;
      const base = baseRef.current;
      if (!q || !d || base?.id !== q.id) return q;
      const patch = buildPatch(q, d, base.version);
      if (!patch) return q;
      const run = (async () => {
        try {
          const saved = await patchMut.mutateAsync({ id: q.id, patch });
          setDraft(draftFromQuestion(saved));
          setDraftBase({ id: saved.id, version: saved.version });
          return saved;
        } catch (error) {
          const current =
            error instanceof ApiError ? error.body?.current : undefined;
          if (
            error instanceof ApiError &&
            error.status === 409 &&
            error.code === "version_conflict" &&
            isQuestionOut(current)
          ) {
            setConflict({ current, patch });
          } else {
            toast.error(errorMessage(error, t("review.errors.save")));
          }
          return undefined;
        } finally {
          savingRef.current = null;
        }
      })();
      savingRef.current = run;
      return run;
    },
    [question, patchMut, t],
  );

  /** Saves pending edits first; undefined means the save failed and the action must stop. */
  const ensureSaved = useCallback(async (): Promise<
    QuestionOut | undefined
  > => {
    if (!question) return undefined;
    const d = draftRef.current;
    if (d && buildPatch(question, d) === null) return question;
    return save();
  }, [question, save]);

  const reloadFromServer = (current: QuestionOut) => {
    queryClient.setQueryData(questionKey(current.id), current);
    setDraft(draftFromQuestion(current));
    setDraftBase({ id: current.id, version: current.version });
    void queryClient.invalidateQueries({ queryKey: ["review"] });
    setConflict(null);
  };

  const overwrite = async () => {
    if (!conflict) return;
    try {
      const saved = await patchMut.mutateAsync({
        id: conflict.current.id,
        patch: { ...conflict.patch, version: conflict.current.version },
      });
      setDraft(draftFromQuestion(saved));
      setDraftBase({ id: saved.id, version: saved.version });
      setConflict(null);
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.save")));
    }
  };

  // --- status actions -----------------------------------------------------------------------
  const isOpen =
    question?.status === "draft" || question?.status === "needs_review";

  const afterDecision = (nextId: string | undefined) => {
    setChecked(new Set());
    select(nextId, true);
  };

  const handleActionError = (error: unknown, q: QuestionOut) => {
    if (
      error instanceof ApiError &&
      error.status === 422 &&
      error.code === "unresolved_errors"
    ) {
      setBlocked({ message: error.message, questionId: q.id });
      return;
    }
    const current = error instanceof ApiError ? error.body?.current : undefined;
    if (
      error instanceof ApiError &&
      error.code === "version_conflict" &&
      isQuestionOut(current)
    ) {
      reloadFromServer(current);
      toast.error(t("review.errors.stale"));
      return;
    }
    toast.error(errorMessage(error, t("review.errors.action")));
  };

  const approve = async (force = false) => {
    if (!question || !isOpen) return;
    const saved = await ensureSaved();
    if (!saved) return;
    const nextId = pickNextId(items, saved.id);
    try {
      await approveMut.mutateAsync({
        id: saved.id,
        version: saved.version,
        force,
      });
      setBlocked(null);
      toast.success(t("review.toast.approved", { label: saved.number_label }));
      afterDecision(nextId);
    } catch (error) {
      handleActionError(error, saved);
    }
  };

  const reject = async (reason: string) => {
    if (!question) return;
    setRejectTarget(null);
    const saved = await ensureSaved();
    if (!saved) return;
    const nextId = pickNextId(items, saved.id);
    try {
      await rejectMut.mutateAsync({
        id: saved.id,
        version: saved.version,
        ...(reason ? { reason } : {}),
      });
      toast.success(t("review.toast.rejected", { label: saved.number_label }));
      afterDecision(nextId);
    } catch (error) {
      handleActionError(error, saved);
    }
  };

  const reopen = async () => {
    if (!question) return;
    try {
      await reopenMut.mutateAsync({
        id: question.id,
        version: question.version,
      });
    } catch (error) {
      handleActionError(error, question);
    }
  };

  const runBulk = async (
    action: "approve" | "reject" | "set_metadata",
    extra: {
      reason?: string;
      metadata?: {
        difficulty?: number;
        tags_add: string[];
        tags_remove: string[];
      };
    } = {},
  ) => {
    const ids = [...checked];
    try {
      const out = await bulkMut.mutateAsync({
        action,
        ids,
        ...(extra.reason ? { reason: extra.reason } : {}),
        ...(extra.metadata ? { metadata: extra.metadata } : {}),
      });
      const failedCodes = [
        ...new Set(
          out.results.filter((r) => !r.ok).map((r) => r.code ?? "error"),
        ),
      ].join(", ");
      const text = t("review.bulk.result", {
        ok: out.succeeded,
        failed: out.failed,
      });
      if (out.failed > 0) toast.warning(`${text} (${failedCodes})`);
      else toast.success(text);
      setChecked(new Set());
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.action")));
    }
  };

  // --- pages & regions ----------------------------------------------------------------------
  const pagesList = useMemo(() => pagesQuery.data ?? [], [pagesQuery.data]);
  const questionPageIds = useMemo(
    () => (question ? pageIdsOf(question.regions) : []),
    [question],
  );
  const pageIdx =
    question?.id === pageSel.qid
      ? Math.min(pageSel.idx, Math.max(0, questionPageIds.length - 1))
      : 0;
  const currentPage =
    pagesList.find((p) => p.id === questionPageIds[pageIdx]) ??
    (questionPageIds.length === 0 ? pagesList[0] : undefined);
  const pageDetail = usePageDetail(sourceId, currentPage?.page_number);
  const extraction = useMemo(
    () => parseExtraction(pageDetail.data?.extraction),
    [pageDetail.data],
  );

  const assetIds = useMemo(() => {
    const ids = new Set(question ? assetIdsOf(question) : []);
    for (const q of sourceQuestions.data ?? []) {
      if (parseRegions(q.regions).some((r) => r.page === currentPage?.id)) {
        assetIdsOf(q).forEach((id) => ids.add(id));
      }
    }
    return [...ids];
  }, [question, sourceQuestions.data, currentPage]);
  const assetQueries = useAssets(assetIds);
  const assetMap = useMemo(
    () =>
      new Map(
        assetQueries.flatMap((a) =>
          a.data ? [[a.data.id, a.data] as const] : [],
        ),
      ),
    [assetQueries],
  );

  const regions = useMemo<Region[]>(() => {
    if (!currentPage) return [];
    const list: Region[] = [];
    for (const q of sourceQuestions.data ?? []) {
      const own = parseRegions(q.regions);
      for (const r of own.filter((x) => x.page === currentPage.id)) {
        list.push({
          id: `q:${q.id}`,
          box: r.box,
          kind: "question",
          status: regionStatus(q.status, q.issues),
          label: q.number_label,
        });
      }
      assetIdsOf(q).forEach((assetId, i) => {
        const override = figureBoxes[assetId];
        const asset = assetMap.get(assetId);
        const box =
          override?.pageId === currentPage.id
            ? override.box
            : asset?.source_page_id === currentPage.id
              ? toBox(asset.region)
              : undefined;
        if (box) {
          list.push({
            id: `f:${assetId}`,
            box,
            kind: "figure",
            status: "ok",
            label: `${q.number_label}.${String(i + 1)}`,
          });
        }
      });
    }
    list.push(...stimulusRegions(stimuli.data ?? [], currentPage.id));
    extraction.headings.forEach((h, i) => {
      list.push({
        id: `h:${String(i)}`,
        box: h.box,
        kind: "heading",
        status: "ok",
        label: h.text,
      });
    });
    return list;
  }, [
    currentPage,
    sourceQuestions.data,
    stimuli.data,
    extraction,
    figureBoxes,
    assetMap,
  ]);

  const selectedRegion =
    question?.id === regionSel.qid
      ? regionSel.id
      : question
        ? `q:${question.id}`
        : "";
  const selectedFigureId = selectedRegion.startsWith("f:")
    ? selectedRegion.slice(2)
    : undefined;
  const canvasMode: PageCanvasMode = tool
    ? "draw"
    : selectedFigureId
      ? "edit"
      : "view";

  const resolveAsset = useCallback(
    (id: string) => assetImageUrl(id, assetMap.get(id)?.updated_at),
    [assetMap],
  );

  const onCanvasSelect = (id: string) => {
    if (!id) return;
    if (id.startsWith("q:")) {
      const qid = id.slice(2);
      if (qid !== selectedId) select(qid);
      else setRegionSel({ qid, id });
      return;
    }
    if (question) setRegionSel({ qid: question.id, id });
  };

  const onCanvasChange = async (id: string, box: Box) => {
    if (!id.startsWith("f:") || !currentPage) return;
    const assetId = id.slice(2);
    const previous = figureBoxes[assetId];
    setFigureBoxes((prev) => ({
      ...prev,
      [assetId]: { pageId: currentPage.id, box },
    }));
    try {
      const asset = await recropMut.mutateAsync({ assetId, box });
      queryClient.setQueryData(assetKey(assetId), asset);
      setFigureBoxes((prev) => {
        const next = { ...prev };
        Reflect.deleteProperty(next, assetId);
        return next;
      });
      toast.success(t("review.toast.recropped"));
    } catch (error) {
      setFigureBoxes((prev) => {
        const next = { ...prev };
        if (previous) next[assetId] = previous;
        else Reflect.deleteProperty(next, assetId);
        return next;
      });
      toast.error(errorMessage(error, t("review.errors.recrop")));
    }
  };

  const onCanvasCreate = async (box: Box) => {
    if (!question || !currentPage) return;
    const activeTool = tool;
    setTool(null);
    if (activeTool === "figure") {
      const saved = await ensureSaved();
      if (!saved) return;
      try {
        const asset = await addFigureMut.mutateAsync({
          id: saved.id,
          pageId: currentPage.id,
          box,
        });
        queryClient.setQueryData(assetKey(asset.id), asset);
        setRegionSel({ qid: saved.id, id: `f:${asset.id}` });
        toast.success(t("review.toast.figureAdded"));
      } catch (error) {
        toast.error(errorMessage(error, t("review.errors.figure")));
      }
    } else if (activeTool === "missed") {
      try {
        const result = await extractMut.mutateAsync({
          sourceId,
          pageNumber: currentPage.page_number,
          box,
        });
        setMissed({ draft: result, box, pageId: currentPage.id });
      } catch (error) {
        toast.error(errorMessage(error, t("review.errors.extractRegion")));
      }
    }
  };

  const confirmRemoveFigure = async () => {
    const assetId = removeAsset;
    setRemoveAsset(null);
    if (!assetId) return;
    const saved = await ensureSaved();
    if (!saved) return;
    try {
      await deleteFigureMut.mutateAsync({ id: saved.id, assetId });
      setRegionSel({ qid: saved.id, id: `q:${saved.id}` });
      toast.success(t("review.toast.figureRemoved"));
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.figure")));
    }
  };

  // --- split / merge ------------------------------------------------------------------------
  const split = async (
    at: { field: "stem"; offset: number } | { choice_index: number },
  ) => {
    const saved = await ensureSaved();
    if (!saved) return;
    try {
      await splitMut.mutateAsync({ id: saved.id, body: { at } });
      toast.success(t("review.toast.split"));
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.split")));
    }
  };

  const splitAtCursor = () => {
    const offset = stemRef.current?.selectionStart ?? draft?.stem.length ?? 0;
    void split({ field: "stem", offset });
  };

  const orderedQuestions = useMemo(
    () =>
      [...(sourceQuestions.data ?? [])].sort((a, b) => a.position - b.position),
    [sourceQuestions.data],
  );
  const nextQuestion = question
    ? orderedQuestions[
        orderedQuestions.findIndex((q) => q.id === question.id) + 1
      ]
    : undefined;

  const confirmMerge = async () => {
    setMergeOpen(false);
    if (!question || !nextQuestion) return;
    const saved = await ensureSaved();
    if (!saved) return;
    try {
      const merged = await mergeMut.mutateAsync([saved.id, nextQuestion.id]);
      toast.success(t("review.toast.merged"));
      select(merged.id);
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.merge")));
    }
  };

  // --- issues -------------------------------------------------------------------------------
  const resolveIssue = async (issue: IssueOut, resolved: boolean) => {
    try {
      await resolveMut.mutateAsync({ id: issue.id, resolved });
    } catch (error) {
      toast.error(errorMessage(error, t("review.errors.action")));
    }
  };

  const applyFix = (issue: IssueOut) => {
    const fix = suggestedFix(issue);
    const current = draftRef.current;
    if (!fix || !current) return;
    const next: Draft =
      fix.field === "type"
        ? isQuestionType(fix.value)
          ? { ...current, type: fix.value }
          : current
        : { ...current, [fix.field]: fix.value };
    setDraft(next);
    void save(next);
  };

  // --- keyboard -----------------------------------------------------------------------------
  const dialogOpen =
    conflict !== null ||
    blocked !== null ||
    rejectTarget !== null ||
    bulkMetaOpen ||
    helpOpen ||
    mergeOpen ||
    removeAsset !== null ||
    reextractOpen ||
    stimulusOpen ||
    missed !== null;

  useReviewShortcuts(
    {
      next: () => {
        move(1);
      },
      prev: () => {
        move(-1);
      },
      approve: () => {
        void approve();
      },
      reject: () => {
        if (isOpen) setRejectTarget("one");
      },
      edit: () => {
        setPane("editor");
        stemRef.current?.focus();
      },
      save: () => {
        void save();
      },
      figure: () => {
        setPane("page");
        setTool((prev) => (prev === "figure" ? null : "figure"));
      },
      cancel: () => {
        setTool(null);
      },
      help: () => {
        setHelpOpen(true);
      },
    },
    dialogOpen,
  );

  const tagSuggestions = useMemo(
    () =>
      [...new Set((sourceQuestions.data ?? []).flatMap((q) => q.tags))].sort(),
    [sourceQuestions.data],
  );
  const stimulus = question?.stimulus_id
    ? stimuli.data?.find((s) => s.id === question.stimulus_id)
    : undefined;

  if (me.data?.role === "teacher") {
    return <Navigate to="/bank" replace />;
  }

  const paneClass = (id: Pane) =>
    cn(
      "bg-card border-border min-h-0 flex-col overflow-hidden rounded-lg border",
      pane === id ? "flex" : "hidden",
      "lg:flex",
    );

  const busy =
    patchMut.isPending ||
    approveMut.isPending ||
    rejectMut.isPending ||
    splitMut.isPending ||
    mergeMut.isPending;

  return (
    <section
      className="flex h-[calc(100vh-7rem)] min-h-[32rem] flex-col gap-3"
      data-testid="review-workspace"
    >
      <header className="flex flex-wrap items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/sources/${sourceId}`}>
            <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
            {t("review.workspace.back")}
          </Link>
        </Button>
        <h1 className="text-lg font-bold tracking-tight">
          {t("review.workspace.title")}
          {source.data ? ` · ${source.data.title}` : ""}
        </h1>
        <span className="ms-auto flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!currentPage}
            onClick={() => {
              setReextractOpen(true);
            }}
          >
            <RefreshCw aria-hidden="true" />
            {t("review.workspace.reextract")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            aria-label={t("review.shortcuts.title")}
            onClick={() => {
              setHelpOpen(true);
            }}
          >
            <HelpCircle aria-hidden="true" />
            <kbd className="font-mono text-xs">?</kbd>
          </Button>
        </span>
      </header>

      <div
        role="tablist"
        aria-label={t("review.panes.switch")}
        className="flex gap-1 lg:hidden"
      >
        {(["queue", "page", "editor"] as const).map((id) => (
          <Button
            key={id}
            type="button"
            role="tab"
            size="sm"
            variant={pane === id ? "default" : "outline"}
            aria-selected={pane === id}
            className="flex-1"
            onClick={() => {
              setPane(id);
            }}
          >
            {t(`review.panes.${id}`)}
          </Button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[18rem_minmax(0,1fr)_28rem]">
        <aside
          aria-label={t("review.panes.queue")}
          className={paneClass("queue")}
        >
          <QueuePane
            queue={queue.data}
            isLoading={queue.isLoading}
            isError={queue.isError}
            filters={filters}
            onFiltersChange={setFilters}
            selectedId={selectedId}
            onSelect={(id) => {
              select(id);
              setPane("page");
            }}
            checked={checked}
            onCheckedChange={setChecked}
            onBulkApprove={() => {
              void runBulk("approve");
            }}
            onBulkReject={() => {
              setRejectTarget("bulk");
            }}
            onBulkMetadata={() => {
              setBulkMetaOpen(true);
            }}
            listRef={listRef}
          />
        </aside>

        <section
          aria-label={t("review.panes.page")}
          className={paneClass("page")}
        >
          <div className="border-border flex flex-wrap items-center gap-2 border-b p-2">
            {questionPageIds.length > 1 ? (
              <div
                role="group"
                aria-label={t("review.page.switcher")}
                className="flex items-center gap-1"
              >
                {questionPageIds.map((pid, i) => {
                  const number = pagesList.find(
                    (p) => p.id === pid,
                  )?.page_number;
                  return (
                    <Button
                      key={pid}
                      type="button"
                      size="sm"
                      variant={i === pageIdx ? "default" : "outline"}
                      aria-pressed={i === pageIdx}
                      onClick={() => {
                        if (question) setPageSel({ qid: question.id, idx: i });
                      }}
                    >
                      {t("review.queue.page", { page: number ?? "—" })}
                    </Button>
                  );
                })}
              </div>
            ) : currentPage ? (
              <span className="text-sm font-medium">
                {t("review.queue.page", { page: currentPage.page_number })}
              </span>
            ) : null}
            <span className="ms-auto flex flex-wrap items-center gap-1">
              <Button
                type="button"
                size="sm"
                variant={tool === "figure" ? "default" : "outline"}
                aria-pressed={tool === "figure"}
                disabled={!question || !currentPage}
                onClick={() => {
                  setTool((prev) => (prev === "figure" ? null : "figure"));
                }}
              >
                <ImagePlus aria-hidden="true" />
                {t("review.page.addFigure")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant={tool === "missed" ? "default" : "outline"}
                aria-pressed={tool === "missed"}
                disabled={!currentPage}
                onClick={() => {
                  setTool((prev) => (prev === "missed" ? null : "missed"));
                }}
              >
                <ScanSearch aria-hidden="true" />
                {t("review.page.addMissed")}
              </Button>
              {selectedFigureId ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setRemoveAsset(selectedFigureId);
                  }}
                >
                  <Trash2 aria-hidden="true" />
                  {t("review.editor.removeFigure")}
                </Button>
              ) : null}
            </span>
          </div>
          {tool ? (
            <p
              role="status"
              className="bg-muted flex items-center gap-1 px-2 py-1 text-xs"
              data-testid="draw-hint"
            >
              <Crop className="size-3.5" aria-hidden="true" />
              {tool === "figure"
                ? t("review.page.drawFigureHint")
                : t("review.page.drawMissedHint")}
            </p>
          ) : selectedFigureId ? (
            <p role="status" className="bg-muted px-2 py-1 text-xs">
              {t("review.page.editFigureHint")}
            </p>
          ) : null}
          <div className="flex min-h-0 flex-1 p-2">
            {currentPage ? (
              <PageCanvas
                key={currentPage.id}
                src={getPageImageUrl(
                  sourceId,
                  currentPage.page_number,
                  "display",
                )}
                width={currentPage.width_px ?? 800}
                height={currentPage.height_px ?? 1130}
                regions={regions}
                selectedId={selectedRegion}
                mode={canvasMode}
                onSelect={onCanvasSelect}
                onChange={(id, box) => {
                  void onCanvasChange(id, box);
                }}
                onCreate={(box) => {
                  void onCanvasCreate(box);
                }}
                className="h-full w-full flex-1"
              />
            ) : pagesQuery.isLoading || questionQuery.isLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <p className="text-muted-foreground p-4 text-sm">
                {t("review.page.none")}
              </p>
            )}
          </div>
        </section>

        <section
          aria-label={t("review.panes.editor")}
          className={paneClass("editor")}
        >
          {question && draft ? (
            <EditorPane
              question={question}
              draft={draft}
              onDraftChange={setDraft}
              dirty={dirty}
              busy={busy}
              stemRef={stemRef}
              resolveAsset={resolveAsset}
              stimulus={stimulus}
              tagSuggestions={tagSuggestions}
              hasNextQuestion={nextQuestion !== undefined}
              onSave={() => {
                void save();
              }}
              onAutosave={() => {
                if (dirty) void save();
              }}
              onApprove={() => {
                void approve();
              }}
              onReject={() => {
                setRejectTarget("one");
              }}
              onReopen={() => {
                void reopen();
              }}
              onResolveIssue={(issue, resolved) => {
                void resolveIssue(issue, resolved);
              }}
              onApplyFix={applyFix}
              onSplitStem={splitAtCursor}
              onSplitChoice={(index) => {
                void split({ choice_index: index });
              }}
              onMerge={() => {
                setMergeOpen(true);
              }}
              onAddFigure={() => {
                setPane("page");
                setTool("figure");
              }}
              onRemoveFigure={setRemoveAsset}
              onEditStimulus={() => {
                setStimulusOpen(true);
              }}
            />
          ) : questionQuery.isError ? (
            <p role="alert" className="text-destructive p-4 text-sm">
              {t("review.errors.load")}
            </p>
          ) : questionQuery.isLoading ? (
            <div className="flex flex-col gap-2 p-2">
              <Skeleton className="h-10" />
              <Skeleton className="h-40" />
            </div>
          ) : (
            <p className="text-muted-foreground p-4 text-sm">
              {t("review.editor.empty")}
            </p>
          )}
        </section>
      </div>

      <ConflictDialog
        current={conflict?.current ?? null}
        draft={draft ?? draftFromQuestion(conflict?.current ?? EMPTY_QUESTION)}
        onReload={() => {
          if (conflict) reloadFromServer(conflict.current);
        }}
        onOverwrite={() => {
          void overwrite();
        }}
        onClose={() => {
          setConflict(null);
        }}
      />
      <ApproveBlockedDialog
        open={blocked !== null}
        message={blocked?.message ?? ""}
        issues={
          question
            ? unresolvedIssues(question.issues).filter(
                (i) => i.severity === "error",
              )
            : []
        }
        isAdmin={me.data?.role === "admin"}
        pending={approveMut.isPending}
        onForce={() => {
          void approve(true);
        }}
        onClose={() => {
          setBlocked(null);
        }}
      />
      <ReasonDialog
        open={rejectTarget !== null}
        onConfirm={(reason) => {
          if (rejectTarget === "bulk") {
            setRejectTarget(null);
            void runBulk("reject", { reason });
          } else {
            void reject(reason);
          }
        }}
        onClose={() => {
          setRejectTarget(null);
        }}
      />
      <BulkMetadataDialog
        open={bulkMetaOpen}
        count={checked.size}
        pending={bulkMut.isPending}
        onConfirm={(metadata) => {
          setBulkMetaOpen(false);
          void runBulk("set_metadata", { metadata });
        }}
        onClose={() => {
          setBulkMetaOpen(false);
        }}
      />
      <ShortcutsDialog
        open={helpOpen}
        onClose={() => {
          setHelpOpen(false);
        }}
      />
      <ConfirmDialog
        open={mergeOpen}
        title={t("review.merge.title")}
        description={t("review.merge.description")}
        confirmLabel={t("review.merge.confirm")}
        testId="merge-dialog"
        onConfirm={() => {
          void confirmMerge();
        }}
        onClose={() => {
          setMergeOpen(false);
        }}
      >
        <div className="flex flex-col gap-2 text-sm">
          {[question, nextQuestion].map((q) =>
            q ? (
              <div key={q.id} className="border-border rounded-md border p-2">
                <p className="font-semibold">{q.number_label}</p>
                <QmdRenderer
                  source={q.stem}
                  lang={q.language}
                  resolveAsset={resolveAsset}
                  className="max-h-24 overflow-auto"
                />
              </div>
            ) : null,
          )}
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={removeAsset !== null}
        title={t("review.figure.removeTitle")}
        description={t("review.figure.removeDescription")}
        confirmLabel={t("review.editor.removeFigure")}
        destructive
        testId="remove-figure-dialog"
        onConfirm={() => {
          void confirmRemoveFigure();
        }}
        onClose={() => {
          setRemoveAsset(null);
        }}
      />
      {currentPage ? (
        <ReextractDialog
          open={reextractOpen}
          sourceId={sourceId}
          pageNumber={currentPage.page_number}
          onClose={() => {
            setReextractOpen(false);
          }}
        />
      ) : null}
      {stimulusOpen && stimulus ? (
        <StimulusDialog
          content={stimulus.content}
          lang={question?.language ?? "ar"}
          resolveAsset={resolveAsset}
          pending={stimulusMut.isPending}
          onSave={async (content) => {
            try {
              await stimulusMut.mutateAsync({ id: stimulus.id, content });
              setStimulusOpen(false);
            } catch (error) {
              toast.error(errorMessage(error, t("review.errors.action")));
            }
          }}
          onClose={() => {
            setStimulusOpen(false);
          }}
        />
      ) : null}
      {missed && source.data ? (
        <MissedQuestionDialog
          draft={missed.draft}
          box={missed.box}
          pageId={missed.pageId}
          subjectId={source.data.subject_id}
          sourceId={sourceId}
          lang={question?.language ?? "ar"}
          onCreated={(created) => {
            setMissed(null);
            select(created.id);
          }}
          onClose={() => {
            setMissed(null);
          }}
        />
      ) : null}
    </section>
  );
}

function toBox(region: readonly number[]): Box | undefined {
  const [x0, y0, x1, y1] = region;
  return x0 !== undefined &&
    y0 !== undefined &&
    x1 !== undefined &&
    y1 !== undefined
    ? [x0, y0, x1, y1]
    : undefined;
}

const EMPTY_QUESTION = {
  answer: null,
  chapter_id: null,
  choices: [],
  confidence: 1,
  created_at: "",
  difficulty: null,
  difficulty_reason: null,
  difficulty_source: null,
  duplicate_of_id: null,
  explanation: null,
  id: "",
  issues: [],
  language: "ar",
  lesson_id: null,
  number_label: "",
  position: 0,
  regions: [],
  source_id: null,
  status: "draft",
  stem: "",
  stimulus_id: null,
  stimulus_position: null,
  subject_id: "",
  tags: [],
  type: "short_answer",
  updated_at: "",
  version: 0,
} satisfies QuestionOut;

function StimulusDialog({
  content,
  lang,
  resolveAsset,
  pending,
  onSave,
  onClose,
}: {
  content: string;
  lang: "ar" | "en";
  resolveAsset: (id: string) => string | undefined;
  pending: boolean;
  onSave: (content: string) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState(content);
  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-2xl" data-testid="stimulus-dialog">
        <DialogHeader>
          <DialogTitle>{t("review.editor.editStimulus")}</DialogTitle>
          <DialogDescription>
            {t("review.editor.stimulusHint")}
          </DialogDescription>
        </DialogHeader>
        <QmdEditor
          id="stimulus-content"
          label={t("review.editor.stimulus")}
          value={value}
          lang={lang}
          resolveAsset={resolveAsset}
          rows={8}
          onChange={setValue}
        />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("review.common.cancel")}
          </Button>
          <Button
            type="button"
            disabled={pending}
            onClick={() => {
              void onSave(value);
            }}
          >
            {t("review.editor.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
