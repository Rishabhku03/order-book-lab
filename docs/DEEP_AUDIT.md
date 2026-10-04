# Audit against the original implementation plan

Audit date: October 3, 2026. The local audit and verification are complete; the external release gates listed below remain pending.

The local feature set follows the original scope. This audit found and repaired an ordering defect in `inspect`, tightened browser trace validation, and corrected report regeneration and setup diagnostics. The remaining release work is a Git commit, reproduction from that committed checkout, Linux CI execution and GitHub Pages deployment.

The benchmark observations remain the October 1 measurements. This audit recalculates their evidence and reproduces their inputs/states; it does not claim new full-matrix timings for the rebuilt CLI. The exact measured executable and source archive are preserved. The book, parser, analytics and benchmark timing function are unchanged by the inspection fix.

Use [the complete manual guide](MANUAL_TESTING.md) to repeat every local workflow. It gives commands, expected values, negative fixtures, UI actions and release checks.

## Findings and repairs

| Finding | Repair | Verification |
| --- | --- | --- |
| `inspect --sequence 2` accepted a file ordered 1, 3, 2 because it skipped sequence 3 before validating ordering | Validate every inspected record's sequence/timestamp, including records beyond the selected book state | Regression cases across all three variants, release/debug/sanitizer integration suites |
| Uploaded frames could have missing provenance, event/statistics ordering mismatch or unsorted depth | Require trace provenance, integer statistics, matching ordering fields, event counters and sorted occupied levels | Browser rejection tests; existing C++ traces still load |
| Upload tests did not exercise exact accepted size/frame limits | Test exactly 10 MB and exactly 10,000 frames, and reject one byte/frame more | Browser integration; manual boundary files generated separately |
| Rebuilding a report overwrote the reviewed benchmark write-up and restored an outdated rerun command | Write generated interpretation inside the run directory, preserve reviewed docs; use a fresh-directory rerun command and correct relative evidence links | Report regeneration and before/after document comparison |
| Doctor displayed Windows setup instructions on Linux; application-control diagnostic pointed to removed documentation | Platform-specific setup text and an actionable application-control message | Windows doctor execution; Linux branch source review |

No change introduces matching, inferred fills or a trading strategy. Allocation failure remains fatal, as documented; semantic rejection is atomic. Browser upload checks validate saved-output structure and do not implement another order book.

## Evidence and test scope

| Evidence | What it establishes |
| --- | --- |
| `tests/test_core.cpp`, six cases / 524 assertions | Core events, invariants, error atomicity, overflow, ordering, analytics, parser and clear API |
| `tests/test_tools.py` and `tests/test_schemas.py`, nine Python tests | Generator golden/determinism, metamorphic properties, CLI/manifest/write errors, independent final states, export precision and corrupted schemas |
| `results/verification.json` | 100-seed event-by-event Python comparisons across all three implementations; 630,000 states including setup |
| `results/audit-20261003/current-manual/verification.json` | 49 inspectable valid/invalid contract fixtures, 147 native checks |
| `results/verification-sanitize-3-2000.json` | ASan/UBSan build smoke comparisons and the separate native/integration suite |
| `results/coverage/summary.json` | Core/parser/analytics coverage, thresholds enforced |
| `results/fuzz/summary.json` and both logs | Fresh 900-second parser and independent-reference state fuzz sessions; target/binary fingerprints |
| `results/audit-20261003/current-build/workload-audit.json` | All 27 million-event inputs regenerated; all variants' checkpoints/final state agree; saved benchmark aggregates and archives checked |
| `results/full/schema-validation.json` | All 369 groups / 2,583 runs, formulas, repetitions, hashes, affinity and 63 million latency samples checked |
| `results/browser/verification.json`, `results/visual-audit/summary.json` | Browser flows, accepted/rejected upload boundaries, safe text rendering, console/page errors, palettes and responsive layouts |
| All 22 PNGs in `results/visual-audit/` | Direct visual review of each event type/status and desktop/mobile replay, charts, errors and evidence pages |
| `results/reproduction/summary.json` | Fresh source copy builds/tests and reproduces nine demo artifacts; excludes Git identity |
| `results/audit-20261003/manual-workflow/verification.json` | Manual guide lifecycle values, optional/ranged trace export, existing output protection and inspection ordering commands executed |
| `results/audit-20261003/smoke-schema.json` | Fresh corrected-binary smoke: 25 groups, 50 runs, six latency artifacts and Google Benchmark execution |
| `docs/evidence/deep-audit.json` | Final audit scope, current binary identity and explicit remaining gates |
| `results/release-verification.json` | Aggregate local workflow; external completion is explicitly separate |

Each source file in the engine, tools, tests, viewer, fuzz targets, dependency declarations and workflows was inspected. Large measurement/trace files were checked by validators and independent aggregate calculations rather than treated as proof merely because they contain a completion flag.

## 1. Summary, scope and architecture

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Compact C++20 project with recorded single-instrument replay | Present in CMake, types, book and CLI | 1, 2, 5 |
| Five event types | ADD/CANCEL/DELETE/EXECUTE/REPLACE implemented and checked | 3, 5, 8 |
| Independent Python implementation | Separate transitions and full level recomputation in `reference.py` | 11 |
| Three comparable C++ implementations | Shared book with tree, hash, reserved hash order indexes | 5, 18, 19 |
| Tests, sanitizers, fuzzing, cross-platform builds | Local checks executed; Windows/Linux automation configured; Linux execution pending | 17, 20 |
| Synthetic reproducible workloads | Versioned SplitMix64 algorithm, manifests and golden bytes | 10, 18 |
| Browser demo displays saved C++ output | Static HTML/CSS/JS/SVG; no browser book implementation | 12 through 16 |
| Hosted demo | Pages workflow configured; actual publication pending | 20 |
| Honest README/benchmark/resume evidence | Measurements tied to hardware, workload, timing boundaries and original source | 18 through 20 |
| No matching, FIFO, live feeds, backtesting, concurrency, pools or WASM | Source remains within the exclusions | 5, 14 |
| Generated data; native Windows; no WSL/Docker prerequisite | Windows launcher/toolchain and pure static viewer | 1, 12 |
| Parsing, updates, analytics and serialization separated | `parser.hpp`, `book.hpp`, `output.hpp`, benchmark modes and tooling | 3, 19 |
| Immutable dependency versions and hashes | Four commit-addressed archives with SHA-256; Python package pins | 1, 20 |
| CMake Debug/Release/sanitize/coverage presets | Present with platform-specific compiler/runtime handling | 2, 17 |
| Optimized release measurements without fast-math/sanitizers/coverage | Observed release flags saved; harness refuses instrumented configurations | 19 |

## 2. Event contract, state and error behavior

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Public apply, best bid/ask, depth snapshot, statistics, clear | Value-returning APIs present; lifecycle and clear tests | 3, 5 |
| Engine owns mutable order state; snapshots do not expose references | Orders and levels private; public snapshots copy values | 3 |
| Parsing errors separate from ApplyResult semantic errors | Parser throws line-numbered errors; apply returns reason without mutation | 8 |
| Exact eight-column CSV with versioned accompanying manifest | Strict header and field count; schema/tick/instrument/config/hash metadata | 7, 8, 10 |
| uint64 sequences/IDs/quantities/timestamps; positive int64 ticks | `from_chars` parsing, field validation and overflow fixtures | 7, 8 |
| Increasing sequences, equal timestamps, gaps, no sorting | Core and inspect ordering checks; timestamp-gap lifecycle fixture | 5, 8 |
| Empty initial book, explicit ADD prefix | Generator prefix and empty fixture | 5, 10 |
| Time export replays preceding events | Complete replay with inclusive output-only time filtering | 6 |
| Inapplicable CSV fields empty | Per-kind semantic checks and fixtures | 8 |
| ADD inactive ID, positive quantity and side/price | Duplicate/field/price/quantity checks | 5, 8 |
| Partial/full CANCEL reduces/removes | Lifecycle and independent fixtures | 5 |
| DELETE entire remaining quantity | Level/order cleanup checked | 5 |
| EXECUTE reduces/removes, resting-price trade accounting | Partial/full and multi-price VWAP tests | 5 |
| REPLACE distinct inactive new ID, side preserved, validated first | Replacement, active/same ID, zero quantity and overflow atomicity tests | 5, 8 |
| Reuse removed IDs allowed; generated IDs monotonic | Lifecycle reuse and generator implementation | 5, 10 |
| Unknown IDs/excess reductions/zero quantities/overflow rejected | Every documented semantic error exercised across variants | 3, 8 |
| Rejected event leaves state, trades, counters, accepted ordering unchanged | Core full-state comparisons and state fuzz model | 3, 8, 17 |
| CLI stops at first error and labels incomplete | Native JSON error path and fixture exits | 8, 9 |
| Order-ID index plus separate ordered sides | Same order semantics and level storage across variants | 5, 19 |
| Per-level quantity/order count, running totals, best at first map entry | Invariant recomputation, full snapshots and best-level tests | 3, 5 |
| No FIFO needed; executions identify IDs | API and UI/documentation state this limit | 5, 14 |
| Unreserved hash and reserved hash share load factor 1.0 | Constructor inspected; reservation uses declared manifest cap | 19 |
| Defaults to hash_reserved; all variants remain in reports | Default CLI argument and complete group checks | 5, 18 |
| Orders positive, one level each; totals/counts exact; no empty levels | `invariants()` independently reconstructs maps from orders | 3, 11 |
| Best prices agree with independent scan | Ordered expected levels in Python/reference and C++ cases | 3, 11 |
| Locked/crossed input accepted and flagged | Core lifecycle and each browser status viewed | 5, 14 |

## 3. Analytics, CLI and exports

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Best quotes with quantity, spread, midpoint | Snapshot values and hand calculations | 5, 13 |
| Top-level and top-five imbalance | Formula tests and event-by-event comparisons | 3, 11 |
| Weighted midpoint and descriptive interpretation | Hand-weighted formula; documented predictor limitation | 3, 5, 19 |
| Execution volume/VWAP from exact checked integer notional | Checked multiplication/addition and independent trade totals | 5, 8 |
| Event counts, active orders, levels, peak live count | Statistics export and complete state comparison | 5, 11, 19 |
| Empty/one-sided/normal/locked/crossed status | All present and inspected | 14 |
| Unavailable analytics null; finite JSON | Empty/one-sided/VWAP-null and schema corruption tests | 5, 7 |
| Top-five traversal outside book-only timing | Timed loop source inspected; analytics consumes every metric | 19 |
| Launcher doctor/build/test/demo/verify/benchmark/report | Commands executed; setup and report regressions checked | 1 through 3, 12, 17 through 19 |
| Direct replay/validate/inspect | Fixture commands and inspection regressions | 5, 6, 9 |
| Meaningful exits, paths with spaces, errors with context | Python integration and manual CLI fixtures | 8, 9 |
| Existing results not silently overwritten | Native export rejection; generator rejection; guarded benchmark resume | 6, 9, 10, 19 |
| Ordinary long-run progress outside benchmark timing | Replay reports every million events; harness progress between workloads | 19 |
| Summary and manifest on success; optional trace off by default | Export integration and artifact inspection | 6 |
| Trace event/time/sequence/top-ten/analytics/status | Export schema, checker, viewer and download checks | 6, 7, 15 |
| 64-bit IDs/timestamps strings; missing values null | Output source and precision-hazard schema/browser tests | 7, 14, 15 |
| Synthetic label, input SHA, configuration and engine identity | Manifests and trace provenance; Git identity currently uncommitted | 7, 20 |

## 4. Browser interaction and visual appearance

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Three labeled synthetic scenarios, <=2,000 frames each | Balanced/cancellation 2,000; lifecycle 9 | 13, 14 |
| Play/pause/next/previous/reset/slider | Interaction tests and direct browser review | 13 |
| 1/10/100 events per second | Each rate advances and pauses; rates remain presentation-only | 13 |
| Ten-level table and cumulative depth | Populated desktop/mobile views; solid/dashed legend | 13, 16 |
| Spread and imbalance history | Saved-frame charts with visible single-point markers | 13, 16 |
| Selected-event explanation | Every event type viewed and checked | 14 |
| Benchmark comparison page and definitions | Charts/tables, timing/memory/latency scope and raw evidence | 16, 19 |
| Input/output/benchmark downloads | Scenario response hashes and every public evidence link checked | 15, 16 |
| Local compatible trace loading, stays in browser | File API with safe DOM text; no upload endpoint | 15 |
| 10 MB and 10,000-frame limits with errors | Exact accepted/rejected boundary tests, manual fixtures | 15 |
| Keyboard accessibility, focus, readable responsive layout | Play keyboard checks, black focus, viewport/overflow inspections | 13, 16 |
| No runtime CDN; bundled assets | Viewer contains only local assets and browser APIs | 16 |
| Later requested white background and black everything else | Computed DOM/pseudo/SVG palette checks and direct screenshots | 16 |
| Safe display of uploaded values | Script-like commit string rendered as text without an image node | 15 |
| Browser errors absent | Both console-error and page-error listeners enabled | 16 |

## 5. Data generation and correctness matrix

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Generator transitions independent of checker | Dense live-ID generator versus recomputed dictionary reference | 10, 11 |
| Three requested event profiles | Weights match 30/25/15/20/10, 30/40/20/5/5, 30/10/10/40/10 | 10 |
| Three capacities/depths | 1,000/100; 10,000/500; 100,000/2,000 per side | 10, 19 |
| Seeds 17,42,2027 and 27 configurations | Full manifests regenerated and compared | 18 |
| One million measured events plus explicit setup | Manifest/count/checkpoint checks | 18, 19 |
| Positive bounded reductions, partial/full reductions, separate bands | Generator source and bounded/full replays | 10, 11, 18 |
| Forced ADD below half cap, ADD becomes DELETE at cap | Source inspected; live histogram and max bounded | 10, 18 |
| Realized mix and population distributions | Manifest values regenerated exactly | 10, 18 |
| Frozen generator version and golden fixture | SplitMix64-v1 plus committed hash test | 3, 10 |
| Empty/one-sided/best disappearance/reprice/locked/crossed edge fixtures | Unit, manual and demo lifecycle cases | 5, 14 |
| Python full orders, rebuilt levels, counters and analytics comparisons | Recursive exact-int/tolerant-float checker | 11 |
| 100 seeds ×2,000 valid measured events, cap 200 | Full differential result and variant breakdown | 11 |
| Large streams compare variants at checkpoints and final state | Every 250,000 events and final hash, regenerated audit | 18 |
| LF/CRLF; missing/extra/blank/header/type/side/int/overflow/oversize/empty parser cases | Six-case core suite and 49 manual fixtures | 3, 8 |
| All event errors and valid reductions/replacements/reuse | Core/CLI fixtures across variants | 3, 5, 8 |
| Ordering/first/last/same-price/best-deletion/one-sided/crossed transitions | Core, inspection regression and browser lifecycle | 3, 5, 14 |
| Hand-calculated analytics and missing values | Mid/spread/imbalance/weighted/VWAP cases | 3, 5 |
| Metamorphic rename/quantity scale/price shift within bounds | Independent transformed levels/analytics across indexes | 11 |
| CLI missing files/options/write failure/spaces/exits/incomplete | Integration and direct manual exercises | 9 |
| Browser playback/seek/reset/scenarios/uploads/large IDs/errors | Integration and visual audit | 13 through 16 |
| ASan/UBSan and parser/state fuzzing with independent small model | Local Windows Clang evidence; Linux execution pending | 17, 20 |
| Fixed corpus, minimized failures retained, CI smoke, 15-minute targets | Corpus and wrapper inspected; fresh release sessions; no unresolved failure to minimize | 17 |
| >=90% line, >=80% branch for core/parser/analytics | 97.20% lines and 91.63% branches; thresholds enforced | 17 |
| Explicit semantic errors regardless of coverage | Named error/atomicity/overflow tests, not just aggregate percentage | 3, 8 |

## 6. Benchmark boundaries and protocol

The full stored matrix is historical evidence. The current-build workload audit proves input and state reproduction, not a new timing result for the rebuilt executable.

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Parse-only in-memory bytes -> events | File loading/reservation precede timed parser region | 19 |
| Book-only preloaded events -> validated updates | Preload/setup outside timed suffix; no analytics traversal | 19 |
| Book plus all analytics including top-five | Observable sink consumes every metric and status | 19 |
| End-to-end open/read/parse/replay/summary | Includes setup, excludes browser trace generation | 19 |
| Export serialization separated | Bounded 2,000-event fixture, timed serialization and flush; same fixture baselines | 19 |
| Separate instrumented event latency | Preallocated samples, steady-clock update timing, sort/output afterwards | 19 |
| Separate isolated memory experiments | Fresh child per repetition; populated before buffer; peak before canonical serialization | 19 |
| Same release settings/checksum/state for variants | Environment flags, raw input hashes and final state validation | 18, 19 |
| Untimed warm-up then seven measurements, fresh state | Repetition -1 discarded, isolated subprocesses each pass | 19 |
| Recorded random variant order seed, retain slow runs | Seed 73, random shuffle plus per-run timestamps; complete repetitions validated | 19 |
| Median and IQR, separate machine/compiler groups | Independent aggregates and environment grouping | 18, 19 |
| Setup excluded steady book but included end-to-end | Native loops and counts inspected | 19 |
| Reservation/preloading outside steady timing; cost recorded | Construction/preload/setup tables, memory and buckets | 19 |
| EPS, derived average ns/event, parse MB/s, elapsed and overhead | Formulas checked per raw result; report recalculated | 18, 19 |
| Average ns/event not called latency percentile | Documentation and report labels | 19 |
| p50/p95/p99/max, nearest rank, count, timer baseline, no subtraction | 63 million saved samples recalculated; clock quantization documented | 18, 19 |
| Latency all three medium profiles seed42, all variants, seven runs | Nine groups × seven gzip files | 18, 19 |
| Run-level percentiles summarized after within-run calculation | Independent medians and run quartiles verified | 18 |
| Synthetic timestamps not used as clock latency/network measure | Steady-clock durations only; explicit limitations | 19 |
| Windows working set/Linux RSS, counts/depth/buffer/reserve/buckets | Per-process memory fields; Windows evidence, Linux configured | 19, 20 |
| No exact allocator bytes/order or simultaneous speed-memory claim | Reports separate modes and process-memory limits | 19 |
| Tree/hash, reservation, mix, overhead, variation experiments | Scenario-level charts/tables and honest reservation null result | 16, 19 |
| Paired throughput ratio and time reduction; range, no cherry-picked overall best | All paired comparisons independently recalculated | 18, 19 |
| AC/power, CPU affinity, hardware/compiler/flags/hash/deps/date | Environment manifest and beginning/ending power data | 19 |
| Local nonsynchronized I/O scratch; cache uncontrolled; variability/thermal limits | Generator scratch and report labels | 19 |
| CI checks tools/schemas, no hard speed thresholds/headline CI numbers | Workflow source reviewed | 20 |
| Raw JSON/CSV/env/workload/hash/chart evidence and compressed latency artifact | Existing full result and archive hashes checked | 18 through 20 |

## 7. Reproduction, CI, documentation and release

| Original requirement | Assessment and evidence | Manual guide |
| --- | --- | --- |
| Demo/smoke/full verification/full benchmark modes | Separate launcher workflows with explicit scopes | 12, 17, 19 |
| Exact generated/canonical integer results, timing allowed to vary | Golden/differential/reproduction/full input checks | 10, 11, 18 |
| Windows/MSVC and Linux/GCC native CI; Clang sanitizer/coverage | Configured; local Windows executed; actual Linux/remote CI pending | 20 |
| PR differential/golden/schema/bench smoke/browser/format/warnings | CI stages present; source reviewed | 20 |
| Release full verification/fuzz/coverage/demo/schema/clean reproduction | Local source-copy checks executed; committed checkout pending | 17, 20 |
| Workflow actions pinned by immutable revision | SHA-addressed action references reviewed | 20 |
| Pages separate gated deployment with required artifact/permissions | Workflow reviewed against official documentation; hosting pending | 20 |
| README purpose/demo/results/quickstart/design/limits | Local demo and supported results present; hosted link pending | 12, 20 |
| Separate event/testing/benchmark methodology docs | Present; manual guide adds all commands and expected results | All |
| Public release commit; no private username/path/unrelated files | Hashes and uncommitted label present; release identity deferred; public files reviewed | 20 |
| Every README/resume number supported by evidence | Correctness/coverage historical timing links and scope reviewed | 18 through 20 |
| Real feed later only, LOBSTER/ITCH caveats | Generated contract and no real-feed/profit claims retained | 20 |
| Implement within proposed work phases/budget | Features and acceptance gates audited; the 45-hour estimate was a planning estimate, not a measured development-time result | 20 |
| Acceptance: no unresolved test/fuzz defects | Local tests, sanitizers and fresh 900-second fuzz sessions passed; every discovered defect repaired and retested | 17 |
| Acceptance: full matrix/final state equivalence/evidence | Historical full matrix verified, current states reproduced; final committed release timing refresh remains a release step | 18 through 20 |
| Acceptance: desktop/mobile hosted viewer and clean committed checkout | Local responsive viewer verified; hosted and committed gates pending | 16, 20 |

## Remaining release gates

1. Authorize/configure the Git release identity and create the release commit.
2. Reproduce from that committed checkout and regenerate exports with its identity.
3. Run the prepared Windows and Linux CI jobs in the connected repository.
4. Refresh final release performance measurements using a new result directory; retain historical October 1 evidence separately.
5. Review the public files, attach release evidence/checksums, deploy Pages and repeat the UI checks on the actual hosted URL.

These gates are not marked passed merely because their scripts exist. The local dashboard and testing workflow can be used now.

## Research checks

The audit checked warm-up, repetitions, observable work and JSON output against the [Google Benchmark guide](https://google.github.io/benchmark/user_guide.html), preset structure against the [CMake presets reference](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html), and the deployment dependency/artifact/permission structure against [GitHub Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages). These references support the chosen tooling; the project's own saved executions establish its observed results.
