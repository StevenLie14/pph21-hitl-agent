from pathlib import Path

from .settings import get_settings

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
PIPELINE_DIR = REPO_ROOT / "pipeline"
TESTS_DIR = REPO_ROOT / "tests"
STATIC_DIR = PACKAGE_DIR / "web" / "static"

DATA = get_settings().data_root
