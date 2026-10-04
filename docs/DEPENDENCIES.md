# Dependencies

The engine's data structures and algorithms use the C++ standard library. Two header libraries handle JSON and input checksums. Catch2 and Google Benchmark are development dependencies.

| Library | Version or commit | License |
| --- | --- | --- |
| Catch2 | 3.8.1 / 56809e5282f104c5c8b570e7c2996cdc352d94f1 | BSL-1.0 |
| Google Benchmark | 1.9.4 / 31c66f47f60d06790a4885a261d682ba339bd100 | Apache-2.0 |
| nlohmann/json | 3.12.0 / 65ee68451d8eb2b5f3a30b410476ab83deb3289b | MIT |
| PicoSHA2 | 161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29 | MIT |

Archive SHA-256 values are pinned in the CMake dependency file. The original license files remain in each downloaded source directory. Preserve those notices if redistributing dependencies or compiled releases.

Python development packages are pinned in `requirements-dev.txt`. The generator, reference checker and report builder use Python's standard library. Playwright is used only for browser verification. The viewer itself has no third-party JavaScript dependency or CDN request.
