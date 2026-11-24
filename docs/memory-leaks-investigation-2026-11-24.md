# Memory leaks investigation 2026-11-24

## Memory leaks investigation 2026-11-24

### Symptom

Host memory was **33 % before the 2026-11-24 pipeline run and 35.2 % after it**
(+~1.4 GiB on a 62.5 GiB host). This follow-up checks the download layer after
yesterday's session-lifetime fix.

### Finding

No download leak. Every source still runs in a short-lived
`run_download.py` subprocess; no `conda run`, `run_download` or HTTP session
process remained after the 07:00–07:22 run. The Airflow scheduler cgroup was
0.58 GiB at rest (peak 2.45 GiB during ETL), and the nine GEO containers held
1.95 GiB total.

The host increase is the desktop session:

| Measurement | Value |
|-------------|------:|
| `gnome-system-monitor` | 10.65 GiB, +0.87 GiB since 23 Nov |
| Chrome | 6.54 GiB, +0.21 GiB since 23 Nov |
| All nine GEO containers | 1.95 GiB |

`gnome-system-monitor` is the same process identified on 2026-11-23 and is still
growing ~1.1 GiB/day. No HTTP response or session is retained between daily
runs.

### Code status

No new leak and no code change today. Yesterday's explicit
`BaseDownloader.close()` / context-manager lifetime and the `run_download.main()`
`finally` close are deployed in the rebuilt Airflow image. Unit tests still cover
the explicit close and the error path.

### Verification

```bash
cd GEO_Download
conda run -n geo_download_311 python -m pytest -q
docker stats --no-stream
```

### Conclusion

GEO_Download does not explain the host increase. Closing or restarting
`gnome-system-monitor` releases its ~10.6 GiB history buffer. After the monitor exited at ~18:44, host used fell from 22.0 GiB (35.2 %) to 11.1 GiB (17.6 %), confirming the attribution. Full evidence is
in [GEO_E2E — Memory leaks investigation 2026-11-24](../../GEO_E2E/docs/memory-leaks-investigation-2026-11-24.md).
