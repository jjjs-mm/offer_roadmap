import pytest

from mini_agent.evidence_sufficiency import assess_evidence_sufficiency
from mini_agent.knowledge import KnowledgeChunk


def chunk(content: str, index: int = 0) -> KnowledgeChunk:
    return KnowledgeChunk(
        document_id="doc",
        source_name="official.pdf",
        chunk_index=index,
        page_number=1,
        content=content,
    )


@pytest.mark.parametrize(
    ("question", "content", "question_type"),
    [
        ("投资目标是什么？", "投资目标：跟踪沪深300指数。", "objective"),
        ("是否投资股票？", "投资范围：本基金不投资于股票。", "scope"),
        ("主要面临哪些风险？", "风险揭示：包括市场风险和信用风险。", "risk"),
        ("它有哪些主要风险？", "风险揭示：包括市场风险和信用风险。", "risk"),
        ("管理费是多少？", "管理费年费率0.30%。", "fee"),
    ],
)
def test_accepts_explicit_evidence(question, content, question_type) -> None:
    result = assess_evidence_sufficiency(question, [chunk(content)])

    assert result.sufficient is True
    assert result.question_type == question_type


def test_rejects_requested_year_missing_from_evidence() -> None:
    result = assess_evidence_sufficiency(
        "2027年的收益率是多少？",
        [chunk("2025年净值增长率为1.20%。")],
    )

    assert result.sufficient is False
    assert result.reason_code == "missing_time_constraint"
    assert result.required_evidence_fields == ["2027"]


@pytest.mark.parametrize(
    ("question", "content", "reason_code"),
    [
        ("晨星评级是多少？", "风险评级可能不一致。", "missing_rating_evidence"),
        ("投资组合的碳排放量是多少？", "投资组合包括债券。", "missing_environmental_evidence"),
        ("基金经理的私人联系电话是多少？", "基金经理为张三。", "private_contact_not_disclosed"),
    ],
)
def test_rejects_related_but_insufficient_evidence(
    question,
    content,
    reason_code,
) -> None:
    result = assess_evidence_sufficiency(question, [chunk(content)])

    assert result.sufficient is False
    assert result.reason_code == reason_code


def test_accepts_explicit_no_fee_statement() -> None:
    result = assess_evidence_sufficiency(
        "是否收取申购费和赎回费？",
        [chunk("本基金不收取申购费用和赎回费用。")],
    )

    assert result.sufficient is True


def test_rejects_private_social_contact_even_when_public_contact_exists() -> None:
    result = assess_evidence_sufficiency(
        "能提供基金经理的个人微信吗？",
        [chunk("客服电话：400-000-0000；基金经理为张三。")],
    )

    assert result.sufficient is False
    assert result.question_type == "contact"
    assert result.reason_code == "private_contact_not_disclosed"
    assert result.required_evidence_fields == ["公开联系方式"]


@pytest.mark.parametrize(
    ("question", "content", "question_type"),
    [
        (
            "股票资产的投资比例是多少？",
            "投资范围：股票资产投资比例为基金资产的60%-95%。",
            "scope",
        ),
        (
            "风险收益水平如何？",
            "风险收益特征：本基金属于中风险产品。",
            "risk",
        ),
        (
            "这只基金如何挑选股票？",
            "主要投资策略：采用自下而上的选股策略。",
            "strategy",
        ),
        (
            "预期年化跟踪误差控制在多少以内？",
            "主要投资策略：预期年化跟踪误差不超过4%。",
            "strategy",
        ),
    ],
)
def test_accepts_real_pdf_question_variants(
    question: str,
    content: str,
    question_type: str,
) -> None:
    result = assess_evidence_sufficiency(
        question,
        [chunk(content)],
    )

    assert result.sufficient is True
    assert result.question_type == question_type
