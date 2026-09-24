# Local benchmark workspace

Real-paper benchmark data is local by default. Initialize the ignored `benchmark/workspace/`
directory with:

```powershell
python benchmark.py init benchmark/workspace --name "Calibration set"
python benchmark.py add benchmark/workspace path/to/paper.pdf --domain "machine learning"
python benchmark.py serve benchmark/workspace
```

PDFs, PIR files, annotations and reports under `workspace/` are ignored by Git. This avoids
publishing copyrighted papers, model outputs or reviewer notes by accident. Only export a
curated dataset after checking its redistribution rights and removing personal information.

See [`docs/benchmarking.md`](../docs/benchmarking.md) for the annotation rules and metrics.
