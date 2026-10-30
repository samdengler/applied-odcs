# The tests import the descriptor as hr.usecase; put the repository
# root on sys.path.  The build's outputs are never committed, so build
# them from the contract before any test module loads the use case.
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from cedar_odcs.engine.contract import build, write  # noqa: E402

write(ROOT / "hr", build(ROOT / "hr", "Employee"))
