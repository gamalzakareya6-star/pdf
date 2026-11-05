"""On GitHub Actions, surface test failures as annotations so they are readable without downloading logs."""
import os


def pytest_runtest_logreport(report):
    if os.environ.get("GITHUB_ACTIONS") and report.when in ("setup", "call") and report.failed:
        text = (report.longreprtext or "")[-3500:]
        text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        title = report.nodeid.replace(",", " ").replace(":", " ")
        print(f"\n::error title={title}::{text}")
