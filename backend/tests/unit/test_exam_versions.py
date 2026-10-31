import random
from typing import Any, cast
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from qbank.exams.versions import (
    ChoiceSpec,
    ItemSpec,
    KeyQuestion,
    answer_key_entry,
    build_layout,
    display_label,
    permute_choices,
    version_label,
)


def section_items(layout: dict[str, object]) -> list[list[dict[str, Any]]]:
    sections = cast(list[dict[str, Any]], layout["sections"])
    return [s["items"] for s in sections]


@st.composite
def exams(draw: st.DrawFn) -> list[tuple[UUID, list[ItemSpec]]]:
    stimuli = [uuid4() for _ in range(3)]
    sections = []
    for _ in range(draw(st.integers(1, 3))):
        items: list[ItemSpec] = []
        for _ in range(draw(st.integers(0, 6))):
            stimulus = draw(st.sampled_from([None, *stimuli]))
            if stimulus is not None and any(i.stimulus_id == stimulus for i in items):
                # keep groups contiguous in the source, as the API guarantees
                stimulus = items[-1].stimulus_id
            n = draw(st.integers(0, 6))
            items.append(
                ItemSpec(
                    item_id=uuid4(),
                    question_id=uuid4(),
                    type=draw(st.sampled_from(["mcq_single", "mcq_multi", "essay"])),
                    points=1,
                    stimulus_id=stimulus,
                    choices=[ChoiceSpec(pinned=draw(st.booleans())) for _ in range(n)],
                )
            )
        sections.append((uuid4(), items))
    return sections


@settings(max_examples=100, deadline=None)
@given(sections=exams(), seed=st.integers(0, 10_000))
def test_layout_properties(sections: list[tuple[UUID, list[ItemSpec]]], seed: int) -> None:
    layout = build_layout(sections, seed=seed)
    assert layout == build_layout(sections, seed=seed)
    number = 0
    outs = cast(list[dict[str, Any]], layout["sections"])
    for (section_id, items), out in zip(sections, outs, strict=True):
        assert out["section_id"] == str(section_id)
        out_items = out["items"]
        assert sorted(i["item_id"] for i in out_items) == sorted(str(i.item_id) for i in items)
        by_id = {str(i.item_id): i for i in items}
        runs: list[UUID | None] = []
        for entry in out_items:
            number += 1
            assert entry["number"] == number
            spec = by_id[entry["item_id"]]
            if spec.stimulus_id is not None and (not runs or runs[-1] != spec.stimulus_id):
                assert spec.stimulus_id not in runs  # group is contiguous
            runs.append(spec.stimulus_id)
            order = entry["choice_order"]
            if order is None:
                assert spec.type == "essay" or not spec.choices
                continue
            assert sorted(order) == list(range(len(spec.choices)))
            for position, source in enumerate(order):
                if spec.choices[position].pinned:
                    assert source == position
        for sid in {i.stimulus_id for i in items} - {None}:  # internal order is preserved
            source_order = [str(i.item_id) for i in items if i.stimulus_id == sid]
            out_order = [e["item_id"] for e in out_items if by_id[e["item_id"]].stimulus_id == sid]
            assert out_order == source_order


def test_no_shuffle_keeps_original_and_labels() -> None:
    items = [
        ItemSpec(uuid4(), uuid4(), "mcq_single", 2, None, [ChoiceSpec(), ChoiceSpec()])
        for _ in range(3)
    ]
    layout = build_layout(
        [(uuid4(), items)], seed=5, shuffle_questions=False, shuffle_choices=False
    )
    (out_items,) = section_items(layout)
    assert [i["item_id"] for i in out_items] == [str(i.item_id) for i in items]
    assert all(i["choice_order"] == [0, 1] for i in out_items)
    assert version_label("ar", 0) == "أ"
    assert version_label("en", 2) == "C"
    assert display_label("ar", 4) == "هـ"
    assert display_label("en", 30) == "31"


def test_permute_pinned_fixed() -> None:
    choices = [ChoiceSpec(), ChoiceSpec(pinned=True), ChoiceSpec(), ChoiceSpec(pinned=True)]
    for seed in range(20):
        order = permute_choices(choices, random.Random(seed))  # noqa: S311 -- test shuffling
        assert order[1] == 1
        assert order[3] == 3  # noqa: PLR2004 -- the second pinned slot
        assert sorted(order) == [0, 1, 2, 3]


@given(seed=st.integers(0, 1000))
def test_answer_key_maps_back_to_original(seed: int) -> None:
    choices = [ChoiceSpec(), ChoiceSpec(pinned=True), ChoiceSpec(), ChoiceSpec()]
    item = ItemSpec(uuid4(), uuid4(), "mcq_single", 1, None, choices)
    layout = build_layout([(uuid4(), [item])], seed=seed)
    entry_layout = section_items(layout)[0][0]
    flags = [False, False, True, False]
    entry, warning = answer_key_entry(entry_layout, KeyQuestion("mcq_single", flags, None), "en")
    assert warning is None
    correct = cast(list[str], entry["correct"])
    assert len(correct) == 1
    position = "ABCD".index(correct[0])
    assert entry_layout["choice_order"][position] == 2  # noqa: PLR2004 -- the correct source index


def test_answer_key_unknown_and_text() -> None:
    points = 3
    item = ItemSpec(uuid4(), uuid4(), "mcq_single", 1, None, [ChoiceSpec(), ChoiceSpec()])
    mcq = section_items(build_layout([(uuid4(), [item])], seed=1))[0][0]
    entry, warning = answer_key_entry(mcq, KeyQuestion("mcq_single", [None, None], "x"), "ar")
    assert entry["correct"] is None
    assert warning is not None
    assert entry["answer_text"] == "x"
    essay = ItemSpec(uuid4(), uuid4(), "essay", points, None, [])
    layout_item = section_items(build_layout([(uuid4(), [essay])], seed=1))[0][0]
    entry, warning = answer_key_entry(layout_item, KeyQuestion("essay", [], "model answer"), "en")
    assert warning is None
    assert entry["correct"] is None
    assert entry["points"] == points
