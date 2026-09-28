import json
from pathlib import Path

import pytest

from recall.extract import SLICE_CAP, extract_all, extract_session
from recall.records import ExplicitRecall, Mutation, read_turns, write_jsonl

FIXTURES = Path(__file__).parent / "fixtures" / "recall"
SESSION = "0f0f0f0f-1111-4222-8333-444444444444"
TRANSCRIPT = FIXTURES / "-Users-example-dev" / f"{SESSION}.jsonl"


@pytest.fixture(scope="module")
def turns():
    return extract_session(TRANSCRIPT)


def test_one_turn_per_prompt_including_slash_and_queued_commands(turns):
    assert [t.prompt for t in turns] == [
        "How should the widget cache expire entries?",
        "<command-message>demo is running…</command-message>\n<command-name>/demo</command-name>",
        "<command-name>/model</command-name>\n<command-message>model</command-message>\n<command-args></command-args>",
        "List the files.",
        "Also count them.",
    ]


def test_turn_identity_comes_from_prompt_record_and_path(turns):
    first = turns[0]
    assert first.session == SESSION
    assert first.project == "-Users-example-dev"
    assert first.prompt_uuid == "00000000-0000-4000-8000-000000000002"
    assert first.ts == "2026-09-01T10:02:00.000Z"


def test_hook_attaches_to_prompt_through_intervening_attachments(turns):
    assert [r.id for r in turns[0].recalls] == [101, 102, 103]
    first = turns[0].recalls[0]
    assert (first.scope, first.scorer, first.score, first.text) == (
        "global/patterns",
        "fts5",
        -9.209,
        "Keep cache eviction in one place.",
    )


def test_expires_suffix_is_not_memory_text(turns):
    assert turns[0].recalls[1].text.startswith("Widget cache layout:")
    assert turns[0].recalls[1].score == -4.5


def test_heading_inside_memory_text_stays_with_that_memory(turns):
    assert "## Section heading inside memory\n- key: value" in turns[0].recalls[1].text
    assert turns[0].recalls[2].text == "Check the clock source before blaming the cache."


def test_hook_after_slash_command_skill_body_belongs_to_command_turn(turns):
    assert [r.id for r in turns[1].recalls] == [301, 302]


def test_hook_without_memory_lines_yields_no_recalls(tmp_path):
    lines = TRANSCRIPT.read_text().splitlines()
    kept = [line for line in lines if "persisted-output" not in line]
    path = tmp_path / "-Users-example-dev" / f"{SESSION}.jsonl"
    path.parent.mkdir()
    path.write_text("\n".join(kept) + "\n")
    assert extract_session(path)[1].recalls == []


def test_persisted_output_parses_only_the_preview_the_model_saw(turns):
    assert turns[1].recalls[1].text == "The demo tool writes a lo"


def test_queued_human_prompt_starts_its_own_turn_with_its_hook(turns):
    assert turns[3].recalls == []
    assert turns[4].prompt_uuid == "00000000-0000-4000-8000-000000000032"
    assert [r.id for r in turns[4].recalls] == [401]


def test_local_output_interrupts_meta_queue_and_compaction_start_no_turn(turns):
    assert "<local-command-stdout>Set model to opus</local-command-stdout>" not in [t.prompt for t in turns]
    assert "RESULT: a.txt\nb.txt" in turns[3].slice
    assert "ASSISTANT: Continuing after compaction." in turns[4].slice
    assert "ASSISTANT: Two files." in turns[4].slice


def test_explicit_recall_ids_come_from_result_header_lines(turns):
    assert turns[0].explicit_recalls == [ExplicitRecall(query="widget cache", ids=[201, 202])]


def test_mutations_cover_update_merge_and_superseded_target(turns):
    assert turns[0].mutations == [
        Mutation(tool="mcp__memory__update", id=101),
        Mutation(tool="mcp__memory__connect", id=103),
        Mutation(tool="mcp__memory__merge", id=107),
        Mutation(tool="mcp__memory__merge", id=108),
    ]


def test_sidechain_records_are_skipped(turns):
    assert all("SIDECHAIN" not in t.slice for t in turns)


def test_slice_holds_prompt_text_tools_and_results(turns):
    slice_lines = turns[0].slice.splitlines()
    assert slice_lines[0] == "USER: How should the widget cache expire entries?"
    assert 'TOOL mcp__memory__recall: {"query": "widget cache", "limit": 5}' in slice_lines
    assert "ASSISTANT: Use a TTL on each entry." in slice_lines
    assert "RESULT: Updated memory 101" in slice_lines


def test_authored_holds_only_what_claude_wrote(turns):
    authored = turns[0].authored.splitlines()
    assert authored[0] == "ASSISTANT: Checking what is already known."
    assert 'TOOL mcp__memory__recall: {"query": "widget cache", "limit": 5}' in authored
    assert "ASSISTANT: Use a TTL on each entry." in authored


def test_authored_excludes_tool_results_and_prompt(turns):
    assert "Widget cache uses LRU" in turns[0].slice
    assert "Widget cache uses LRU" not in turns[0].authored
    assert "[id:201]" not in turns[0].authored
    assert "RESULT:" not in turns[0].authored
    assert "USER:" not in turns[0].authored
    assert turns[3].authored == 'TOOL Bash: {"command": "ls"}'


def test_slice_is_cut_to_cap(tmp_path):
    record = json.loads(TRANSCRIPT.read_text().splitlines()[1])
    record["message"]["content"] = "x" * (SLICE_CAP + 500)
    path = tmp_path / "p" / "s.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(record) + "\n")
    assert len(extract_session(path)[0].slice) == SLICE_CAP


def test_malformed_line_raises_with_file_and_line(tmp_path):
    path = tmp_path / "p" / "s.jsonl"
    path.parent.mkdir()
    path.write_text(TRANSCRIPT.read_text().splitlines()[0] + "\n{not json\n")
    with pytest.raises(ValueError, match=rf"{path}:2: malformed transcript line"):
        extract_session(path)


def test_extract_all_reads_every_project_transcript():
    assert [t.prompt_uuid for t in extract_all(FIXTURES)] == [t.prompt_uuid for t in extract_session(TRANSCRIPT)]


def test_turns_round_trip_through_the_shared_contract(turns, tmp_path):
    path = tmp_path / "turns.jsonl"
    write_jsonl(path, turns)
    assert read_turns(path) == turns
