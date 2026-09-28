from recall.mechanical import classify, distinctive_tokens
from recall.records import ExplicitRecall, Mutation, Recall, RecallKind, RecallVerdict, Turn

JUDGED_AT = "2026-09-29T08:00:12Z"


def make_turn(prompt="how would this work?", authored="", tool_output="", recalls=(), explicit=(), mutations=()):
    return Turn(
        session="s1",
        prompt_uuid="p1",
        ts="2026-09-28T17:53:36Z",
        project="-Users-tslater-dev",
        prompt=prompt,
        recalls=list(recalls),
        explicit_recalls=list(explicit),
        mutations=list(mutations),
        slice="\n".join([prompt, authored, tool_output]),
        authored=authored,
    )


def make_recall(memory_id, text, score=-9.2):
    return Recall(id=memory_id, scope="dev/patterns", scorer="fts5", score=score, text=text)


def test_common_words_are_not_distinctive():
    text = "Always check the status carefully before committing because problems happen"
    assert distinctive_tokens(text) == set()


def test_distinctive_tokens_cover_paths_flags_identifiers_and_commands():
    text = (
        "Run `advise-quiet` from ~/.claude/bin with --no-verify; the statusLine key "
        "lives in settings.json and remaining_percentage is inverted. See recall/records.py."
    )
    assert distinctive_tokens(text) == {
        "advise-quiet",
        "~/.claude/bin",
        "--no-verify",
        "statusLine",
        "settings.json",
        "remaining_percentage",
        "recall/records.py",
    }


def test_short_tokens_and_version_numbers_are_not_distinctive():
    assert distinctive_tokens("Use e.g. and/or with v3.13.0 or a_b") == set()


def test_shared_common_words_leave_recall_undecided():
    recall = make_recall(6523, "Always check the status of the build before you commit changes")
    turn = make_turn(authored="I will check the status of the build and then commit the changes.", recalls=[recall])

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == [6523]


def test_token_echoed_from_prompt_is_not_a_citation():
    recall = make_recall(6523, "Delete the statusLine key from settings.json rather than nulling it")
    turn = make_turn(
        prompt="why is settings.json not loading?",
        authored="Reading settings.json now. It parses fine.",
        recalls=[recall],
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == [6523]


def test_supersede_beats_cite():
    recall = make_recall(6523, "Use `shot-scraper` for screenshots")
    turn = make_turn(
        authored="Running shot-scraper, then updating memory id:6523.",
        recalls=[recall],
        mutations=[Mutation(tool="mcp__memory__update", id=6523)],
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert [(v.memory_id, v.verdict, v.evidence) for v in verdicts] == [
        (6523, RecallVerdict.SUPERSEDED, "mcp__memory__update")
    ]
    assert undecided == []


def test_realistic_citation_by_distinctive_token():
    recalls = [
        make_recall(
            6101,
            "To disable statusline: delete the statusLine key from settings.json; "
            "setting it to null causes a validation error that skips the entire file",
            score=-11.4,
        ),
        make_recall(6523, "cmux hex colors must be six digits", score=-4.1),
    ]
    turn = make_turn(
        prompt="turn off the status bar at the bottom",
        authored=("Edit ~/.claude/settings.json: removing the statusLine key entirely, since null fails validation."),
        recalls=recalls,
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert len(verdicts) == 1
    verdict = verdicts[0]
    assert verdict.memory_id == 6101
    assert verdict.verdict == RecallVerdict.CITED
    assert verdict.evidence == "settings.json"
    assert verdict.recall_kind == RecallKind.AUTOMATIC
    assert verdict.score == -11.4
    assert verdict.confidence == 1.0
    assert verdict.judge_model == "mechanical"
    assert verdict.judged_at == JUDGED_AT
    assert undecided == [6523]


def test_id_reference_is_a_citation():
    recall = make_recall(6523, "Prefer small commits")
    turn = make_turn(authored="Per [id:6523] I split this into two commits.", recalls=[recall])

    verdicts, _ = classify(turn, JUDGED_AT)

    assert [(v.verdict, v.evidence) for v in verdicts] == [(RecallVerdict.CITED, "id:6523")]


def test_id_reference_needs_exact_number():
    recall = make_recall(652, "Prefer small commits")
    turn = make_turn(authored="See id:6523 and #65234.", recalls=[recall])

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == [652]


def test_token_inside_longer_identifier_is_not_a_citation():
    recall = make_recall(6523, "Keep state in state.json")
    turn = make_turn(authored="Wrote indexer-state.json and state.jsonl.", recalls=[recall])

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == [6523]


def test_repeated_automatic_recall_yields_one_verdict():
    recall = make_recall(6523, "Prefer small commits")
    turn = make_turn(authored="Following #6523.", recalls=[recall, recall])

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert len(verdicts) == 1
    assert undecided == []


def test_repeated_undecided_recall_is_returned_once():
    recall = make_recall(6523, "Prefer small commits")
    turn = make_turn(recalls=[recall, recall])

    _, undecided = classify(turn, JUDGED_AT)

    assert undecided == [6523]


def test_explicit_recalls_get_mechanical_verdicts_only():
    turn = make_turn(
        authored="Recalled memories, then applied #6121.",
        explicit=[ExplicitRecall(query="commit style", ids=[6121, 6931, 7000])],
        mutations=[Mutation(tool="mcp__memory__forget", id=7000)],
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert [(v.memory_id, v.verdict, v.recall_kind, v.score) for v in verdicts] == [
        (6121, RecallVerdict.CITED, RecallKind.EXPLICIT, None),
        (7000, RecallVerdict.SUPERSEDED, RecallKind.EXPLICIT, None),
    ]
    assert undecided == []


def test_explicit_recall_of_automatic_id_adds_no_second_verdict():
    recall = make_recall(6523, "Prefer small commits")
    turn = make_turn(
        authored="Following #6523.",
        recalls=[recall],
        explicit=[ExplicitRecall(query="commits", ids=[6523])],
    )

    verdicts, _ = classify(turn, JUDGED_AT)

    assert [(v.memory_id, v.recall_kind) for v in verdicts] == [(6523, RecallKind.AUTOMATIC)]


def test_slash_joined_prose_is_not_a_path():
    assert distinctive_tokens("Agents claim/submit/check tasks across Data/Control/Action layers") == set()


def test_single_hump_product_names_are_not_distinctive():
    assert distinctive_tokens("Push to GitHub and publish the OpenAPI spec for SpecTrace") == set()


def test_multi_hump_and_lower_camel_case_stay_distinctive():
    assert distinctive_tokens("Call getFleetCost or ReadyForReview") == {"getFleetCost", "ReadyForReview"}


def test_workbench_root_is_not_a_distinctive_path():
    assert distinctive_tokens("Keep active projects in ~/dev/ and nothing else") == set()


def test_nested_and_rooted_paths_stay_distinctive():
    assert distinctive_tokens("Clone into ~/dev/get-shit-done and use /forge or /dev/null") == {
        "~/dev/get-shit-done",
        "/forge",
        "/dev/null",
    }


def test_token_only_in_tool_output_is_not_a_citation():
    recall = make_recall(6101, "Delete the statusLine key from settings.json rather than nulling it")
    turn = make_turn(
        authored="Read(file_path=/tmp/notes.txt)",
        tool_output="notes: remember to back up ~/.claude/settings.json",
        recalls=[recall],
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == [6101]


def test_explicit_recall_echoed_only_in_tool_output_gets_no_verdict():
    turn = make_turn(
        authored='mcp__memory__recall(query="statusline")',
        tool_output="[id:6101] [global] Delete the statusLine key from settings.json rather than nulling it",
        explicit=[ExplicitRecall(query="statusline", ids=[6101])],
    )

    verdicts, undecided = classify(turn, JUDGED_AT)

    assert verdicts == []
    assert undecided == []
