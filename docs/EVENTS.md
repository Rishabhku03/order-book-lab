# Event and output contract

## Input

CSV schema version 1 uses the exact header:

```text
sequence,timestamp_ns,type,order_id,side,price_ticks,quantity,new_order_id
```

The parser accepts LF or CRLF and a final line without a newline. Blank records, quoted fields, whitespace around numbers, invalid headers, unknown types and lines over 4,096 bytes are rejected. Inapplicable fields must be empty. Input records are never reordered.

IDs, quantities, sequences and timestamps are unsigned 64-bit integers. Prices are positive signed 64-bit integer ticks. ID zero is allowed. The first sequence may be zero; later sequences increase strictly. Gaps and equal timestamps are allowed. Timestamps cannot decrease.

| Event | Fields beyond sequence, timestamp, type and ID | Behavior |
| --- | --- | --- |
| ADD | Side B/A, price, positive quantity | Introduce an inactive ID |
| CANCEL | Positive quantity | Reduce remaining quantity |
| DELETE | None | Remove the entire order |
| EXECUTE | Positive quantity | Reduce quantity and record a trade at resting price |
| REPLACE | Price, positive quantity, new ID | Replace old order, preserve side |

The new ID in a replacement must differ from the old ID and be inactive. An inactive ID may be reused. Both full cancellation and full execution remove the order and any empty price level.

Every file starts from an empty book. Initial orders must appear as ADD events. A depth snapshot alone cannot initialize the order-ID index.

## Validation and atomicity

Semantic validation runs before mutation. Unknown IDs, duplicate active IDs, excessive reductions, invalid fields and arithmetic overflow leave the observable book unchanged. Rejection also preserves event counters, execution statistics and the last accepted sequence and timestamp.

Allocation failures are fatal to a run; the library does not promise a usable book after an allocation exception. The CLI reports incomplete output and exits with code 2. It does not continue after a rejected event. Successful runs exit with code 0.

Book quantity, execution volume and execution notional use checked unsigned 64-bit arithmetic. An execution whose price-times-quantity product or accumulated notional cannot fit is rejected. This intentionally bounds supported session size.

Locked and crossed books are accepted and labeled. No inferred matching, queue priority or automatic execution is performed.

## Manifest

The adjacent JSON manifest contains schema version, synthetic flag, instrument, positive tick size, SHA-256, generator version and declared counts. Generated manifests also store seed, profile, requested and realized event mix, maximum capacity, price levels and live-population statistics.

Native commands verify the entire CSV hash before processing it. A manifest supplies reserved capacity but does not replace event validation. A declared event count must match a complete replay.

## Output

Successful replay writes `summary.json`, `manifest.json` and, when requested, `trace.json`. Existing output directories are rejected. Large runs leave traces disabled unless explicitly requested.

IDs, prices, quantities and timestamps are strings in JSON to preserve 64-bit values. Analytics are floating-point numbers; unavailable values are null. No NaN or infinity is emitted. Event counts are JSON integers.

The trace includes the top ten occupied levels and analytics after each accepted event. `--full-state` adds canonical orders and all occupied levels for verification; these expanded traces are not intended for the public viewer. `audit` emits full states as newline-delimited JSON for the Python checker.

The inspect command replays preceding events and requires an exact target sequence. File integrity and sequence/timestamp ordering are checked for the whole file. The CLI parses the remainder of an inspected file but does not apply later book updates.

For a trace of an inclusive timestamp range, add `--trace --trace-from-ns 1000 --trace-to-ns 5000` to replay. Events before the range establish the book state. Replay still validates the complete stream and produces its final summary; only exported frames are filtered. Equal timestamps remain in input order. A reversed range is rejected.

## Analytics

Spread is ask minus bid in ticks. Midpoint is their mean. Imbalance is bid quantity minus ask quantity divided by their sum, using either best-level quantities or each side's best five levels. Weighted midpoint weights ask by bid quantity and bid by ask quantity. Execution VWAP uses executed quantity and resting price.

All two-sided price and imbalance measures are null when either side is absent. VWAP is null until an execution occurs. Floating-point analytics are descriptive; the weighted midpoint is not a tested price forecast.
