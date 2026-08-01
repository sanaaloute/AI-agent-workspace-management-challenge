# Performance Review Notes
Date: 2025-03-15

Re-ran the ingest benchmarks for Project Falcon after the watermark
change: p99 dropped from 380ms to 210ms. Queue depth now stable under
the 2x load test. Next: profile the parser shim overhead.
