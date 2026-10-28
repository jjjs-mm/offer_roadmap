import json
from pathlib import Path

import pytest

from mini_agent.answer_evaluation import (
    AnswerEvalCase,
    AnswerEvalOutput,
    evaluate_answers,
    infer_abstention,
    load_answer_eval_cases,
    parse_sse_answer,
)


def answerable_case() -> AnswerEvalCase:
    return AnswerEvalCase(
        case_id="fee-1",
        category="fact",
        question="这只基金的管理费是多少？",
        document_source="fees.md",
        expected_answer_terms=(("管理费",), ("0.50%",)),
        expected_sources=frozenset({"fees.md"}),
        should_abstain=False,
    )


def test_evaluates_correct_answer_and_citation() -> None:
    outputs = {
        "fee-1": AnswerEvalOutput(
            answer="该基金的管理费为每年 0.50%。",
            cited_sources=frozenset({"fees.md"}),
            abstained=False,
        )
    }

    report = evaluate_answers([answerable_case()], outputs)

    assert report.answer_correct_rate == 1.0
    assert report.citation_correct_rate == 1.0
    assert report.abstention_accuracy == 1.0
    assert report.overall_success_rate == 1.0
    assert report.failed_case_ids == ()


def test_marks_missing_fact_as_failure() -> None:
    outputs = {
        "fee-1": AnswerEvalOutput(
            answer="该基金收取管理费。",
            cited_sources=frozenset({"fees.md"}),
            abstained=False,
        )
    }

    report = evaluate_answers([answerable_case()], outputs)

    assert report.answer_correct_rate == 0.0
    assert report.citation_correct_rate == 1.0
    assert report.overall_success_rate == 0.0
    assert report.failed_case_ids == ("fee-1",)


def test_evaluates_correct_abstention() -> None:
    case = AnswerEvalCase(
        case_id="unknown-1",
        category="unanswerable",
        question="基金经理是谁？",
        document_source="fees.md",
        expected_answer_terms=(),
        expected_sources=frozenset(),
        should_abstain=True,
    )
    outputs = {
        "unknown-1": AnswerEvalOutput(
            answer="所选资料未提供基金经理信息，无法回答。",
            cited_sources=frozenset(),
            abstained=True,
        )
    }

    report = evaluate_answers([case], outputs)

    assert report.answer_correct_rate == 1.0
    assert report.citation_correct_rate == 1.0
    assert report.abstention_accuracy == 1.0
    assert report.overall_success_rate == 1.0


def test_requires_every_case_to_have_output() -> None:
    with pytest.raises(ValueError, match="fee-1"):
        evaluate_answers([answerable_case()], {})


@pytest.mark.parametrize(
    "answer",
    [
        "所选资料未提供该信息，无法回答。",
        "资料不足，无法据此回答。",
        "未检索到与问题相关的内容。",
    ],
)
def test_infers_abstention(answer: str) -> None:
    assert infer_abstention(answer) is True


def test_loads_and_validates_dataset(tmp_path) -> None:
    dataset_path = tmp_path / "answers.json"
    dataset_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "fee-1",
                        "category": "fact",
                        "question": "管理费是多少？",
                        "document_source": "fees.md",
                        "expected_answer_terms": ["0.50%"],
                        "expected_sources": ["fees.md"],
                        "should_abstain": False,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = load_answer_eval_cases(dataset_path)

    assert cases[0].case_id == "fee-1"
    assert cases[0].expected_answer_terms == (("0.50%",),)


def test_rejects_expected_terms_on_abstention_case(tmp_path) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "unknown-1",
                        "category": "unanswerable",
                        "question": "基金经理是谁？",
                        "document_source": "fees.md",
                        "expected_answer_terms": ["张三"],
                        "expected_sources": [],
                        "should_abstain": True,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="拒答用例"):
        load_answer_eval_cases(dataset_path)


def test_accepts_any_alias_for_the_same_fact() -> None:
    case = AnswerEvalCase(
        case_id="custody-fee-1",
        category="paraphrase",
        question="托管服务怎么收费？",
        document_source="fees.md",
        expected_answer_terms=(
            ("托管费", "托管服务费"),
            ("0.10%",),
        ),
        expected_sources=frozenset({"fees.md"}),
        should_abstain=False,
    )
    outputs = {
        "custody-fee-1": AnswerEvalOutput(
            answer="托管服务费为每年 0.10%。",
            cited_sources=frozenset({"fees.md"}),
            abstained=False,
        )
    }

    report = evaluate_answers([case], outputs)

    assert report.overall_success_rate == 1.0


def test_parses_streamed_answer_and_citations() -> None:
    response_text = "\n".join(
        [
            "event: content",
            'data: {"type":"content","content":"管理费为"}',
            "",
            "event: content",
            'data: {"type":"content","content":"0.50%。"}',
            "",
            "event: citation",
            (
                'data: {"type":"citation",'
                '"source_name":"fund.md",'
                '"chunk_index":0}'
            ),
            "",
            "event: done",
            'data: {"type":"done"}',
        ]
    )

    output = parse_sse_answer(response_text)

    assert output.answer == "管理费为0.50%。"
    assert output.cited_sources == frozenset({"fund.md"})
    assert output.abstained is False


def test_raises_for_sse_error_event() -> None:
    with pytest.raises(RuntimeError, match="模型失败"):
        parse_sse_answer(
            'data: {"type":"error","message":"模型失败"}'
        )


def test_checked_in_answer_dataset_has_balanced_cases() -> None:
    dataset_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "answer_eval_dataset.json"
    )

    cases = load_answer_eval_cases(dataset_path)

    assert len(cases) == 12
    assert sum(not case.should_abstain for case in cases) == 8
    assert sum(case.should_abstain for case in cases) == 4
    assert len({case.case_id for case in cases}) == 12
