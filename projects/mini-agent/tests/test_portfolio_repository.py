from hashlib import sha256

from mini_agent.portfolio import analyze_portfolio_csv
from mini_agent.portfolio_repository import PortfolioRepository


CSV_CONTENT = (
    "name,asset_type,quantity,price\n"
    "沪深300ETF,equity_fund,100,4.20\n"
    "中短债基金,bond_fund,500,1.25\n"
)


def test_repository_saves_and_loads_portfolio(tmp_path) -> None:
    database_path = tmp_path / "portfolio.sqlite3"
    file_bytes = CSV_CONTENT.encode("utf-8")
    analysis = analyze_portfolio_csv(CSV_CONTENT)

    repository = PortfolioRepository(database_path)

    saved = repository.save(
        filename="portfolio.csv",
        file_bytes=file_bytes,
        analysis=analysis,
    )

    assert len(saved.portfolio_id) == 32
    assert saved.filename == "portfolio.csv"
    assert saved.content_sha256 == sha256(file_bytes).hexdigest()
    assert saved.analysis == analysis

    # 创建新的 Repository，模拟另一个进程重新连接数据库。
    another_repository = PortfolioRepository(database_path)
    loaded = another_repository.get(saved.portfolio_id)

    assert loaded == saved


def test_repository_returns_none_for_unknown_id(tmp_path) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )

    assert repository.get("missing-id") is None