"""ai/library — the Library data layer (Increment 6 / LIB, VG-13).

Spec §15.4 wants a Library that knows, for every document: **where it came
from**, **who uses it and how much**, **whether it is still true**, and **how
to open it at the passage that answered the question**. `documents` had eight
columns and knew none of the four.

Built so far (T1–T2, pulled forward — see [06_lib.md](../../../docs/product-road-map/increment-6/06_lib.md)):

* **provenance** — ten columns on `documents` (`library.provenance`);
* **influence** — `retrieval_usages`, written at the caller after rerank,
  non-blocking (`library.models`, `library.usage_log`).

T3–T8 (rollup + reaper, staleness, artifact filing, citations, connected
drives, credential expiry) are not built. The two here came first because they
are **time series, and a time series started later cannot be backfilled** —
every week without the usage log is a week of influence data that does not
exist, the same argument LEARN's KPI history makes.

Import submodules directly; this package init deliberately re-exports nothing,
following the rule an `ai/` package init must not import back toward its own
consumers (the VOICE lesson, HANDOFF §5).
"""
