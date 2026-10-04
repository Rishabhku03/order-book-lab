# Benchmark methodology

## Inputs

Three profiles, three sizes and seeds 17, 42 and 2027 produce 27 configurations. Each full configuration contains a setup prefix and one million measured events. All variants receive byte-identical input. Generator version and SHA-256 appear in each manifest.

The setup prefix contains half the maximum live population. The generator forces adds below half capacity and changes adds to deletes at the cap. Requested percentages therefore differ from realized percentages, which are included in the manifests. The generated streams are valid workloads, not calibrated market simulations.

| Scale | Maximum live orders | Price levels per side |
| --- | ---: | ---: |
| Small | 1,000 | 100 |
| Medium | 10,000 | 500 |
| Large | 100,000 | 2,000 |

## Timed regions

Book and analytics measurements preload normalized events, build the setup state, then time the measured suffix. The analytics measurement computes the documented statistics after every suffix event. Parse-only timing reads bytes already in memory into a reserved event vector. End-to-end timing includes opening and reading CSV, parsing, replay and final summary calculation. Book construction and reservation are measured separately, outside that processing window. The setup ADD prefix is included in end-to-end replay.

The export experiment uses a separate 2,000-event fixture and writes newline-delimited JSON. Its book and end-to-end baselines use that same fixture. It measures serialization and output overhead; it is not mixed with million-event throughput.

Construction, event preloading, and setup times are recorded outside steady-state timing. Final-state checks occur after timing. Separate validation passes compare checkpoints every 250,000 events and final state across all variants.

One unrecorded warm-up precedes seven recorded repetitions. Each measurement uses a separate process and a selected logical CPU. Variant order is shuffled with seed 73. All raw repetitions are retained; no slow observations are dropped. Reports show median and inclusive-interpolated quartiles.

## Latency and memory

Instrumented latency is a separate pass on the three medium profiles with seed 42. It surrounds each book update with steady-clock reads and records nearest-rank p50, p95, p99 and maximum. Reported percentiles are medians of run-level percentiles. A timer-pair p50 from 10,000 empty clock-read pairs is reported without subtraction. The latency table summarizes each run statistic by its median, including the maximum column; every run's maximum remains in raw JSON. Maxima are scheduling-sensitive and are not service guarantees. Clock quantization can produce zero-duration observations.

Every measured latency pass also saves a gzip CSV in input order under `latency/`. Its checksum appears in the matching raw result. These files contain one `duration_ns` column. Sorting them and taking element `ceil(N*p)-1` reproduces each run's nearest-rank percentile. The report includes run-level quartiles as well as the median. Sample writing and compression occur after update timing.

Memory runs query the populated book before loading the event vector, then after loading and replay. These are Windows working-set or Linux RSS measurements. Current and peak process memory include runtime overhead. State serialization and invariant recomputation are excluded from the memory sample used in the report.

## Environment and interpretation

Record CPU, operating system, toolchain, release flags, source and binary hashes, affinity, power plan, Python version and workload hashes. Local scratch files reside outside the synchronized source folder. Their cache state is uncontrolled because checksum validation reads the input before timing; do not label the results cold-cache I/O.

Run on AC power without other heavy tasks. Different operating systems or compilers belong to different reports. CI runs smoke measurements to catch broken tools, not to set performance thresholds.

Throughput speedup is candidate events/s divided by baseline events/s. Time reduction is one minus candidate elapsed time divided by baseline elapsed time. Compare the same workload and timing boundary. A maximum improvement across configurations is not an average improvement. Report inconsistent or absent gains directly.

Raw JSON, summary CSV, environment metadata and charts are generated together. A dedicated validator checks every required group and repetition, matching input and final-state hashes, and recomputes latency percentiles from the gzip samples. A run is complete only when its completion marker exists. Never use an incomplete report as resume evidence.
