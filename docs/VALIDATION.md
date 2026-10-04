# Local validation

Local verification passed on Windows on October 4, 2026. The October 1 full performance matrix passed independent result validation. The release commit and GitHub publication are pending. See [the detailed audit](DEEP_AUDIT.md) and [manual testing guide](MANUAL_TESTING.md).

## Completed checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Native C++ semantics and parser tests | 6 test cases, 524 assertions; MSVC debug and release | Local test logs and [aggregate release checks](evidence/release-verification.json) |
| Python integration and schema tests | 9 tests on release; debug/sanitizer runs skip the release-only benchmark test | [Aggregate release checks](evidence/release-verification.json) |
| Independent differential verification | 100 seeds, 2,000 measured events per seed, all three variants; 630,000 comparisons including setup | [Correctness JSON](evidence/verification.json) |
| AddressSanitizer and UndefinedBehaviorSanitizer | C++ and integration tests passed; 3-seed differential check passed with Windows Clang 23.1.2 | [Sanitizer differential result](evidence/sanitizer.json) |
| Coverage | 312/321 lines: 97.20%; 219/239 branches: 91.63% | [Coverage summary](evidence/coverage.json) |
| Parser fuzzing | Fresh 900-second budget, 75,809,302 executions, no reported failure | [Fuzz summary](evidence/fuzz.json) |
| State fuzzing | Fresh 900-second budget, 312,431 executions, no reported failure | [Fuzz summary](evidence/fuzz.json) |
| Browser interaction and visual checks | Chromium desktop 1440 x 1000 and mobile 390 x 844; white backgrounds, black text/charts, playback and upload flows passed | [Visual audit](evidence/visual-audit.json), [browser checks](evidence/browser.json) |
| Fresh source reproduction | New build without the workspace cache; tests passed and nine demo artifacts reproduced | [Reproduction summary](evidence/reproduction.json) |
| Formatting and compiler warnings | Formatting passed; project warnings fail builds | [Aggregate release checks](evidence/release-verification.json) |

Coverage includes `book.hpp` and its analytics, `parser.hpp`, and `types.hpp`. CLI and browser behavior have separate integration tests. Defensive invariant failures and some unreachable counter paths remain uncovered. Passing coverage, sanitizers and fuzzing provides evidence about the exercised code; it does not prove the absence of defects.

Reviewed screenshots: [desktop replay](evidence/visual-desktop.png), [mobile replay](evidence/visual-mobile.png) and [benchmark page](evidence/visual-benchmarks.png).

Differential verification compares complete orders, aggregated levels, counters and analytics after each accepted event. Integers must match exactly. Derived floating-point values use relative tolerance 1e-12 and absolute tolerance 1e-10. Each variant contributes 200,000 measured-event comparisons; setup events add 30,000 comparisons across all variants.

State fuzzing compares all three indexes against an independent vector model. Both fuzz targets keep a regression corpus and retain failure artifacts. The October 4 aggregate verification ran fresh 900-second sessions and recorded matching target/binary fingerprints. Separate release/debug/sanitizer regression checks cover the inspection-ordering repair.

## Performance evidence

The full suite completed 27 main workloads, 369 measurement groups and 2,583 recorded runs, with seven repetitions per group. The [evidence validator](../web/evidence/schema-validation.json) checked required groups and repetitions, input/final-state hashes, CPU affinity and measurement formulas. It recalculated p50, p95, p99 and maxima from 63 million samples in 63 checked gzip files. Google Benchmark results are retained separately in `results/full/microbench.json`.

The reserved-hash balanced medium workload at seed 42 processed a median 7.114 million book updates/s; throughput IQR was 7.081 to 7.198 million events/s. Its instrumented p99 was 300 ns in all seven runs. This used a Ryzen 7 5800H, Windows 11, MSVC 19.44 and logical CPU 0. The workload declares a 10,000-order cap and 500 available levels per side; its setup contains 5,000 live orders. Book-only timing excludes parsing, analytics traversal and output.

Across the 27 workloads, reserved-hash paired throughput versus tree ranged from 1.566x to 1.825x, with a median of 1.598x across configurations. Reservation versus unreserved hash ranged from 0.955x to 1.080x, with a median of 1.003x. It provided no consistent improvement over unreserved hashing. All scenario-level results remain visible.

Measurements ran on AC power with the Balanced power plan; beginning and ending metadata record those settings. The dashboard stayed on a static page during timing. Input and raw-result files were stored outside OneDrive. File-cache state was uncontrolled, and laptop scheduling or thermal drift can affect measurements. No slow run was removed.

The [benchmark interpretation](BENCHMARK_RESULTS.md) and [browser report](../web/benchmarks.html) link the full public evidence. `results/full/latency-samples.zip` preserves the original gzip samples with environment and validation metadata. `results/full/bin/lob.exe` preserves the exact measured executable and matches its recorded SHA-256. `measurement-sources.zip` preserves the measured source fingerprint. The current CLI was rebuilt for the inspection-ordering repair; its complete benchmark timing function and core headers remain unchanged, but historical timings are not relabeled as new measurements. The [provenance](../web/evidence/report-provenance.json) records these differences. These local artifacts can be attached to a release after GitHub is connected.

## Repeating the checks

```text
python tools/run.py build
python tools/run.py verify --suite full
python tools/run.py benchmark --suite full
python tools/run.py report --run results/full
python tools/run.py serve
```

For laptop performance measurements, use AC power, close the dashboard and avoid concurrent heavy work. Prefer a local nonsynchronized results directory. File-cache state is uncontrolled; these runs do not establish cold-cache performance.

The benchmark command creates a new timestamped run directory and prints its path. Supply `--run` with a new local directory to choose its location. An existing directory resumes only when the source and binary fingerprints match. The report command above opens the completed evidence bundled in this workspace; use a new run's printed directory to report new measurements.

## External release steps

- Execute the configured GCC/Linux, Clang/Linux and Windows/MSVC jobs after connecting a repository.
- Create the Git release commit, then repeat reproduction from that committed checkout.
- Publish GitHub Pages after reviewing the public artifacts and passing the deployment checks.

The source currently has no Git commit. Exports identify it as `uncommitted`; benchmark evidence records source and executable SHA-256 hashes. Local verification and fresh-source reproduction are complete. Cross-platform CI execution, committed-checkout reproduction and hosted deployment remain pending.
