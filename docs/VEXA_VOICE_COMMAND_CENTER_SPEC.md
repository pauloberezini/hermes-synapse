# Vexa Voice Command Center

## 1. Product Goal

Vexa is the primary owner-facing interface for Hermes. It is not a second chat
screen and not a decorative "Jarvis" imitation. It is a voice-first command
center that:

- receives a spoken or typed goal;
- sends it to the root orchestrator;
- shows the current execution phase and active agents;
- speaks the final answer with a female Russian voice;
- preserves the same approvals, budgets, audit trail and kill switch as the
  existing control plane;
- keeps working locally when external providers are unavailable.

The visual identity is a calm blue holographic intelligence core. Motion must
represent state: idle, listening, transcribing, planning, executing, speaking,
degraded and offline.

## 2. Scope

### Phase 1: operational voice center

- Dedicated `Vexa` navigation section.
- Animated WebGL-free Canvas 2D core with a generated blue background plate.
- Push-to-talk and conversational listening modes.
- Existing `faster-whisper` STT endpoint.
- Existing root WebSocket command route.
- Female browser TTS fallback.
- Live answer, transcript, connection and agent state.
- Server TTS provider diagnostics.
- Responsive desktop and mobile layout.
- Reduced-motion support.

### Phase 2: fully local speech service

- Server-side Piper or RHVoice provider.
- Audio streaming instead of waiting for a complete WAV.
- Local model cache mounted outside the application image.
- Voice preview and explicit model-license acknowledgement.
- Russian pronunciation dictionary for project names, MCP tools and agent IDs.
- Echo cancellation and interruption while Vexa is speaking.

### Phase 3: hands-free mode

- Silero VAD for speech boundaries.
- `openWakeWord` model for "Vexa" activation.
- Browser-to-server streaming over a dedicated authenticated WebSocket.
- Barge-in: stop speech immediately when the owner starts talking.
- Session timeout and visible privacy indicator.

### Phase 4: autonomous command operations

- Intent classification before execution.
- Plan preview for destructive or high-risk operations.
- Direct integration with control-plane task IDs and approval queue.
- Voice confirmation for R2/R3 actions.
- UI plus physical confirmation for R4 actions.
- Spoken progress summaries without flooding the user.
- Automatic validation and a final evidence report.

## 3. Recommended Local Voice Stack

### Speech to text

Use the existing `faster-whisper` integration. It is MIT licensed, supports
Russian, VAD filtering, quantized CPU inference and CUDA. Recommended server
profiles:

| Profile | Model | Device | Compute | Use |
| --- | --- | --- | --- | --- |
| Low latency | `small` | CPU | `int8` | short commands |
| Balanced | `medium` | CUDA | `float16` | Russian conversation |
| Accuracy | `large-v3-turbo` | CUDA | `float16` | noisy room / mixed language |

Add hotwords such as `Vexa`, `Hermes`, agent names, MCP server names and project
names when upgrading the streaming recognizer.

### Text to speech

Provider order:

1. **Piper**: preferred production adapter. Local, fast and GPL-3.0 engine.
   Every selected voice model must have its own model card reviewed. The common
   `ru_RU-irina-medium` dataset license is not clearly declared, so it must not
   be downloaded silently.
2. **RHVoice**: fully local GPL-2.0 engine with strong Russian pronunciation and
   small resource use. It is less natural than neural TTS but a safe autonomous
   fallback when the selected voice package license is compatible.
3. **Silero TTS `v5_5_ru`**: best practical naturalness for Russian female
   voices such as `xenia` and `baya`, but the main public model is
   non-commercial. Enable only for a personal/non-commercial deployment after
   explicit license acceptance.
4. **Browser SpeechSynthesis**: zero-install fallback. Prefer Russian female
   voices and never block command execution when no voice is available.

Official sources:

- https://github.com/SYSTRAN/faster-whisper
- https://github.com/OHF-Voice/piper1-gpl
- https://github.com/RHVoice/RHVoice
- https://github.com/snakers4/silero-models
- https://github.com/dscripka/openWakeWord

## 4. Interaction State Machine

```text
offline
  -> ready
  -> listening
  -> transcribing
  -> planning
  -> executing
  -> speaking
  -> ready
```

Error transitions always return to `ready` after an actionable error is shown.
The microphone is never active without a persistent visual indicator.

Conversational mode starts only after a user gesture. After Vexa finishes
speaking, it may reopen the microphone. It stops automatically when:

- the user disables the mode;
- the tab loses permission;
- the network disconnects;
- a configured inactivity timeout expires;
- an R3/R4 approval is waiting;
- the kill switch is enabled.

## 5. Command Pipeline

1. Capture Opus audio in the browser with echo cancellation, noise suppression
   and automatic gain control.
2. Transcribe locally.
3. Normalize wake word and punctuation, but preserve the original transcript.
4. Send the text to the root `jarvis` orchestrator session with an opaque run ID.
5. The orchestrator creates or updates a control-plane task.
6. Specialist agents execute bounded steps.
7. Validators run tests, lint, build and domain-specific checks.
8. The orchestrator either repairs the result or requests approval.
9. Vexa shows evidence and speaks a concise final answer.
10. The project-memory service stores the plan, decisions and changed files.

## 6. Security Requirements

- No shell command may be built from voice text.
- TTS subprocesses use argument arrays, `shell=False`, input size limits and a
  hard timeout.
- Audio and transcripts use authenticated API routes.
- Temporary audio is deleted after processing.
- Hands-free mode has a visible recording indicator and a one-click stop.
- Unknown tools and dependencies remain approval-gated.
- Vexa cannot bypass control-plane risk levels.
- Spoken confirmations are insufficient for R4 operations.
- Every autonomous action records actor, task ID, risk class and evidence hash.

## 7. API Contract

### `GET /api/voice/status`

Returns STT readiness, model, language, device and TTS provider status.

### `POST /api/voice/transcribe`

Existing multipart upload. Future streaming mode uses a separate authenticated
WebSocket and does not change this endpoint.

### `GET /api/voice/tts/status`

Returns configured provider, executable/model availability, voice and fallback
information. It must never download a model.

### `POST /api/voice/synthesize`

```json
{
  "text": "Задача завершена.",
  "voice": null,
  "rate": 1.0
}
```

Returns `audio/wav`. Input is capped, sanitized only for control characters and
passed to a provider over stdin. Missing providers return `503`.

## 8. Acceptance Criteria

- Vexa is reachable from the main navigation in one click.
- The core animation stays smooth at desktop and mobile sizes and stops or
  simplifies under `prefers-reduced-motion`.
- A voice command reaches the root orchestrator and appears in the transcript.
- The same command can be typed when microphone access is unavailable.
- Vexa speaks a Russian answer with a female voice when one exists.
- Missing local TTS never breaks the response; browser fallback remains active.
- Agent activity and connection state update live.
- All controls are keyboard accessible and have visible focus.
- Frontend tests, TypeScript, ESLint and production build pass.
- Backend voice tests pass without a TTS engine installed.

## 9. Deployment Gate

Installing Piper, RHVoice, Silero or any voice model is a separate approved
operation. Before installation, record:

- exact package and version;
- source repository and checksum;
- engine license;
- voice/model license;
- disk, RAM and VRAM estimate;
- rollback command;
- whether the model may be used commercially.

