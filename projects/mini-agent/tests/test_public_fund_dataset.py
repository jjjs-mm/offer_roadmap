import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads(
        (PROJECT_DIR / relative_path).read_text(encoding="utf-8")
    )


def test_public_fund_manifest_has_unique_reproducible_documents() -> None:
    manifest = load_json("data/public_funds/manifest.json")
    documents = manifest["documents"]
    filenames = [document["filename"] for document in documents]
    hashes = [document["sha256"] for document in documents]
    managers = [document["fund_manager"] for document in documents]

    assert len(documents) == 24
    assert len(filenames) == len(set(filenames))
    assert len(hashes) == len(set(hashes))
    assert len(set(managers)) >= 9
    assert all(manager.strip() for manager in managers)
    assert all(len(value) == 64 for value in hashes)
    assert all(
        document["source_url"].startswith("https://")
        for document in documents
    )


def test_public_fund_datasets_are_disjoint_and_valid() -> None:
    manifest = load_json("data/public_funds/manifest.json")
    dev = load_json("data/public_fund_eval_dev.json")
    test = load_json("data/public_fund_eval_test.json")
    blind = load_json("data/public_fund_eval_blind_v2.json")
    blind_v3 = load_json("data/public_fund_eval_blind_v3.json")
    filenames = {
        document["filename"] for document in manifest["documents"]
    }

    assert dev["split"] == "dev"
    assert test["split"] == "test"
    assert test["frozen"] is True
    assert blind["split"] == "blind"
    assert blind["frozen"] is True
    assert blind["created_after_query_normalizer_v1"] is True
    assert blind_v3["split"] == "blind"
    assert blind_v3["frozen"] is True
    assert blind_v3["created_after_dev_v3"] is True
    assert len(dev["cases"]) == 130
    assert len(test["cases"]) == 30
    assert len(blind["cases"]) == 30
    assert len(blind_v3["cases"]) == 10

    dev_ids = {case["case_id"] for case in dev["cases"]}
    test_ids = {case["case_id"] for case in test["cases"]}
    blind_ids = {case["case_id"] for case in blind["cases"]}
    blind_v3_ids = {case["case_id"] for case in blind_v3["cases"]}
    assert len(dev_ids) == len(dev["cases"])
    assert len(test_ids) == len(test["cases"])
    assert len(blind_ids) == len(blind["cases"])
    assert len(blind_v3_ids) == len(blind_v3["cases"])
    assert dev_ids.isdisjoint(test_ids)
    assert dev_ids.isdisjoint(blind_ids)
    assert test_ids.isdisjoint(blind_ids)
    assert dev_ids.isdisjoint(blind_v3_ids)
    assert test_ids.isdisjoint(blind_v3_ids)
    assert blind_ids.isdisjoint(blind_v3_ids)

    for dataset in (dev, test, blind, blind_v3):
        for case in dataset["cases"]:
            assert case["selected_source"] in filenames
            assert case["expected_source"] in {None, case["selected_source"]}
            assert all(page > 0 for page in case["expected_pages"])
            assert bool(case["expected_source"]) == bool(
                case["expected_pages"]
            )
