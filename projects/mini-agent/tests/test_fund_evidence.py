from mini_agent.fund_evidence import missing_fee_terms
from mini_agent.knowledge import KnowledgeChunk


CHUNKS = [
    KnowledgeChunk(
        document_id="fees",
        source_name="fees.md",
        chunk_index=0,
        content="管理费每年0.50%，托管费每年0.10%。",
    )
]


def test_reports_requested_fee_missing_from_evidence() -> None:
    assert missing_fee_terms("赎回费是多少？", CHUNKS) == ["赎回费"]


def test_accepts_fee_terms_present_in_evidence() -> None:
    assert missing_fee_terms(
        "管理费和托管费各是多少？",
        CHUNKS,
    ) == []

def test_fee_name_without_rate_is_not_evidence() -> None:
    chunks = [
        KnowledgeChunk(
            document_id="notice",
            source_name="notice.md",
            chunk_index=0,
            content="本资料未披露赎回费。",
        )
    ]

    assert missing_fee_terms("赎回费是多少？", chunks) == [
        "赎回费"
    ]


def test_does_not_borrow_another_fee_rate() -> None:
    chunks = [
        KnowledgeChunk(
            document_id="notice",
            source_name="notice.md",
            chunk_index=0,
            content="赎回费未披露，管理费每年0.50%。",
        )
    ]

    assert missing_fee_terms("赎回费是多少？", chunks) == [
        "赎回费"
    ]
