import re
from typing import Literal

from pydantic import BaseModel

from mini_agent.fund_evidence import missing_fee_terms
from mini_agent.knowledge import KnowledgeChunk


QuestionType = Literal[
    "fee",
    "objective",
    "scope",
    "strategy",
    "risk",
    "manager",
    "performance",
    "rating",
    "contact",
    "environmental",
    "unknown",
]


class EvidenceSufficiencyResult(BaseModel):
    sufficient: bool
    question_type: QuestionType
    reason_code: str
    reason: str
    matched_chunk_indices: list[int]
    required_evidence_fields: list[str]


INTENT_RULES: tuple[
    tuple[QuestionType, tuple[str, ...], tuple[str, ...]],
    ...,
] = (
    ("objective", ("投资目标", "目标是什么"), ("投资目标",)),
    ("strategy", ("投资策略", "采用什么策略"), ("投资策略",)),
    (
        "scope",
        (
            "投资范围",
            "投资哪些",
            "是否投资",
            "可以投资",
            "投资比例",
            "最低比例",
            "标的指数",
            "跟踪什么",
        ),
        ("投资范围", "投资于", "不投资于", "标的指数"),
    ),
    (
        "scope",
        ("剩余期限", "期限不超过"),
        ("剩余期限",),
    ),
    (
        "risk",
        (
            "风险水平",
            "风险等级",
            "风险收益水平",
            "风险收益特征",
            "哪些风险",
            "主要风险",
            "什么风险",
            "面临风险",
        ),
        ("风险收益特征", "主要风险", "风险揭示", "低风险", "中风险", "高风险"),
    ),
    (
        "strategy",
        ("如何挑选", "复制策略", "跟踪误差"),
        ("主要投资策略", "选股策略", "复制法", "跟踪误差"),
    ),
    ("manager", ("基金经理",), ("基金经理",)),
    ("performance", ("收益率", "净值增长率"), ("收益率", "净值增长率")),
)


def _result(
    *,
    sufficient: bool,
    question_type: QuestionType,
    reason_code: str,
    reason: str,
    chunks: list[KnowledgeChunk],
    required_evidence_fields: tuple[str, ...] = (),
) -> EvidenceSufficiencyResult:
    return EvidenceSufficiencyResult(
        sufficient=sufficient,
        question_type=question_type,
        reason_code=reason_code,
        reason=reason,
        matched_chunk_indices=[chunk.chunk_index for chunk in chunks],
        required_evidence_fields=list(required_evidence_fields),
    )


def assess_evidence_sufficiency(
    question: str,
    evidence: list[KnowledgeChunk],
) -> EvidenceSufficiencyResult:
    """用可审计规则判断已召回证据是否包含回答所需事实。"""
    if not evidence:
        return _result(
            sufficient=False,
            question_type="unknown",
            reason_code="no_evidence",
            reason="没有召回证据",
            chunks=[],
        )

    evidence_text = "\n".join(chunk.content for chunk in evidence)

    requested_years = set(re.findall(r"(?:19|20)\d{2}", question))
    missing_years = sorted(
        year for year in requested_years if year not in evidence_text
    )
    if missing_years:
        return _result(
            sufficient=False,
            question_type="performance" if "收益" in question else "unknown",
            reason_code="missing_time_constraint",
            reason="证据未包含问题指定年份：" + "、".join(missing_years),
            chunks=evidence,
            required_evidence_fields=tuple(missing_years),
        )

    if "晨星" in question or "评级" in question:
        if "晨星" not in evidence_text:
            return _result(
                sufficient=False,
                question_type="rating",
                reason_code="missing_rating_evidence",
                reason="证据未提供所问评级",
                chunks=evidence,
                required_evidence_fields=("晨星评级",),
            )

    if "碳排放" in question or "碳足迹" in question:
        if "碳排放" not in evidence_text and "碳足迹" not in evidence_text:
            return _result(
                sufficient=False,
                question_type="environmental",
                reason_code="missing_environmental_evidence",
                reason="证据未提供环境指标",
                chunks=evidence,
                required_evidence_fields=("碳排放或碳足迹",),
            )

    contact_terms = ("电话", "联系方式", "手机", "微信", "邮箱", "社交账号")
    if any(term in question for term in contact_terms):
        if any(term in question for term in ("私人", "个人微信", "个人手机号", "私人邮箱")):
            return _result(
                sufficient=False,
                question_type="contact",
                reason_code="private_contact_not_disclosed",
                reason="公开资料不提供个人联系方式",
                chunks=evidence,
                required_evidence_fields=("公开联系方式",),
            )
        if not any(term in evidence_text for term in ("联系电话", "客服电话", "联系方式")):
            return _result(
                sufficient=False,
                question_type="contact",
                reason_code="missing_contact_evidence",
                reason="证据未提供所问联系方式",
                chunks=evidence,
                required_evidence_fields=("公开联系方式",),
            )

    requested_fees = missing_fee_terms(question, evidence)
    if any(term in question for term in ("管理费", "托管费", "申购费", "赎回费")):
        if requested_fees:
            return _result(
                sufficient=False,
                question_type="fee",
                reason_code="missing_explicit_fee",
                reason="证据未提供明确费率：" + "、".join(requested_fees),
                chunks=evidence,
                required_evidence_fields=tuple(requested_fees),
            )
        return _result(
            sufficient=True,
            question_type="fee",
            reason_code="explicit_fee_found",
            reason="证据包含问题要求的明确费用信息",
            chunks=evidence,
            required_evidence_fields=tuple(
                term for term in ("管理费", "托管费", "申购费", "赎回费")
                if term in question
            ),
        )

    for question_type, question_terms, evidence_terms in INTENT_RULES:
        if not any(term in question for term in question_terms):
            continue
        if any(term in evidence_text for term in evidence_terms):
            return _result(
                sufficient=True,
                question_type=question_type,
                reason_code="intent_evidence_found",
                reason="证据包含该问题类型所需的事实字段",
                chunks=evidence,
                required_evidence_fields=evidence_terms,
            )
        return _result(
            sufficient=False,
            question_type=question_type,
            reason_code="missing_intent_evidence",
            reason="证据未包含该问题类型所需的事实字段",
            chunks=evidence,
            required_evidence_fields=evidence_terms,
        )

    return _result(
        sufficient=False,
        question_type="unknown",
        reason_code="unsupported_question_type",
        reason="无法用可审计规则确认现有证据足以回答",
        chunks=evidence,
    )
