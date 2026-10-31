import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Text,
    and_,
    case,
    cast,
    func,
    literal_column,
    or_,
    select,
    tuple_,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSQUERY
from sqlalchemy.orm import Session

from qbank.models import (
    Chapter,
    Lesson,
    Question,
    Role,
    Source,
    SourcePage,
    ValidationIssue,
)
from qbank.schemas.bank import (
    BankFacets,
    BankQuestionOut,
    BankSearchOut,
    BankStatsOut,
    ChapterFacet,
    IssuesCount,
    LessonFacet,
    QuestionsMove,
    QuestionsMoveOut,
    SourceFacet,
    TagCount,
)
from qbank.services.errors import Invalid, NotFound
from qbank.services.scoping import get, scoped
from qbank.services.unit_of_work import found, save
from qbank.text.normalize import normalize_ar

SortMode = Literal["relevance", "newest", "difficulty", "source_order"]
MatchMode = Literal["fts", "fuzzy"]

_FUZZY_THRESHOLD = 0.3
_CURSOR_PARTS = 3

_GRP_TOTAL = 63
_GRP_CHAPTER = 31
_GRP_LESSON = 47
_GRP_TYPE = 55
_GRP_DIFFICULTY = 59
_GRP_STATUS = 61
_GRP_SOURCE = 62

_STATS_GRP_TOTAL = 7
_STATS_GRP_STATUS = 3
_STATS_GRP_TYPE = 5
_STATS_GRP_DIFF = 6
_TAX_GRP_CHAPTER = 1
_TAX_GRP_LESSON = 2


@dataclass(frozen=True)
class SearchFilters:
    org_id: UUID
    role: Role
    norm_q: str = ""
    subject_id: UUID | None = None
    chapter_ids: list[UUID] | None = None
    lesson_ids: list[UUID] | None = None
    types: list[str] | None = None
    difficulty_min: int | None = None
    difficulty_max: int | None = None
    statuses: list[str] | None = None
    source_ids: list[UUID] | None = None
    tags: list[str] | None = None
    has_figure: bool | None = None
    has_answer: bool | None = None
    exam_title: str | None = None
    exclude_duplicates: bool = True


@dataclass(frozen=True)
class PageSpec:
    sort: SortMode
    match_mode: MatchMode
    cursor_rest: str | None
    limit: int


def _build_tsquery(norm_q: str) -> ColumnElement[Any]:
    web_tsq = func.websearch_to_tsquery("simple", norm_q)
    plain_tsq = func.plainto_tsquery("simple", norm_q)
    base_text = case(
        (cast(web_tsq, Text) != "", cast(web_tsq, Text)),
        else_=cast(plain_tsq, Text),
    )
    return cast(func.regexp_replace(base_text, r"'([^']*)$", r"':*\1"), TSQUERY)


def _has_answer_expr() -> ColumnElement[bool]:
    has_text = and_(Question.answer.is_not(None), func.btrim(Question.answer) != "")
    has_choice = Question.choices.op("@>")(cast([{"is_correct": True}], JSONB))
    return or_(has_text, has_choice)


def _build_clauses(  # noqa: PLR0912 -- each filter dimension adds one independent predicate
    filters: SearchFilters,
    match_mode: MatchMode,
    *,
    exclude_dim: str | None = None,
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [Question.org_id == filters.org_id]
    if filters.exclude_duplicates:
        clauses.append(Question.duplicate_of_id.is_(None))
    if filters.norm_q:
        if match_mode == "fts":
            clauses.append(Question.search_vector.op("@@")(_build_tsquery(filters.norm_q)))
        else:
            clauses.append(
                and_(
                    Question.normalized_text.op("%")(filters.norm_q),
                    func.similarity(Question.normalized_text, filters.norm_q) > _FUZZY_THRESHOLD,
                )
            )
    if filters.subject_id is not None:
        clauses.append(Question.subject_id == filters.subject_id)
    if exclude_dim != "chapter" and filters.chapter_ids:
        clauses.append(Question.chapter_id.in_(filters.chapter_ids))
    if exclude_dim != "lesson" and filters.lesson_ids:
        clauses.append(Question.lesson_id.in_(filters.lesson_ids))
    if exclude_dim != "type" and filters.types:
        clauses.append(Question.type.in_(filters.types))
    if exclude_dim != "difficulty":
        if filters.difficulty_min is not None:
            clauses.append(Question.difficulty >= filters.difficulty_min)
        if filters.difficulty_max is not None:
            clauses.append(Question.difficulty <= filters.difficulty_max)
    if filters.role == Role.teacher:
        clauses.append(Question.status == "approved")
    elif exclude_dim != "status" and filters.statuses:
        clauses.append(Question.status.in_(filters.statuses))
    if exclude_dim != "source" and filters.source_ids:
        clauses.append(Question.source_id.in_(filters.source_ids))
    if exclude_dim != "tags" and filters.tags:
        clauses.append(Question.tags.overlap(cast(filters.tags, ARRAY(Text))))
    if filters.has_figure is True:
        clauses.append(Question.stem.contains("asset:"))
    elif filters.has_figure is False:
        clauses.append(~Question.stem.contains("asset:"))
    if filters.has_answer is True:
        clauses.append(_has_answer_expr())
    elif filters.has_answer is False:
        clauses.append(~_has_answer_expr())
    if filters.exam_title is not None:
        clauses.append(Question.metadata_json.op("->>")("exam_title") == filters.exam_title)
    return clauses


def _encode_cursor(payload: str) -> str:
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str, expected_sort: SortMode) -> tuple[MatchMode | None, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        parts = raw.split("|", 2)
        if len(parts) != _CURSOR_PARTS:
            raise ValueError("Invalid cursor parts")
        sort_str, mode_str, rest = parts
        if sort_str != expected_sort or mode_str not in ("fts", "fuzzy"):
            raise ValueError("Cursor sort or mode mismatch")
        mode: MatchMode = "fuzzy" if mode_str == "fuzzy" else "fts"
        return mode, rest
    except (ValueError, UnicodeError) as exc:
        raise Invalid("invalid_cursor") from exc


def _parse_offset(cursor_rest: str | None) -> int:
    if cursor_rest is None:
        return 0
    try:
        offset = int(cursor_rest)
        if offset < 0:
            raise ValueError("Negative offset")
        return offset
    except ValueError as exc:
        raise Invalid("invalid_cursor") from exc


def _apply_newest_sort(stmt: Any, cursor_rest: str | None) -> Any:
    if cursor_rest is not None:
        try:
            dt_str, id_str = cursor_rest.split("|", 1)
            dt = datetime.fromisoformat(dt_str)
            uid = UUID(id_str)
        except ValueError as exc:
            raise Invalid("invalid_cursor") from exc
        stmt = stmt.where(tuple_(Question.created_at, Question.id) < tuple_(dt, uid))
    return stmt.order_by(Question.created_at.desc(), Question.id.desc())


def _apply_difficulty_sort(stmt: Any, cursor_rest: str | None) -> Any:
    if cursor_rest is not None:
        try:
            diff_str, id_str = cursor_rest.split("|", 1)
            uid = UUID(id_str)
            if diff_str == "null":
                stmt = stmt.where(and_(Question.difficulty.is_(None), Question.id > uid))
            else:
                diff_val = int(diff_str)
                stmt = stmt.where(
                    or_(
                        and_(Question.difficulty == diff_val, Question.id > uid),
                        Question.difficulty > diff_val,
                        Question.difficulty.is_(None),
                    )
                )
        except ValueError as exc:
            raise Invalid("invalid_cursor") from exc
    return stmt.order_by(Question.difficulty.asc().nulls_last(), Question.id.asc())


def _apply_sort_and_cursor(stmt: Any, norm_q: str, spec: PageSpec) -> tuple[Any, int]:
    if spec.sort == "newest":
        return _apply_newest_sort(stmt, spec.cursor_rest).limit(spec.limit + 1), 0
    if spec.sort == "difficulty":
        return _apply_difficulty_sort(stmt, spec.cursor_rest).limit(spec.limit + 1), 0

    offset = _parse_offset(spec.cursor_rest)
    if spec.sort == "source_order":
        stmt = stmt.order_by(
            Question.source_id.asc().nulls_last(), Question.position.asc(), Question.id.asc()
        )
    elif norm_q and spec.match_mode == "fts":
        rank = func.ts_rank_cd(Question.search_vector, _build_tsquery(norm_q))
        stmt = stmt.order_by(rank.desc(), Question.created_at.desc(), Question.id.desc())
    elif norm_q and spec.match_mode == "fuzzy":
        sim = func.similarity(Question.normalized_text, norm_q)
        stmt = stmt.order_by(sim.desc(), Question.created_at.desc(), Question.id.desc())
    else:
        stmt = stmt.order_by(Question.created_at.desc(), Question.id.desc())
    if offset > 0:
        stmt = stmt.offset(offset)
    return stmt.limit(spec.limit + 1), offset


def _extract_page_ref(
    regions: list[dict[str, object]], metadata_json: dict[str, object]
) -> tuple[UUID | None, int | None]:
    page_uuid: UUID | None = None
    page_int: int | None = None
    if regions:
        first = regions[0]
        p_num = first.get("page_number")
        page_val = first.get("page")
        if isinstance(p_num, int):
            page_int = p_num
        elif isinstance(page_val, int):
            page_int = page_val
        elif isinstance(page_val, str):
            if page_val.isdigit():
                page_int = int(page_val)
            else:
                try:
                    page_uuid = UUID(page_val)
                except ValueError:
                    page_uuid = None
    if page_uuid is None and page_int is None:
        for key in ("page_number", "page"):
            val = metadata_json.get(key)
            if isinstance(val, int):
                page_int = val
                break
    return page_uuid, page_int


def _execute_page_query(
    db: Session,
    filters: SearchFilters,
    spec: PageSpec,
) -> tuple[list[Any], int]:
    clauses = _build_clauses(filters, spec.match_mode)
    base_stmt = (
        select(
            Question.id,
            Question.subject_id,
            Question.number_label,
            Question.type,
            func.left(Question.stem, 200).label("stem_preview"),
            func.jsonb_array_length(Question.choices).label("choices_count"),
            Question.difficulty,
            Question.tags,
            Question.status,
            Question.chapter_id,
            Chapter.title.label("chapter_title"),
            Question.lesson_id,
            Lesson.title.label("lesson_title"),
            Question.source_id,
            Source.title.label("source_title"),
            Question.stimulus_id,
            Question.stem.contains("asset:").label("has_figure"),
            Question.regions,
            Question.metadata_json.label("metadata_json"),
            Question.created_at,
        )
        .outerjoin(Chapter, Question.chapter_id == Chapter.id)
        .outerjoin(Lesson, Question.lesson_id == Lesson.id)
        .outerjoin(Source, Question.source_id == Source.id)
        .where(*clauses)
    )
    stmt, offset = _apply_sort_and_cursor(base_stmt, filters.norm_q, spec)
    return list(db.execute(stmt).all()), offset


def _hydrate_items(db: Session, rows: list[Any]) -> list[BankQuestionOut]:
    if not rows:
        return []
    q_ids = [r.id for r in rows]
    page_uuids: set[UUID] = set()
    page_refs: list[tuple[UUID | None, int | None]] = []
    for r in rows:
        p_uuid, p_int = _extract_page_ref(r.regions or [], r.metadata_json or {})
        page_refs.append((p_uuid, p_int))
        if p_uuid is not None:
            page_uuids.add(p_uuid)

    page_numbers: dict[UUID, int] = (
        dict(
            db.execute(
                select(SourcePage.id, SourcePage.page_number).where(SourcePage.id.in_(page_uuids))
            ).all()
        )
        if page_uuids
        else {}
    )

    issue_counts: dict[UUID, IssuesCount] = {qid: IssuesCount() for qid in q_ids}
    for qid, sev, cnt in db.execute(
        select(ValidationIssue.question_id, ValidationIssue.severity, func.count())
        .where(ValidationIssue.question_id.in_(q_ids), ValidationIssue.resolved_at.is_(None))
        .group_by(ValidationIssue.question_id, ValidationIssue.severity)
    ):
        if sev == "error":
            issue_counts[qid].error = int(cnt)
        elif sev == "warning":
            issue_counts[qid].warning = int(cnt)

    items: list[BankQuestionOut] = []
    for r, (p_uuid, p_int) in zip(rows, page_refs, strict=True):
        source_page = p_int if p_int is not None else (page_numbers.get(p_uuid) if p_uuid else None)
        items.append(
            BankQuestionOut(
                id=r.id,
                subject_id=r.subject_id,
                number_label=r.number_label,
                type=r.type,
                stem_preview=r.stem_preview,
                choices_count=int(r.choices_count or 0),
                difficulty=r.difficulty,
                tags=list(r.tags or []),
                status=r.status,
                chapter_id=r.chapter_id,
                chapter_title=r.chapter_title,
                lesson_id=r.lesson_id,
                lesson_title=r.lesson_title,
                source_id=r.source_id,
                source_title=r.source_title,
                source_page=source_page,
                stimulus_id=r.stimulus_id,
                has_figure=bool(r.has_figure),
                issues_count=issue_counts[r.id],
            )
        )
    return items


def _compute_facets(  # noqa: PLR0912, PLR0915 -- aggregates 7 facet dimensions and resolves titles
    db: Session,
    filters: SearchFilters,
    match_mode: MatchMode,
) -> BankFacets:
    all_clauses = _build_clauses(filters, match_mode)

    chapter_counts: dict[UUID, int] = {}
    lesson_counts: dict[UUID, int] = {}
    type_counts: dict[str, int] = {}
    difficulty_counts: dict[int, int] = {}
    status_counts: dict[str, int] = {}
    source_counts: dict[UUID, int] = {}
    total = 0

    has_chapter_filter = bool(filters.chapter_ids)
    has_lesson_filter = bool(filters.lesson_ids)
    has_type_filter = bool(filters.types)
    has_diff_filter = filters.difficulty_min is not None or filters.difficulty_max is not None
    has_status_filter = filters.role != Role.teacher and bool(filters.statuses)
    has_source_filter = bool(filters.source_ids)

    sets = [
        tuple_(),
        tuple_(Question.chapter_id),
        tuple_(Question.lesson_id),
        tuple_(Question.type),
        tuple_(Question.difficulty),
        tuple_(Question.status),
        tuple_(Question.source_id),
    ]

    grp_stmt = (
        select(
            func.grouping(
                Question.chapter_id,
                Question.lesson_id,
                Question.type,
                Question.difficulty,
                Question.status,
                Question.source_id,
            ).label("grp"),
            Question.chapter_id,
            Question.lesson_id,
            Question.type,
            Question.difficulty,
            Question.status,
            Question.source_id,
            func.count().label("cnt"),
        )
        .where(*all_clauses)
        .group_by(func.grouping_sets(*sets))
    )
    for row in db.execute(grp_stmt):
        grp = int(row.grp)
        cnt = int(row.cnt)
        if grp == _GRP_TOTAL:
            total = cnt
        elif grp == _GRP_CHAPTER and row.chapter_id is not None:
            chapter_counts[row.chapter_id] = cnt
        elif grp == _GRP_LESSON and row.lesson_id is not None:
            lesson_counts[row.lesson_id] = cnt
        elif grp == _GRP_TYPE and row.type is not None:
            type_counts[row.type] = cnt
        elif grp == _GRP_DIFFICULTY and row.difficulty is not None:
            difficulty_counts[int(row.difficulty)] = cnt
        elif grp == _GRP_STATUS and row.status is not None:
            status_counts[row.status] = cnt
        elif grp == _GRP_SOURCE and row.source_id is not None:
            source_counts[row.source_id] = cnt

    if has_chapter_filter:
        for cid, cnt in db.execute(
            select(Question.chapter_id, func.count())
            .where(
                *_build_clauses(filters, match_mode, exclude_dim="chapter"),
                Question.chapter_id.is_not(None),
            )
            .group_by(Question.chapter_id)
        ):
            if cid is not None:
                chapter_counts[cid] = int(cnt)

    if has_lesson_filter:
        for lid, cnt in db.execute(
            select(Question.lesson_id, func.count())
            .where(
                *_build_clauses(filters, match_mode, exclude_dim="lesson"),
                Question.lesson_id.is_not(None),
            )
            .group_by(Question.lesson_id)
        ):
            if lid is not None:
                lesson_counts[lid] = int(cnt)

    if has_type_filter:
        for qtype, cnt in db.execute(
            select(Question.type, func.count())
            .where(*_build_clauses(filters, match_mode, exclude_dim="type"))
            .group_by(Question.type)
        ):
            type_counts[qtype] = int(cnt)

    if has_diff_filter:
        for diff, cnt in db.execute(
            select(Question.difficulty, func.count())
            .where(
                *_build_clauses(filters, match_mode, exclude_dim="difficulty"),
                Question.difficulty.is_not(None),
            )
            .group_by(Question.difficulty)
        ):
            if diff is not None:
                difficulty_counts[int(diff)] = int(cnt)

    if has_status_filter:
        for st, cnt in db.execute(
            select(Question.status, func.count())
            .where(*_build_clauses(filters, match_mode, exclude_dim="status"))
            .group_by(Question.status)
        ):
            status_counts[st] = int(cnt)

    if has_source_filter:
        for sid, cnt in db.execute(
            select(Question.source_id, func.count())
            .where(
                *_build_clauses(filters, match_mode, exclude_dim="source"),
                Question.source_id.is_not(None),
            )
            .group_by(Question.source_id)
        ):
            if (
                sid is not None
            ):  # filtered above; narrows the type (source_id became nullable in T12)
                source_counts[sid] = int(cnt)

    chapters_out: list[ChapterFacet] = []
    if chapter_counts:
        chapters = db.scalars(
            scoped(select(Chapter), Chapter, filters.org_id)
            .where(Chapter.id.in_(chapter_counts.keys()))
            .order_by(Chapter.position.asc(), Chapter.id.asc())
        ).all()
        chapters_out = [
            ChapterFacet(id=c.id, title=c.title, count=chapter_counts[c.id]) for c in chapters
        ]

    lessons_out: list[LessonFacet] = []
    if lesson_counts:
        lessons = db.scalars(
            scoped(select(Lesson), Lesson, filters.org_id)
            .where(Lesson.id.in_(lesson_counts.keys()))
            .order_by(Lesson.position.asc(), Lesson.id.asc())
        ).all()
        lessons_out = [
            LessonFacet(
                id=les.id,
                chapter_id=les.chapter_id,
                title=les.title,
                count=lesson_counts[les.id],
            )
            for les in lessons
        ]

    sources_out: list[SourceFacet] = []
    if source_counts:
        sources = db.scalars(
            scoped(select(Source), Source, filters.org_id).where(
                Source.id.in_(source_counts.keys())
            )
        ).all()
        sources_out = sorted(
            (SourceFacet(id=s.id, title=s.title, count=source_counts[s.id]) for s in sources),
            key=lambda x: (-x.count, x.title, str(x.id)),
        )

    tag_col = func.unnest(Question.tags).label("tag")
    cnt_col = func.count().label("cnt")
    tag_clauses = _build_clauses(filters, match_mode, exclude_dim="tags")
    tag_stmt = (
        select(tag_col, cnt_col)
        .where(*tag_clauses)
        .group_by(literal_column("tag"))
        .order_by(literal_column("cnt").desc(), literal_column("tag").asc())
        .limit(30)
    )
    tags_out = [TagCount(tag=str(r.tag), count=int(r.cnt)) for r in db.execute(tag_stmt)]

    return BankFacets(
        total=total,
        chapters=chapters_out,
        lessons=lessons_out,
        types=type_counts,
        difficulties=difficulty_counts,
        statuses=status_counts,
        sources=sources_out,
        tags=tags_out,
    )


def search_questions(  # noqa: PLR0913, PLR0917 -- search endpoint parameters
    db: Session,
    org_id: UUID,
    role: Role,
    q: str | None = None,
    subject_id: UUID | None = None,
    chapter_ids: list[UUID] | None = None,
    lesson_ids: list[UUID] | None = None,
    types: list[str] | None = None,
    difficulty_min: int | None = None,
    difficulty_max: int | None = None,
    statuses: list[str] | None = None,
    source_ids: list[UUID] | None = None,
    tags: list[str] | None = None,
    has_figure: bool | None = None,
    has_answer: bool | None = None,
    exam_title: str | None = None,
    exclude_duplicates: bool = True,
    facets: bool = False,
    sort: SortMode | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> BankSearchOut:
    norm_q = normalize_ar(q) if q else ""
    effective_sort: SortMode = sort if sort is not None else ("relevance" if norm_q else "newest")

    cursor_mode: MatchMode | None = None
    cursor_rest: str | None = None
    if cursor is not None:
        cursor_mode, cursor_rest = _decode_cursor(cursor, effective_sort)

    filters = SearchFilters(
        org_id=org_id,
        role=role,
        norm_q=norm_q,
        subject_id=subject_id,
        chapter_ids=chapter_ids,
        lesson_ids=lesson_ids,
        types=types,
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        statuses=statuses,
        source_ids=source_ids,
        tags=tags,
        has_figure=has_figure,
        has_answer=has_answer,
        exam_title=exam_title,
        exclude_duplicates=exclude_duplicates,
    )

    match_mode: MatchMode = cursor_mode or "fts"
    rows, offset = _execute_page_query(
        db,
        filters,
        PageSpec(sort=effective_sort, match_mode=match_mode, cursor_rest=cursor_rest, limit=limit),
    )

    if norm_q and cursor_mode is None and not rows:
        fuzzy_rows, fuzzy_offset = _execute_page_query(
            db,
            filters,
            PageSpec(sort=effective_sort, match_mode="fuzzy", cursor_rest=None, limit=limit),
        )
        if fuzzy_rows:
            match_mode = "fuzzy"
            rows = fuzzy_rows
            offset = fuzzy_offset

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        if effective_sort == "newest":
            next_cursor = _encode_cursor(
                f"newest|{match_mode}|{last.created_at.isoformat()}|{last.id}"
            )
        elif effective_sort == "difficulty":
            diff_token = "null" if last.difficulty is None else str(int(last.difficulty))
            next_cursor = _encode_cursor(f"difficulty|{match_mode}|{diff_token}|{last.id}")
        else:
            next_cursor = _encode_cursor(f"{effective_sort}|{match_mode}|{offset + limit}")

    items = _hydrate_items(db, rows)

    if facets:
        facets_out = _compute_facets(db, filters, match_mode)
        total = facets_out.total
    else:
        facets_out = None
        total = int(
            db.scalar(
                select(func.count())
                .select_from(Question)
                .where(*_build_clauses(filters, match_mode))
            )
            or 0
        )

    return BankSearchOut(
        items=items,
        next_cursor=next_cursor,
        total=total,
        match_mode=match_mode,
        facets=facets_out,
    )


def autocomplete_tags(  # noqa: PLR0913 -- independent autocomplete filter parameters
    db: Session,
    org_id: UUID,
    role: Role,
    *,
    subject_id: UUID | None = None,
    q: str | None = None,
    limit: int = 50,
) -> list[TagCount]:
    clauses: list[ColumnElement[bool]] = [
        Question.org_id == org_id,
        Question.duplicate_of_id.is_(None),
    ]
    if role == Role.teacher:
        clauses.append(Question.status == "approved")
    if subject_id is not None:
        clauses.append(Question.subject_id == subject_id)

    tag_col = func.unnest(Question.tags).label("tag")
    cnt_col = func.count().label("cnt")
    stmt = (
        select(tag_col, cnt_col)
        .where(*clauses)
        .group_by(literal_column("tag"))
        .order_by(literal_column("cnt").desc(), literal_column("tag").asc())
    )
    if not q or not q.strip():
        return [TagCount(tag=str(r.tag), count=int(r.cnt)) for r in db.execute(stmt.limit(limit))]

    raw_q = q.strip().casefold()
    norm_q = normalize_ar(q)
    matched: list[TagCount] = []
    for r in db.execute(stmt):
        tag_str = str(r.tag)
        if raw_q in tag_str.casefold() or (norm_q and norm_q in normalize_ar(tag_str)):
            matched.append(TagCount(tag=tag_str, count=int(r.cnt)))
            if len(matched) >= limit:
                break
    return matched


def _approved_taxonomy_counts(
    db: Session, org_id: UUID, subject_id: UUID | None
) -> tuple[list[ChapterFacet], list[LessonFacet]]:
    approved_clauses: list[ColumnElement[bool]] = [
        Question.org_id == org_id,
        Question.duplicate_of_id.is_(None),
        Question.status == "approved",
    ]
    if subject_id is not None:
        approved_clauses.append(Question.subject_id == subject_id)

    chapter_counts: dict[UUID, int] = {}
    lesson_counts: dict[UUID, int] = {}
    tax_stmt = (
        select(
            func.grouping(Question.chapter_id, Question.lesson_id).label("grp"),
            Question.chapter_id,
            Question.lesson_id,
            func.count().label("cnt"),
        )
        .where(*approved_clauses)
        .group_by(
            func.grouping_sets(
                tuple_(Question.chapter_id),
                tuple_(Question.lesson_id),
            )
        )
    )
    for row in db.execute(tax_stmt):
        grp = int(row.grp)
        cnt = int(row.cnt)
        if grp == _TAX_GRP_CHAPTER and row.chapter_id is not None:
            chapter_counts[row.chapter_id] = cnt
        elif grp == _TAX_GRP_LESSON and row.lesson_id is not None:
            lesson_counts[row.lesson_id] = cnt

    chapters_stmt = scoped(select(Chapter), Chapter, org_id).order_by(
        Chapter.position.asc(), Chapter.id.asc()
    )
    if subject_id is not None:
        chapters_stmt = chapters_stmt.where(Chapter.subject_id == subject_id)
    chapters = db.scalars(chapters_stmt).all()
    approved_by_chapter = [
        ChapterFacet(id=c.id, title=c.title, count=chapter_counts.get(c.id, 0)) for c in chapters
    ]

    lessons_stmt = scoped(select(Lesson), Lesson, org_id).order_by(
        Lesson.position.asc(), Lesson.id.asc()
    )
    if subject_id is not None:
        lessons_stmt = lessons_stmt.where(Chapter.subject_id == subject_id)
    lessons = db.scalars(lessons_stmt).all()
    approved_by_lesson = [
        LessonFacet(
            id=les.id,
            chapter_id=les.chapter_id,
            title=les.title,
            count=lesson_counts.get(les.id, 0),
        )
        for les in lessons
    ]
    return approved_by_chapter, approved_by_lesson


def bank_stats(
    db: Session,
    org_id: UUID,
    role: Role,
    subject_id: UUID | None = None,
) -> BankStatsOut:
    clauses: list[ColumnElement[bool]] = [
        Question.org_id == org_id,
        Question.duplicate_of_id.is_(None),
    ]
    if role == Role.teacher:
        clauses.append(Question.status == "approved")
    if subject_id is not None:
        clauses.append(Question.subject_id == subject_id)

    total = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_difficulty: dict[int, int] = {}

    grp_stmt = (
        select(
            func.grouping(Question.status, Question.type, Question.difficulty).label("grp"),
            Question.status,
            Question.type,
            Question.difficulty,
            func.count().label("cnt"),
        )
        .where(*clauses)
        .group_by(
            func.grouping_sets(
                tuple_(),
                tuple_(Question.status),
                tuple_(Question.type),
                tuple_(Question.difficulty),
            )
        )
    )
    for row in db.execute(grp_stmt):
        grp = int(row.grp)
        cnt = int(row.cnt)
        if grp == _STATS_GRP_TOTAL:
            total = cnt
        elif grp == _STATS_GRP_STATUS and row.status is not None:
            by_status[row.status] = cnt
        elif grp == _STATS_GRP_TYPE and row.type is not None:
            by_type[row.type] = cnt
        elif grp == _STATS_GRP_DIFF and row.difficulty is not None:
            by_difficulty[int(row.difficulty)] = cnt

    approved_by_chapter, approved_by_lesson = _approved_taxonomy_counts(db, org_id, subject_id)

    return BankStatsOut(
        total=total,
        by_status=by_status,
        by_type=by_type,
        by_difficulty=by_difficulty,
        approved_by_chapter=approved_by_chapter,
        approved_by_lesson=approved_by_lesson,
    )


def move_questions(
    db: Session,
    org_id: UUID,
    data: QuestionsMove,
) -> QuestionsMoveOut:
    lesson = found(get(db, Lesson, org_id, data.lesson_id))
    chapter = found(get(db, Chapter, org_id, lesson.chapter_id))

    unique_ids = list(dict.fromkeys(data.ids))
    questions = list(
        db.scalars(scoped(select(Question), Question, org_id).where(Question.id.in_(unique_ids)))
    )
    if len(questions) != len(unique_ids):
        raise NotFound()
    if any(q.subject_id != chapter.subject_id for q in questions):
        raise Invalid("cross_subject_move")

    for q in questions:
        q.lesson_id = lesson.id
        q.chapter_id = chapter.id
        q.taxonomy_source = "human"
    save(db)
    return QuestionsMoveOut(moved=len(questions))
