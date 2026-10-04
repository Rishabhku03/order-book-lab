# Local benchmark results

Measured on AMD Ryzen 7 5800H with Radeon Graphics, Windows-11-10.0.26200-SP0, MSVC 19.44.35229.0. Logical CPU 0; seven repetitions per group.

Inputs are synthetic. Each main workload contains one million measured events plus its setup prefix. Figures below are medians; raw repetitions and inclusive quartiles remain in the report.

## Order index comparison

| Candidate / tree | Lowest paired median speedup | Highest paired median speedup | Median across 27 workloads |
| --- | ---: | ---: | ---: |
| hash | 1.551× | 1.860× | 1.595× |
| hash_reserved | 1.566× | 1.825× | 1.598× |

The range shows workload dependence. The median across configurations gives equal weight to each workload; it is not a combined stream throughput. Reservation trades bucket allocation and setup costs against lookup and rehash behavior. Compare its populated memory and construction costs alongside speed.

## Reservation and a representative result

Reservation versus unreserved hashing produced paired median throughput ratios from 0.955x to 1.080x, with a median of 1.003x across 27 workloads. The gain was inconsistent. This experiment supports a tree-to-hash lookup improvement; it does not establish reservation as a general optimization.

For balanced medium, seed 42, reserved hash processed 7.114 million book updates/s. Its seven-run throughput IQR was 7.081 to 7.198 million events/s. The instrumented p99 was 300 ns in every run; tree p99 was 500 ns. The empty timer-pair p50 was zero at the clock's measurement granularity. No timer correction was subtracted.

The configured cap is 10,000 orders and 500 price levels per side. Memory was sampled after the 5,000-order setup prefix, before loading the event buffer. Median populated working set was 5.055 MiB for reserved hash, 4.988 MiB for unreserved hash, and 4.938 MiB for tree. Median construction times were 66.6, 2.0 and 1.5 microseconds, respectively. These are process measurements, including runtime overhead.

The representative reserved-hash/tree paired throughput ratio was 1.608x, corresponding to a median paired time reduction of 37.81%. Ratios are computed per matched repetition; dividing the two independently computed throughput medians gives a different value.

## Workload patterns at seed 42

| Workload | Tree M events/s | Hash M events/s | Reserved hash M events/s |
| --- | ---: | ---: | ---: |
| balanced-small-42 | 6.264 | 9.676 | 9.823 |
| balanced-medium-42 | 4.479 | 7.078 | 7.114 |
| balanced-large-42 | 2.550 | 4.690 | 4.636 |
| cancellation-small-42 | 6.601 | 10.272 | 10.360 |
| cancellation-medium-42 | 4.644 | 7.395 | 7.359 |
| cancellation-large-42 | 2.780 | 4.718 | 4.835 |
| execution-small-42 | 6.251 | 9.843 | 9.748 |
| execution-medium-42 | 4.535 | 7.120 | 7.096 |
| execution-large-42 | 2.657 | 4.660 | 4.605 |

Compare event profiles within a scale and implementation. Both order population and available depth change between scales, so the scaling result cannot be attributed to order count alone.

## Analytics, parsing and export

Analytics elapsed-time ratios range from 2.404× to 6.054× against their matching baselines.
Export elapsed-time ratios range from 52.704× to 56.861× against their matching baselines.

Parse-only medians range from 52.00 to 57.29 MB/s. End-to-end runs include file opening, parsing, replay and summary calculation; their file cache is uncontrolled.

## Limits and reproduction

Instrumented update latency includes timer reads; run-level p50, p95, p99, maxima, dispersion and the empty timer baseline are in the report. The saved gzip samples reproduce each percentile. Memory is Windows working set or Linux RSS, including process overhead.

Laptop power, scheduling and thermal drift can affect results. No network, queueing, real-market or profitability claim follows from these inputs.

Run `python tools/run.py benchmark --suite full` after a release build. It creates a fresh timestamped results directory; use its printed path for reporting or validation. To validate the completed local evidence, run `python tools/schemas.py --run results/full`. Existing benchmark directories can only resume with matching source and binary fingerprints.

Evidence: [comparison report](../web/benchmarks.html), [all measured groups](../web/evidence/summary.json), [raw repetitions](../web/evidence/raw-results.json), [environment](../web/evidence/environment.json).

## Saved local artifacts

`results/full/` contains every repetition, Google Benchmark output, workload manifests, state validation, latency samples and the generated report. `latency-samples.zip` bundles the 63 gzip files and their environment/validation metadata; `latency-archive.json` records its checksum. `measurement-sources.zip` and `bin/lob.exe` preserve the exact measured source and executable. The current CLI was rebuilt after the inspection-ordering repair. [Provenance](../web/evidence/report-provenance.json) records the difference; these figures remain October 1 measurements.

GitHub release attachment and a committed release identity are deferred until the user connects a repository.
