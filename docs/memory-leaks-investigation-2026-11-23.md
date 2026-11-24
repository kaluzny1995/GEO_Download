# Memory leaks investigation 2026-11-23

## Memory leaks investigation 2026-11-23

### Symptom

The GEO stack ran from 2026-11-17 without task errors, while host memory in the
Airflow callbacks grew from **11.92 GiB to 19.63 GiB** (~**1.3 GiB/day**); the
user-reported span was 8.7 → 22.2 GiB.

### Root cause

The growth was in the desktop session, not the pipeline: on 2026-11-23
`gnome-system-monitor` held **9.74 GiB RSS** and grew ~**1.1 GiB/day**; Chrome
held ~6.3 GiB. The nine GEO containers together held only ~2.6–3.4 GiB and were
flat across the run. The per-repository pages repeat this context so each repo
owns the same conclusion.

### GEO_Download audit

Every source runs in its own short-lived `run_download.py` subprocess, so Python
heap growth cannot survive a task. The audit found no module-level cache that
accumulates between days:

* `IBTrACS` caches the reference CSV only for the current run (`_cache_path` /
  `_cache_url`); the cache object dies with the process.
* `reverse_geocode` reloads and rewrites a bounded JSON map per run; it is not
  held between Process invocations.
* `_get_json` and `_download_csv` close every `requests.Response` in `finally`;
  the CSV reader streams lines instead of buffering the body first.
* `setup_logger` already reuses its file handler per `(name, file)`.

One real resource-lifetime gap remained: **`BaseDownloader` created a
`requests.Session` but never closed it**. The process exit hides this in the
Airflow path, but long-lived callers (tests, future multi-source runners) keep
the adapter's connection pool and response buffers until garbage collection.

### Change made

`BaseDownloader` now owns an explicit session lifetime:

```python
downloader.close()  # closes the requests.Session
with downloader:  # closes it on exit, even on error
    ...
```

`run_download.main()` closes the downloader in a `finally` block, so a failed
download (including the "nothing downloaded" `RuntimeError`) releases the pool
before the process exits.

Tests added in `test/downloader/test_base_downloader.py` (explicit close and
context-manager close on exception) and `test/test_run_download.py` (the runner
closes the downloader on the failure path).

### Verification

```bash
cd GEO_Download
conda run -n geo_download_311 python -m pytest -q
```

The unit tests assert both the direct close and the error-path close. The
Airflow task remains short-lived, so no cross-day growth is possible in this
repository.

### Conclusion

GEO_Download did not cause the host growth. The explicit session close removes
a latent descriptor/socket leak for long-lived callers and makes the downloader
safe to reuse.
