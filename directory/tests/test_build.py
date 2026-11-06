"""The committed artifacts are what the hand-written contract gives."""

from cedar_odcs.engine.contract import build
from directory.usecase import CONTRACT, ROOT


def test_committed_artifacts_are_what_the_contract_gives():
    for rel, text in build(ROOT, CONTRACT).items():
        assert (ROOT / rel).read_text() == text, f"{rel} is behind the contract; run cedar-odcs build"
