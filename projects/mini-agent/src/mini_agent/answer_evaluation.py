import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnswerEvalCase:
    case_id: str
    category: str
    question: str
    document_source: str
    expected_answer_terms: tuple[tuple[str, ...], ...]
    expected_sources: frozenset[str]
    should_abstain: bool


@dataclass(frozen=True)
class AnswerEvalOutput:
    answer: str
    cited_sources: frozenset[str]
    abstained: bool


@dataclass(frozen=True)
class AnswerEvalReport:
    total_cases: int
    answerable_cases: int
    unanswerable_cases: int
    answer_correct_rate: float
    citation_correct_rate: float
    abstention_accuracy: float
    overall_success_rate: float
    failed_case_ids: tuple[str, ...]


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空")
    return value.strip()


def _normalize_text(value: str) -> str:
    return "".join(value.lower().split()).replace("％", "%")


def infer_abstention(answer: str) -> bool:
    normalized = _normalize_text(answer)
    markers = (
        "无法回答",
        "无法据此回答",
        "未提供",
        "未披露",
        "未检索到",
        "资料不足",
    )
    return any(marker in normalized for marker in markers)


def parse_sse_answer(
    response_text: str,
) -> AnswerEvalOutput:
    answer_parts: list[str] = []
    cited_sources: set[str] = set()

    for line in response_text.splitlines():
        if not line.startswith("data:"):
            continue

        raw_data = line.removeprefix("data:").strip()
        if not raw_data:
            continue

        event = json.loads(raw_data)
        event_type = event.get("type")

        if event_type == "content":
            content = event.get("content")
            if isinstance(content, str):
                answer_parts.append(content)
        elif event_type == "citation":
            source_name = event.get("source_name")
            if isinstance(source_name, str):
                cited_sources.add(source_name)
        elif event_type == "error":
            message = event.get("message", "未知错误")
            raise RuntimeError(f"RAG 请求失败: {message}")

    answer = "".join(answer_parts).strip()
    if not answer:
        raise ValueError("SSE 响应中没有答案内容")

    return AnswerEvalOutput(
        answer=answer,
        cited_sources=frozenset(cited_sources),
        abstained=infer_abstention(answer),
    )


def evaluate_answers(
    cases: list[AnswerEvalCase],
    outputs: dict[str, AnswerEvalOutput],
) -> AnswerEvalReport:
    if not cases:
        raise ValueError("评测用例不能为空")

    case_ids = {case.case_id for case in cases}
    missing_outputs = case_ids - outputs.keys()
    if missing_outputs:
        names = ", ".join(sorted(missing_outputs))
        raise ValueError(f"缺少评测输出: {names}")

    unknown_outputs = outputs.keys() - case_ids
    if unknown_outputs:
        names = ", ".join(sorted(unknown_outputs))
        raise ValueError(f"存在未知评测输出: {names}")

    answerable_cases = sum(
        not case.should_abstain for case in cases
    )
    unanswerable_cases = len(cases) - answerable_cases
    answer_correct_count = 0
    citation_correct_count = 0
    abstention_correct_count = 0
    overall_success_count = 0
    failed_case_ids: list[str] = []

    for case in cases:
        output = outputs[case.case_id]
        normalized_answer = _normalize_text(output.answer)
        abstention_correct = (
            output.abstained == case.should_abstain
        )

        if case.should_abstain:
            answer_correct = output.abstained
        else:
            answer_correct = (
                not output.abstained
                and all(
                    any(
                        _normalize_text(alias) in normalized_answer
                        for alias in aliases
                    )
                    for aliases in case.expected_answer_terms
                )
            )

        citation_correct = (
            output.cited_sources == case.expected_sources
        )
        overall_success = (
            answer_correct
            and citation_correct
            and abstention_correct
        )

        answer_correct_count += int(answer_correct)
        citation_correct_count += int(citation_correct)
        abstention_correct_count += int(abstention_correct)
        overall_success_count += int(overall_success)

        if not overall_success:
            failed_case_ids.append(case.case_id)

    total_cases = len(cases)
    return AnswerEvalReport(
        total_cases=total_cases,
        answerable_cases=answerable_cases,
        unanswerable_cases=unanswerable_cases,
        answer_correct_rate=answer_correct_count / total_cases,
        citation_correct_rate=citation_correct_count / total_cases,
        abstention_accuracy=(
            abstention_correct_count / total_cases
        ),
        overall_success_rate=(
            overall_success_count / total_cases
        ),
        failed_case_ids=tuple(failed_case_ids),
    )


def load_answer_eval_cases(path: Path) -> list[AnswerEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases 不能为空")

    cases: list[AnswerEvalCase] = []
    case_ids: set[str] = set()

    for item in raw_cases:
        case_id = _required_string(item.get("case_id"), "case_id")
        if case_id in case_ids:
            raise ValueError(f"重复的 case_id: {case_id}")
        case_ids.add(case_id)

        raw_terms = item.get("expected_answer_terms")
        raw_sources = item.get("expected_sources")
        should_abstain = item.get("should_abstain")

        if not isinstance(raw_terms, list):
            raise ValueError(
                "expected_answer_terms 必须是列表"
            )

        term_groups: list[tuple[str, ...]] = []
        for term in raw_terms:
            if isinstance(term, str) and term.strip():
                term_groups.append((term.strip(),))
                continue

            if (
                isinstance(term, list)
                and term
                and all(
                    isinstance(alias, str) and alias.strip()
                    for alias in term
                )
            ):
                term_groups.append(
                    tuple(alias.strip() for alias in term)
                )
                continue

            raise ValueError(
                "expected_answer_terms 中的每项必须是"
                "字符串或非空别名列表"
            )
        if not isinstance(raw_sources, list) or not all(
            isinstance(source, str) and source.strip()
            for source in raw_sources
        ):
            raise ValueError(
                "expected_sources 必须是非空字符串列表"
            )
        if not isinstance(should_abstain, bool):
            raise ValueError("should_abstain 必须是布尔值")
        if should_abstain and raw_terms:
            raise ValueError("拒答用例不应设置预期答案词")
        if should_abstain and raw_sources:
            raise ValueError("拒答用例不应设置预期引用")
        if not should_abstain and not raw_terms:
            raise ValueError("可回答用例必须设置预期答案词")
        if not should_abstain and not raw_sources:
            raise ValueError("可回答用例必须设置预期引用")

        cases.append(
            AnswerEvalCase(
                case_id=case_id,
                category=_required_string(
                    item.get("category"),
                    "category",
                ),
                question=_required_string(
                    item.get("question"),
                    "question",
                ),
                document_source=_required_string(
                    item.get("document_source"),
                    "document_source",
                ),
                expected_answer_terms=tuple(term_groups),
                expected_sources=frozenset(
                    source.strip() for source in raw_sources
                ),
                should_abstain=should_abstain,
            )
        )

    return cases


def load_answer_eval_outputs(
    path: Path,
) -> dict[str, AnswerEvalOutput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        raise ValueError("outputs 必须是列表")

    outputs: dict[str, AnswerEvalOutput] = {}
    for item in raw_outputs:
        case_id = _required_string(item.get("case_id"), "case_id")
        if case_id in outputs:
            raise ValueError(f"重复的输出 case_id: {case_id}")

        raw_sources = item.get("cited_sources")
        if not isinstance(raw_sources, list) or not all(
            isinstance(source, str) and source.strip()
            for source in raw_sources
        ):
            raise ValueError("cited_sources 必须是字符串列表")

        answer = _required_string(item.get("answer"), "answer")
        outputs[case_id] = AnswerEvalOutput(
            answer=answer,
            cited_sources=frozenset(
                source.strip() for source in raw_sources
            ),
            abstained=infer_abstention(answer),
        )

    return outputs
