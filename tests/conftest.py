import os
import tempfile
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# Force pytest temp files into the workspace so Windows permissions do not break tmp_path.
LOCAL_TMP_DIR = ROOT_DIR / ".pytest_tmp"
LOCAL_TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(LOCAL_TMP_DIR)
os.environ["TEMP"] = str(LOCAL_TMP_DIR)
os.environ["TMPDIR"] = str(LOCAL_TMP_DIR)
tempfile.tempdir = str(LOCAL_TMP_DIR)


def pytest_configure(config) -> None:
    # Use a fresh basetemp each run so pytest does not reuse a stale directory
    # with Windows ACLs inherited from a previous process.
    config.option.basetemp = tempfile.mkdtemp(dir=str(LOCAL_TMP_DIR), prefix="basetemp-")
