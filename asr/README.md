# Isolated CPU benchmark

Uses stable WhisperX 3.8.6, faster-whisper, Silero VAD and pyannote community-1.
Upstream: https://github.com/m-bain/whisperX (BSD-2-Clause); https://github.com/pyannote/pyannote-audio (MIT; model has separate terms); https://github.com/snakers4/silero-vad (MIT).

1. Create a Hugging Face account and accept https://huggingface.co/pyannote/speaker-diarization-community-1 conditions.
2. Create a READ token at https://huggingface.co/settings/tokens; never paste it in chat or commit it.
3. On the remote server run ./scripts/asr-test.sh. Token input is hidden and saved in ignored .asr.env (0600). Select a numbered recording.
4. Default: 5-minute excerpt, multilingual small model, CPU int8, 2 CPU threads, 4 GiB cap. Image build and first model downloads may take a long time.
5. Optional: ./scripts/asr-test.sh --language en --start 60 --seconds 300; or --recording USER_ID/RECORDING_UUID.mp3. Mixed-language accuracy must be checked manually.
6. Output: ignored asr-results/. Model cache: ignored .asr-cache/. Segment and word timestamps are relative to the excerpt; add excerpt_start_seconds to map to the stored cropped recording.
7. Speaker labels do not identify teacher/pupils. Technical amplitude indicators are not a quality score or ASR accuracy. DNSMOS/NISQA are not implemented yet.
8. Alignment failure is explicit in JSON; diarization failure stops the run. Audio stays on the server; Hugging Face is used to download models. Telemetry disabled.

This is a benchmark, not a production queue or a transcription button. Existing website, worker and reports remain unchanged. Measure real runtime/RAM before enabling a full-lesson queue. Container dependencies/model compatibility require the first build and real smoke test.
To replace a token, remove or rename .asr.env locally and rerun the hidden prompt.
