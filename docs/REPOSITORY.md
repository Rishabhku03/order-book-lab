# Repository layout

Run project commands from the repository root, which contains `CMakeLists.txt`, `README.md` and `tools/`.

| Path | Contents |
| --- | --- |
| `include/`, `src/` | C++ replay library and command-line interface |
| `cmake/`, `CMakePresets.json` | Build configuration and pinned dependencies |
| `tools/` | Generation, independent checking, verification and reporting |
| `tests/`, `fuzz/` | Native, Python and browser tests; fuzz targets and regression seeds |
| `bench/` | Google Benchmark microbenchmarks |
| `web/` | Static viewer, sample exports and public measurement summaries |
| `docs/` | Event contract, methodology, testing instructions and verification evidence |
| `.github/workflows/` | CI and GitHub Pages workflows |

The sample exports let the viewer run without a compiler. Public evidence supports the measurements in the README.

Build caches, compiled programs, temporary workloads, logs and large raw benchmark artifacts are generated locally and excluded by `.gitignore`. They are not needed to clone and build the project. Builds download the pinned dependencies and create a new `build/` directory; verification creates a new `results/` directory.

Large raw measurements are kept separately from the source repository. The historical October 1 run includes latency samples, raw repetitions, the measured executable and its source archive. Its public summaries are in `web/evidence/`; section 18 of [the manual guide](MANUAL_TESTING.md) explains how to validate the complete artifacts when available.

## Start here

From the repository root, run:

```powershell
python tools/run.py doctor
python tools/run.py build
python tools/run.py test
python tools/run.py demo
```

To view the saved output without building first, run `python tools/run.py serve`. Follow [the manual guide](MANUAL_TESTING.md) for every test and later release step.

The release commit, remote CI execution and GitHub Pages deployment are pending. Their acceptance checks are documented in the manual guide.
