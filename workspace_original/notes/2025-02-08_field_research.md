# Field Research Notes
Date: 2025-02-08

Latency measurements for the Project Falcon ingest path: p50 = 41ms,
p99 = 380ms. The backpressure valve engages too early; propose raising
the queue watermark from 10k to 25k messages. See logs/server.log for
the raw deployment lines.
