from pathlib import Path


def test_no_kraken_runtime_reference() -> None:
    root = Path(__file__).parents[1] / "app"
    offenders = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sql"}:
            if "kraken" in path.read_text(encoding="utf-8").lower():
                offenders.append(str(path))
    assert offenders == []
