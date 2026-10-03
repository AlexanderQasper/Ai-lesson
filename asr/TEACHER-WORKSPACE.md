# Teacher workspace first stage

Private course CRUD (create/read/edit), TXT/Markdown UTF-8 and JSON import (1 MB), JSON export, and a private topic/task bank with search and type filtering. No external catalogue integration or AI course generation is enabled yet. Imported Markdown is displayed as escaped text, not executed HTML.

Benchmark transcripts are imported explicitly with scripts/import-asr-tests.py and shown beside the existing private audio player. Timing clicks seek playback; TXT export preserves draft status. The viewer does not start ASR jobs. Recording deletion cascades to transcripts; audio changes invalidate their playback/download association.

Validation: scripts/test-teacher.py exercises disposable accounts, course import/export/edit, material creation/search, owner isolation, CSRF, HTML escaping, transcript access and stale-file handling. Use a test container with the application source mounted. It creates and removes only fixture accounts and files.
