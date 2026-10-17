# Performance output ownership

Current performance execution and result formats belong to
[marty-performance](https://github.com/ElevenID/marty-performance).
See [performance qualification requirements](../../docs/PERFORMANCE_TESTING.md)
for retained workload, baseline, observability and reporting requirements.

Keep generated raw requests, summaries, reports and charts in ignored output
(such as `reports/generated/`) or bounded CI artifacts. Keep reviewed source
workloads, fixtures and baseline definitions under their owning repository's
version control. Old compatibility-service thresholds and CI examples are retired.
