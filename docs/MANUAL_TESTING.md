# Complete manual testing guide

Follow the sections in order. Commands below use Windows PowerShell from the project folder. Every expected success exits with code 0. An intentional native or launcher error exits with code 2. Check `$LASTEXITCODE` immediately after a command. Stop if an unexpected failure occurs; a later successful command does not erase it.

Keep a record with columns for step, actual result, pass/fail, evidence path, date and notes. Screenshots verify visible behavior. Native tests, independent comparisons and measurement files verify the backend requirements.

The release commit, repository connection, Linux CI and hosted publication are pending. Section 20 describes their acceptance checks.

## 1. Open the project and check prerequisites

In File Explorer, open the repository root: the folder containing `CMakeLists.txt`, `README.md` and `tools/`. Type `powershell` into its address bar and press Enter.

```powershell
Get-Location
python --version
python tools/run.py doctor
$LASTEXITCODE
```

Expected: Python 3.11 or newer; CMake, Ninja and MSVC compiler found; Clang, llvm-profdata and llvm-cov found for the full verification modes. The launcher discovers the Microsoft compiler environment, so an ordinary PowerShell window is sufficient.

For a new machine:

1. Install Microsoft Visual Studio Build Tools with **Desktop development with C++**, including its Windows SDK.
2. Install Python 3.11 or newer and LLVM/Clang with its sanitizer and coverage tools.
3. Run these commands, then repeat doctor:

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tools/run.py doctor
```

The first CMake build downloads four dependencies. Their exact commits and archive checksums are in `cmake/Dependencies.cmake`. Internet access is required for the first download; no account or market-data subscription is needed.

## 2. Build both ordinary configurations

```powershell
python tools/run.py build --preset debug
$LASTEXITCODE
python tools/run.py build --preset release
$LASTEXITCODE
.\build\release\lob.exe --version
.\build\debug\lob.exe --version
```

Expected: both builds succeed with project compiler warnings treated as errors. Version output identifies 1.0.0 and the build type. `uncommitted` is expected until the deferred Git release. Release is used for performance; Debug is used for additional correctness checks. A second build should reuse the dependency and compilation cache.

## 3. Run the ordinary tests

```powershell
python tools/run.py test --preset release
python tools/run.py test --preset debug
.\build\release\lob_tests.exe --list-tests
.\build\release\lob_tests.exe
```

Expected: all six C++ cases and nine Python tests pass on release. Debug intentionally skips the one release-only benchmark test. The current C++ suite has 524 assertions.

Check each named C++ case appears:

| Case | Requirements exercised |
| --- | --- |
| Full lifecycle and analytics agree across indexes | All event types; partial/full reductions; ID reuse; null metrics; crossed/locked/empty states; snapshot(0); clear and restarting at sequence 0 |
| Every semantic error preserves complete state | Duplicate/unknown IDs; fields; excessive reductions; invalid replacement; invalid enum/side; sequence/time rejection; unchanged counters and orders |
| Overflow rejects updates without changing orders or trades | Total quantity, trade multiplication and accumulated trade overflow; atomic rejection |
| Level ordering and weighted formulas | Independent best-price expectations; best-level deletion; repricing; top-five imbalance; weighted midpoint |
| Counter overflow, replacement overflow and multi-price VWAP | Counter-limit injection; atomic replacement overflow; hand-calculated VWAP |
| Parser rejects malformed input and accepts CRLF | Header/field/type/side/integer errors; signed/unsigned overflow; line limit; LF/CRLF; final line without newline |

The Python tests also exercise deterministic generation, independent final states, metamorphic transformations, CLI errors, output protection, paths containing spaces, time-filtered exports and corrupted schemas. Counter-limit injection and `clear()` are library tests because those conditions cannot be reached through a small practical CSV. Run the named cases to verify them rather than trying to emit billions of events manually.

## 4. Prepare the manual contract and upload fixtures

Choose a fresh directory for each repetition:

```powershell
$manual = 'results/manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python tools/manual_cases.py --out $manual --check
Get-Content "$manual/cases.json"
```

Expected: 49 contract cases and 147 native checks pass, including independent final-state comparison for every valid case and every index variant. `verification.json` records the result. The script rejects an existing destination; choose another name to repeat it.

Keep `$manual` in this PowerShell session for the following commands. The JSON file lists every fixture's expected exit code and error text, so you can check each separately.

## 5. Replay and inspect every event type manually

```powershell
foreach ($variant in @('tree','hash','hash_reserved')) {
    .\build\release\lob.exe validate --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --variant $variant --full-state
    $LASTEXITCODE
}
```

Expected: all three final states agree; only variant metadata differs. Final state has one bid order, ID 1, price 100 ticks, quantity 1; no ask; execution volume 10, execution notional 1000, VWAP 100; event counts `[4,2,1,2,2]`; peak live orders 3.

Inspect each accepted sequence:

```powershell
foreach ($sequence in @(1,3,4,5,6,7,8,9,10,11,12)) {
    .\build\release\lob.exe inspect --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --sequence $sequence --full-state
}
```

| Sequence | Change | Expected state or calculation |
| ---: | --- | --- |
| 1 | ADD bid ID 1, 100 ticks, 10 units | One-sided; midpoint/spread/imbalances null; VWAP null |
| 3 | ADD ask ID 2, 104 ticks, 30 units | Sequence gap and equal timestamps accepted; midpoint 102; spread 4; imbalance -0.5; weighted midpoint 101 |
| 4 | ADD bid ID 3 at the same price, 20 units | Bid aggregate 30 units and 2 orders; imbalance 0; weighted midpoint 102 |
| 5 | CANCEL 5 from ID 3 | ID 3 remains with 15; bid aggregate 25 |
| 6 | EXECUTE 4 from ID 1 | ID 1 remains with 6; volume 4; notional 400; VWAP 100 |
| 7 | REPLACE ask ID 2 with ID 4 at 99 ticks, 7 units | Side remains ask; crossed; spread -1; old ID absent |
| 8 | REPLACE ID 4 with now-inactive ID 2 at 100 ticks | Locked; spread 0; ID reuse accepted |
| 9 | DELETE ID 3 | Its remaining 15 units removed; bid aggregate 6 and 1 order |
| 10 | EXECUTE the remaining 6 from ID 1 | No bid level remains; one-sided ask; volume 10; VWAP 100 |
| 11 | CANCEL all 7 from ID 2 | Empty book; no occupied levels; two-sided analytics null; VWAP remains 100 |
| 12 | ADD reused ID 1 | New bid order accepted after its earlier removal |

Test exact sequence lookup:

```powershell
.\build\release\lob.exe inspect --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --sequence 2
$LASTEXITCODE
```

Expected: code 2 and `requested sequence not found`. The engine requires the exact target; it still checks the complete file checksum and parses later records without applying them.

Also verify ordering errors beyond an inspection target:

```powershell
.\build\release\lob.exe inspect --input "$manual/reversed-sequence.csv" --manifest "$manual/reversed-sequence.manifest.json" --sequence 2
.\build\release\lob.exe inspect --input "$manual/reversed-time.csv" --manifest "$manual/reversed-time.manifest.json" --sequence 1
```

Expected: both exit 2 with a sequence/timestamp error, even though inspection skips later book updates. Inspection cannot accept a reordered input file.

Run the multi-price trade example:

```powershell
.\build\release\lob.exe validate --input "$manual/vwap.csv" --manifest "$manual/vwap.manifest.json" --full-state
.\build\release\lob.exe validate --input "$manual/empty.csv" --manifest "$manual/empty.manifest.json"
.\build\release\lob.exe validate --input "$manual/one-sided.csv" --manifest "$manual/one-sided.manifest.json"
```

Expected: VWAP is `(2*100 + 3*110)/5 = 106`, volume 5 and notional 530. Header-only input is a valid empty session; a file with no header is invalid. The missing side, midpoint, spread and imbalances are null; the available best quote remains present. The top-five formula is checked using the hand-calculated C++ case in section 3.

## 6. Export results, full state and an inclusive time range

```powershell
$output = "$manual/replayed"
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output $output --trace
Get-ChildItem $output
Get-Content "$output/summary.json"
Get-Content "$output/manifest.json"
```

Expected: `summary.json`, `manifest.json`, `trace.json`. Summary says `complete: true`; manifest and trace connect to the original SHA-256 and engine version. Trace contains 11 frames, each with its accepted event, timestamp, top-ten depth, statistics and analytics.

```powershell
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output "$manual/no-trace"
Test-Path "$manual/no-trace/trace.json"
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output "$manual/range" --trace --trace-from-ns 3 --trace-to-ns 4
Get-Content "$manual/range/trace.json"
```

Expected: `False` for the trace-disabled run. Filtered trace contains sequences 5 and 6 only. At sequence 5 the bid quantity is 25, proving the preceding ADD records were applied. The final summary still describes sequence 12 and all 11 events. Bounds are inclusive; equal timestamps retain their input order.

```powershell
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output "$manual/reversed-range" --trace --trace-from-ns 4 --trace-to-ns 3
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output "$manual/trace-limit" --trace --trace-limit 1
```

Expected: both exit 2; reversed range and exceeded trace limit explained. These failed runs do not produce a successful summary. Native traces have a default 10,000-frame limit and an explicit upper safety bound of 100,000; the browser always limits compatible traces to 10,000 frames and ten levels per side. Expanded `--full-state` traces are for verification and may exceed the viewer's depth contract.

## 7. Inspect exact serialization and input integrity

```powershell
$trace = Get-Content "$output/trace.json" -Raw | ConvertFrom-Json
$trace.frames[0].event
$trace.frames[0].analytics
Get-FileHash "$manual/lifecycle.csv" -Algorithm SHA256
Get-Content "$manual/lifecycle.manifest.json"
```

Expected: IDs, sequence, timestamp, quantity and tick prices are decimal JSON strings. Unavailable analytics are `null`, never zero, NaN or infinity. File hash equals manifest `sha256` and trace `input_sha256` (PowerShell may display the hash in uppercase).

Copy the files before deliberately corrupting them:

```powershell
Copy-Item -LiteralPath "$manual/lifecycle.csv" -Destination "$manual/corrupted.csv"
Copy-Item -LiteralPath "$manual/lifecycle.manifest.json" -Destination "$manual/corrupted.manifest.json"
Add-Content -LiteralPath "$manual/corrupted.csv" -Value 'corruption'
.\build\release\lob.exe validate --input "$manual/corrupted.csv" --manifest "$manual/corrupted.manifest.json"
$LASTEXITCODE
```

Expected: code 2, input SHA-256 mismatch, `complete: false`. Refreshing a checksum does not make an invalid event stream valid; the separate contract fixtures already have correct hashes and must still fail semantic/parser checks.

## 8. Run every parser and semantic rejection case

```powershell
foreach ($case in (Get-Content "$manual/cases.json" -Raw | ConvertFrom-Json)) {
    Write-Host $case.name 'expected exit' $case.expected_exit
    .\build\release\lob.exe validate --input "$manual/$($case.name).csv" --manifest "$manual/$($case.name).manifest.json"
    Write-Host 'Actual exit:' $LASTEXITCODE
}
```

Check every row in `cases.json`; do not just check the last exit code. Expected rejection groups include:

- Duplicate active ADD ID; unknown CANCEL, DELETE, EXECUTE and REPLACE IDs.
- Excessive cancellation/execution; zero ADD/CANCEL/EXECUTE/REPLACE quantity.
- Zero/negative prices, missing side, extra replacement ID on ADD.
- Replacement to active or same ID, missing replacement ID, replacement side field.
- Inapplicable fields on DELETE/CANCEL; duplicate or decreasing sequence; decreasing timestamp.
- Total quantity overflow, replacement total overflow, execution product and accumulator overflow.
- Missing/extra fields; bad/negative/overflowing integers; price overflow; unknown type; bad side; spaces and quoted numbers.
- Blank record, oversized line, completely empty file, malformed header.
- LF, CRLF and final line without newline must succeed.

Every native failure returns incomplete JSON on stderr with the input filename and a reason. Event failures identify the line and sequence. The CLI stops at the first error. The core atomicity tests and state fuzzer check that rejected updates leave orders, levels, trade totals, counters and accepted ordering state unchanged; the CLI does not expose a rejected book for subsequent use.

## 9. Check CLI failures and output protection

```powershell
.\build\release\lob.exe
.\build\release\lob.exe unknown
.\build\release\lob.exe validate --unknown x
.\build\release\lob.exe validate --input missing.csv --manifest missing.json
.\build\release\lob.exe validate --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --variant unknown
.\build\release\lob.exe validate --input "$manual/lifecycle.csv" --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json"
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output $output --trace
```

Expected: each exits 2; the existing replay directory remains intact. Check its summary checksum before and after the last command if desired. Unknown, missing and duplicate options have clear errors.

```powershell
Set-Content -LiteralPath "$manual/obstacle" -Value 'keep'
.\build\release\lob.exe replay --input "$manual/lifecycle.csv" --manifest "$manual/lifecycle.manifest.json" --output "$manual/obstacle/result"
Get-Content "$manual/obstacle"
```

Expected: code 2 for write failure and the obstacle still contains `keep`. Also replay a fixture copied into a directory whose name contains spaces; quote both file arguments. The Python integration suite checks this automatically.

Manifest error tests in `test_manifest_and_output_errors` cover negative/zero capacity, setup greater than total, wrong event count, unsupported/fractional schema version, non-synthetic flag and zero tick size. Run them directly:

```powershell
python -m unittest discover -s tests -p test_tools.py -v
```

## 10. Generate your own deterministic workload

```powershell
python tools/generate.py "$manual/generated.csv" --events 2000 --seed 42 --profile balanced --size small
python tools/generate.py "$manual/generated-again.csv" --events 2000 --seed 42 --profile balanced --size small
Get-FileHash "$manual/generated.csv"
Get-FileHash "$manual/generated-again.csv"
Get-Content "$manual/generated.manifest.json"
.\build\release\lob.exe validate --input "$manual/generated.csv" --manifest "$manual/generated.manifest.json"
```

Expected: identical CSV hashes and manifest values. Small workload has 500 explicit setup ADDs plus 2,000 requested measured events. `--events` specifies the measured suffix, not total file length. Generator refuses to overwrite an existing CSV.

Repeat with `--profile cancellation` and `--profile execution`, and `--size medium` and `--size large`, using new filenames. The exact matrix is three profiles × three scales × seeds 17/42/2027. Requested weights, realized counts/percentages, cap/depth, min/max/mean live population and population histogram must be visible in the manifest. Validity controls can change requested proportions. Prices occupy separate bid and ask bands; IDs increase; reductions are positive and bounded. The golden fixture test detects changed generated bytes.

## 11. Independent checks and metamorphic properties

```powershell
python tools/run.py verify --suite full --checks core
Get-Content results/verification.json
python -m unittest discover -s tests -p test_tools.py -v
```

Expected: 100 seeds × 2,000 measured events, capacity 200, all three indexes; 630,000 event states including 100 setup events per seed. Each variant contributes 200,000 measured comparisons. The independent Python implementation recomputes levels from active orders. Exact integers match; floating-point tolerance is relative 1e-12 and absolute 1e-10.

The metamorphic test independently verifies these transformations across all variants:

1. Rename IDs, including values above JavaScript's exact integer range: levels and analytics stay equal.
2. Multiply quantities by three: level quantities triple; midpoint and imbalance stay equal.
3. Add 123 ticks to every price: levels, midpoint, weighted midpoint and VWAP shift by 123; spread and imbalances stay equal.

The independent checker is intentionally for bounded valid books. It is not the large-workload timing tool or a second browser engine.

## 12. Start the complete local dashboard

In terminal A:

```powershell
python tools/run.py demo
```

Expected: C++ regenerates three scenarios and opens `http://127.0.0.1:8765/`. If the port is already serving the dashboard, use that page, stop the existing server with Ctrl+C in its terminal, or use `--port 8766`. Do not run a second server on the occupied port.

`python tools/run.py serve` opens the already-exported data without regenerating it. Keep terminal A running while testing. Use terminal B for other commands. After code changes, regenerate demo and reload the browser to avoid testing cached assets.

## 13. Check every replay control and visible feature

1. Confirm the page background and panel/control backgrounds are white. Text, borders, focus outlines, chart strokes and bars are black. Bids use a solid line; asks use a dashed line. Browser font smoothing may show neutral edge shades.
2. Confirm the page labels synthetic data, saved C++ output and one instrument. Engine provenance and input SHA-256 appear in About.
3. Balanced flow starts at Event 1 / 2000. Previous is disabled. Its first bid is 999.95, quantity 251; no ask; spread and imbalance show N/A; state is one-sided.
4. Click Next, then Previous; position and selected-event details change and return correctly.
5. Seek to Event 151 (slider index 150). Both tables have ten levels. Best bid is 999.99, best ask 1000.02, spread 3 ticks and displayed imbalance -0.713. Cumulative depth is nondecreasing in quantity. Spread and imbalance history end at the selected frame.
6. Click Play at 1 event/s; observe several events. Pause and confirm position stays still. Repeat at 10 and 100 events/s. Change speed during playback; playback continues at the selected rate. These are presentation settings, not native benchmark results.
7. Seek during playback; playback stops at the chosen frame. Previous/Next also stop playback. Reset returns to Event 1 and Play.
8. Seek to the last event; Next is disabled. Play at the last event restarts from the beginning. At the end of playback the control returns to Play.
9. Select cancellation-heavy flow; it starts at Event 1 / 2000 and changes its book/details. Switch to lifecycle; it starts at Event 1 / 9.
10. Use Tab and Shift+Tab to reach links, selectors, upload, buttons and slider. Focus must be visible. Space toggles focused Play/Pause; arrow keys move the focused slider; selectors and file input are usable from the keyboard.
11. Scroll to About and footer; confirm all content is readable and no colored accents or runtime CDN assets appear.

## 14. Verify all nine browser lifecycle frames

Step forward one event at a time through the lifecycle scenario. Prices below are displayed currency values; engine prices remain integer ticks with tick size 0.01.

| Event | Action and expected display |
| ---: | --- |
| 1 | ADD ID `9007199254740993` displayed exactly; bid 100.00, quantity 100; one-sided, missing metrics N/A |
| 2 | ADD ask 100.04, quantity 60; normal; spread 4; imbalance 0.250 |
| 3 | ADD bid 99.99, quantity 80; two occupied bid levels |
| 4 | EXECUTE 40 from first bid; quantity becomes 60; spread 4; imbalance 0.000 |
| 5 | REPLACE ask with ID 4 at 99.99; crossed; spread -1 |
| 6 | REPLACE ask with ID 5 at 100.00; locked; spread 0 |
| 7 | CANCEL remaining 60 from first bid; best bid becomes 99.99; normal |
| 8 | DELETE bid ID 3; one-sided ask; bid table says No orders |
| 9 | EXECUTE all remaining ask; empty; both tables say No orders; missing metrics N/A |

Check the selected-event explanation for ADD/CANCEL/DELETE/EXECUTE/REPLACE, exact sequence and synthetic timestamp. Previous and seeking must restore the prior saved state exactly. Executions use resting prices; the browser does not perform matching.

## 15. Downloads, local uploads and exact limits

Download the CSV, manifest and trace for **each** scenario. Open them and confirm their input hashes agree. Load a downloaded trace with OPEN YOUR TRACE; it returns to frame 1, hides CSV/manifest links and retains a working trace download. Switching back to a bundled scenario restores all three downloads and clears the upload selection.

The manual fixture directory contains these browser files:

| File | Expected result |
| --- | --- |
| valid-upload.json | Accepted, lifecycle begins at frame 1 |
| bad-upload.json | Clear schema error; playback stops |
| zero-upload.json | Invalid ADD fields error |
| numeric-id-upload.json | Invalid identifier error; 64-bit IDs must be strings |
| 10mb-upload.json | Accepted: exactly 10,485,760 bytes, valid JSON plus whitespace |
| over-10mb-upload.json | Rejected: 10 MB size error |
| 10000-frames-upload.json | Accepted: exactly 10,000 structurally compatible frames |
| frame-limit-upload.json | Rejected: 10,001-frame error; compact file is below the size limit |

The last two files are deliberate schema-boundary fixtures, not new C++ replays. They reuse a saved frame with updated sequence fields. Browser validation checks the export structure, not order-lifecycle correctness.

Also edit copies of `valid-upload.json` and try: missing/invalid input hash or instrument; mismatched event/statistics sequence; descending timestamp; duplicate sequence; unknown event; zero level quantity; unsorted levels; price/ID outside their integer range; more than ten levels on a side; missing/non-finite analytics, or null in a required integer field. Each must show a clear validation error without executing content. A literal `<script>` in a compatible string field must display as text, never execute. Local file uploads do not send the file to a server; inspect the browser Network panel during upload to confirm no upload request.

After an invalid upload, choose a valid file or a bundled scenario. The error disappears and playback works. Open browser developer tools Console and verify there are no JavaScript errors. The error shown inside the app for a rejected file is expected.

## 16. Responsive and visual checks on all pages

Inspect Replay, Benchmarks and Verification at desktop 1440×1000 and mobile 390×844, using your browser's responsive mode.

1. Confirm no page-wide horizontal scrolling, clipped controls or overlapping labels. Replay tables stay readable and panels stack on mobile.
2. Check initial and populated books, each event type, every status, upload errors, hover/focus and disabled controls.
3. Benchmarks: inspect throughput, latency and memory charts; all measured groups; paired comparisons; parsing/setup costs; latency distribution; analytics/export overhead; method and evidence links. Wide tables/charts scroll within their containers on mobile. All seven evidence links download readable data.
4. Verify latencies are labeled instrumented, maxima as medians of run maxima, memory as process working set/RSS, and the release commit as uncommitted until release.
5. Verification: open and close every recorded-checks section; download all six evidence files. Inspect long JSON on mobile; it must wrap within the panel. Deferred external release steps remain visible.

Repeat the automated visual and browser checks:

```powershell
python tools/run.py browser-test
python tests/visual_audit.py
Get-Content results/visual-audit/summary.json
```

Expected: all flows pass, no page or console errors, black/white computed colors, 22 captured views. Open **every** PNG listed in the summary to review layout, wording, charts and event states. Automated color/overflow checks cannot replace viewing those screenshots.

## 17. Sanitizers, fuzzing, coverage and full verification

You can run all local release checks with:

```powershell
python tools/run.py build
python tools/run.py verify --suite full
```

This runs ordinary tests and the full differential suite, then Debug, Clang sanitizers, coverage, both 900-second fuzz targets, demo regeneration, schemas, browser/visual checks, a fresh source build/reproduction and formatting. It does not run the full performance matrix. Allow time for downloads, compilation and a fresh fuzz session; leave it running until the final completion message.

For separate inspectable checks:

```powershell
python tools/run.py build --preset sanitize
python tools/run.py verify --preset sanitize --suite smoke
python tools/run.py build --preset coverage
python tools/coverage.py
python tools/run.py build --preset fuzz
python tools/fuzz.py --seconds 900
python tools/format.py --check
python tools/schemas.py
python tools/reproduce.py
```

Expected evidence:

| Check | What to open and verify |
| --- | --- |
| ASan/UBSan | No sanitizer report; tests and 18,900 smoke comparisons pass; `results/verification-sanitize-3-2000.json` complete |
| Coverage | `results/coverage/summary.json`: at least 90% lines and 80% branches; open `results/coverage/html/index.html` for uncovered code |
| Fuzzing | `results/fuzz/summary.json`: parser and state, at least 900-second budget each, exit 0, matching source/binary fingerprints; examine both logs and retained corpus |
| Formatting | Exit 0; compiler warning checks are part of successful builds |
| Export schema | Three demo traces pass |
| Reproduction | `results/reproduction/summary.json`: release built without workspace cache; all tests pass; nine demo artifacts match except deferred commit metadata |
| Aggregate | `results/release-verification.json`: complete true, all local groups recorded, external checks explicitly pending |

Short fuzz smoke (`--seconds 30`) writes `results/fuzz-smoke` and cannot replace the 900-second release evidence. If fuzzing finds a crash, retain its log and artifact, fix the defect, minimize the failing input using libFuzzer's crash minimization mode, add it to the regression corpus, and rerun both targets. Passing fuzz/sanitizer runs do not prove absence of all defects.

## 18. Audit the existing full measurement evidence

The original local artifacts remain outside the source upload. In this installation, use `../results/full`; if you have restored the raw release artifacts inside the project, use `results/full`. A clone contains the public summaries, but this historical audit also requires the separately retained raw samples, measured executable and source archive.

```powershell
$historical = '../results/full'
if (-not (Test-Path "$historical/complete.json")) { $historical = 'results/full' }
python tools/schemas.py --run $historical
$audit = 'results/workload-audit-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python tools/audit_workloads.py --run $historical --out $audit
Get-Content "$audit/workload-audit.json"
python tools/run.py report --run $historical
```

Expected: 369 groups, 2,583 raw runs, seven repetitions, 63 latency artifacts and `samples_recomputed: true`. The workload audit regenerates every million-event input, checks the complete manifest, replays all three variants, compares each saved checkpoint/final hash, checks event counts and recalculates stored medians/quartiles/paired ratios. It also verifies the measured source archive and preserved measured binary in `results/full/bin/`. It records whether the current binary still matches; the inspection-ordering fix requires a rebuilt current binary. It does not replace the historical timing observations with new numbers.

The report command writes `report.html`, `summary.json`, `summary.csv`, evidence and a generated write-up within its run directory. It preserves the reviewed `docs/BENCHMARK_RESULTS.md` and the dashboard's published report. Open the run's `report.html` in a browser to inspect it.

`audit_workloads.py` audits the bundled October 1 evidence specifically, including its frozen source archive and reviewed write-up. For a new run, use the general schema validator and inspect its recorded provenance. New source/binary fingerprints prevent silently resuming an old run.

## 19. Run smoke and full performance experiments yourself

Finish all correctness/fuzz checks first. Close browser playback and other heavy applications. Plug the laptop into AC power and record its power mode. Keep it ventilated and note interruptions or thermal drift. Use a nonsynchronized local result directory.

```powershell
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$smoke = Join-Path $env:LOCALAPPDATA "OrderBookLab/benchmarks/manual-smoke-$runStamp"
python tools/run.py benchmark --suite smoke --run $smoke --cpu 0
python tools/schemas.py --run $smoke
python tools/run.py report --run $smoke
```

Expected: the small balanced seed-42 input, two repetitions per main group, latency, isolated memory and small export comparisons, plus Google Benchmark evidence. Smoke charts carry a preliminary warning. Smoke results are a tool check and must not replace full resume measurements.

```powershell
$full = Join-Path $env:LOCALAPPDATA ('OrderBookLab/benchmarks/manual-full-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
python tools/run.py benchmark --suite full --run $full --cpu 0
python tools/schemas.py --run $full
python tools/run.py report --run $full
```

The earlier full run took about 90 minutes on this laptop; duration varies. Do not run other tests simultaneously with performance timing. The launcher prints progress by workload and saves all repetitions, including slow ones. An interrupted run has no completion marker. Resume using the same `--run` path only if source, binary, suite, CPU, OS and compiler still match. Changed fingerprints require a new directory.

Inspect the following before treating a run as evidence:

- `complete.json`: complete, 27 main workloads and seven repetitions; the extra export fixture is separate.
- `environment.json`: CPU, RAM, OS, compiler/version, actual configured flags, dependency versions, source/binary hashes, selected logical CPU, timestamp, power information, synchronized-folder labels and uncontrolled file-cache label. Release flags must have no sanitizers, coverage or fast-math.
- `workloads/`: all 27 profiles/scales/seeds plus the small export manifest, with setup counts, realized mix and checksums. Inputs are generated in temporary local storage.
- `validation/`: identical checkpoints and final hashes from all variants, outside timed passes.
- `raw/`: seven repetitions for every required group, input/final hash, accepted counts, timestamps and affinity. The untimed warm-up is deliberately not a raw measured repetition.
- Book timing excludes parser, preload/reservation/setup, analytics traversal and output. Book+analytics includes the documented metrics and top-five traversal. Construction/preload/setup costs are recorded separately.
- Parse timing consumes bytes already in memory and includes normalized-event creation. Parsing MB/s uses decimal megabytes. End-to-end includes opening/read/parse, setup and measured events, replay and final summary; it excludes large trace generation.
- Export compares the same separate 2,000-event fixture against its book/end-to-end baselines and flushes serialized output within timing.
- Latency covers all three medium profiles, seed 42, all variants and seven repetitions. `latency/` has 63 gzip files, one million samples each. Each raw record includes sample count, checksum, nearest-rank method, p50/p95/p99/max and empty timer-pair p50. Timer overhead is reported without subtraction. Samples are saved after update timing.
- Memory runs use isolated children. Populated memory is sampled after half-capacity setup, before event-array loading; buffer bytes, occupied levels, live/peak orders, bucket count, current and peak process memory remain visible. Values describe process working set/RSS, not exact allocator bytes per order.
- `summary.json`/CSV: median and inclusive IQR over repetitions; run-level latency medians and dispersion; paired speedups and time reduction from the same workload and repetition; analytics/export overhead and memory charts.
- `microbench.json`: separate Google Benchmark repetitions, warm-up, release build and observable work. These tiny lifecycle results are distinct from whole-stream headline measurements.

Recalculate a raw throughput value as accepted measured events / elapsed seconds, and average ns/event as elapsed seconds × 1e9 / measured events. This average is not p99. Nearest-rank p99 is sorted sample at `ceil(N*0.99)-1`. Ratios compare matched boundaries and environments. Keep Windows and Linux/compiler results separate. Discuss gains, regressions, reservation costs, event-mix effects and seed/repetition variability; never select the largest speedup as an overall claim. Depth and capacity change together across scales.

The existing headline numbers describe October 1 measurements, not today's new timings. The original inputs are synthetic. Neither benchmark speed nor weighted midpoint establishes network latency, a trading forecast or profitability.

## 20. Release, privacy, cross-platform CI and hosting later

These steps require a release commit and a configured GitHub repository:

1. Review README, all public `web/` files, downloads and evidence for local usernames, private paths, unrelated files or credentials. Public data must remain labeled synthetic. Large input CSVs and raw latency samples belong in reproducible local/release artifacts, not ordinary source commits.
2. Create the authorized release commit and record its identity. Rebuild and regenerate the demo so exported engine commits refer to that release. Retain the source hashes and commit associated with historical benchmark measurements; do not relabel old measurements as a new engine version.
3. Reproduce from a genuinely clean committed checkout. The current fresh-source test is useful but has no Git metadata. Verify README setup/build/test/demo commands and exact generated inputs/canonical outputs from the checkout.
4. Run `.github/workflows/ci.yml` on GitHub. Check Windows/MSVC and Ubuntu/GCC native jobs, Clang sanitizer/fuzz job, coverage job and browser/visual job. Download artifacts and inspect failures/results. Actions are pinned to immutable revisions. CI smoke speeds are not headline figures or timing pass/fail thresholds.
5. Complete 900-second release fuzz sessions and coverage targets for the release code; regenerate demo and verify its output schema/browser flows. Review artifact checksums and release evidence.
6. Configure GitHub Pages to use GitHub Actions. Manually run `publish demo`; its verification job must pass before deployment. Pages is not automatically published on every push. Verify repository/environment permissions and artifact upload/deployment results.
7. Open the hosted URL at desktop/mobile sizes and repeat sections 13 through 16, especially relative asset/download paths, local uploads and visible release identity. Record the actual URL in README.
8. Attach raw per-run results, source/environment/workload manifests, compressed latency samples and checksums to the release. Every README/resume number must link to the matching completed evidence. Use two or three supported resume claims after reviewing their measurement scope.

## 21. Finish and keep the evidence

Save your pass/fail record and screenshots, plus the relevant JSON/logs. Stop the local server with Ctrl+C in terminal A, confirm the localhost page no longer reloads, then restart `python tools/run.py serve` to check a normal restart. Preserve benchmark results; choose fresh directories instead of deleting or overwriting previous evidence.

Completion means every local section passed and any external section is explicitly marked pending or supported by actual run evidence. A screenshot, configured workflow or completion flag alone cannot establish every requirement.
