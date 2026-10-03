# CPU comparison — 2026-10-03

Same private five-minute English classroom excerpt. No verified reference transcript and no human listening evaluation yet. No LLM rewriting.

| Test | Whisper small / WhisperX | Parakeet TDT 0.6B v3 / ONNX FP32 | Whisper large-v3-turbo / faster-whisper int8 |
|---|---:|---:|---:|
| ASR stage | 98.3 s, includes model loading | ~99.8 s after model loading, includes chunk preparation | 245.2 s, excludes model loading |
| Model loading | Included in ASR stage | 9.9 s | 53.3 s |
| Total test | 1182.9 s, includes speaker clustering | 109.7 s, no speaker clustering | 299.2 s, speaker turns reused |
| Peak process memory | 2984 MB, whole pipeline | 2805 MB | 2177 MB |
| Timing | Forced word alignment repaired in 56.4 s; 355/355 words timed | Fixed 30-second chunk intervals, not word timing | Native estimated word timing |

These stages have slightly different scopes, so only approximate ASR speed comparisons are warranted. Pyannote speaker clustering took 1079.4 s separately and is the main observed bottleneck. Its labels remain unverified.

## Useful disagreements

- Date: Whisper small and turbo produced “24th of December”; Parakeet produced malformed “204th or all December”. Requires audio checking.
- Christmas question: Parakeet produced “Which animal carried Mary”; small produced “Which animal can marry”; turbo produced “Which animal can't marry”. Parakeet's wording is more plausible in context, but plausibility is not a reference transcript.
- Fireplace choices: small produced “Heads”; Parakeet and turbo produced “Hats”. Requires audio checking.
- Parakeet's fixed chunk boundary splits Bethlehem and repeats a fragment. Production should use VAD segmentation or checked overlap stitching instead of blind chunks.
- The turbo run had zero segments flagged by the coarse log-probability/no-speech/repetition thresholds, despite suspicious wording. Those signals cannot guarantee correctness.

## Decision for this stage

Keep all three private drafts in the account with playback seeking and TXT export. Parakeet remains a promising CPU candidate: near-small processing time and some useful recoveries; turbo is a stronger comparison baseline but did not resolve every difficult phrase and was slower. Do not select a verified production winner, claim WER, or use unreviewed text as evidence for lesson evaluation. Check disagreement intervals and then test another noisy or multilingual lesson. No paid transcription API was used.

Generated audio/results stay outside Git. The viewer requires recording ownership and marks drafts stale when the stored audio changes.
