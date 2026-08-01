# Project Falcon — Status Update
Date: 2025-01-14

Schema freeze is done (one week late). Ingest workers are at 60%.
Risk flagged: the old CRM export job still emits CSV v1, which breaks
the new parser. Decision: keep a compatibility shim until 2025-03-01.
