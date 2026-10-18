# T26A Live gateway foundation

This is an injectable backend foundation. It has not contacted a Live model,
opened a real microphone, measured Hindi speech fidelity, or been deployed.
Keep the product voice action unavailable until those gates pass. No model ID or
entitlement is inferred from an installed SDK or a publisher catalog.

## Wiring contract

```python
from packages.common.auth import FirebaseIdentityVerifier
from services.live_gateway import (
    GatewayConfig,
    GoogleLiveProvider,
    LiveSessionRegistry,
    create_live_gateway,
)

# Parent runtime owns ADC client/project/region and explicitly verified Live model.
# capabilities_verified=True is a trusted configuration assertion, NOT a probe.
provider = GoogleLiveProvider(
    genai_client, configured_live_model, capabilities_verified=verified_live_capabilities
)
registry = LiveSessionRegistry(intake)
app = create_live_gateway(
    intake=intake,
    verifier=FirebaseIdentityVerifier(firebase_project_id),
    provider=provider,
    registry=registry,
    config=GatewayConfig(allowed_origins=tuple(exact_hosting_origins)),
)
```

Use the existing Firebase project for identity and the configured GenAI project for
model processing. The verifier validates both Firebase ID and App Check tokens.
Only a victim actor owning an unexpired consented case may start; there is no
header/debug token bypass, caller-provided actor, or browser model key. Origins
must match exactly. Production origins require HTTPS. Health only reports serving
liveness and performs no inference; it does not establish model readiness.

The `processing_options` factory argument is server-owned, default `{}`. It must
not silently opt an unreviewed draft into planning; an explicitly authorized demo
preview needs the same existing domain opt-in policy. Model tool arguments cannot
set this option or source='confirmed'. Confirmed facts remain protected.

Configure the ASGI server's WebSocket maximum message size to 20,000 bytes and a
bounded receive queue (for uvicorn: `--ws-max-size 20000 --ws-max-queue 16`). App
checks occur after ASGI frame delivery, so application size checks alone cannot
prevent allocation of an oversized transport frame. Disable request/payload/token
logging and configure the project's safe logging formatter. Cloud Run request
timeout must accommodate the 600-second maximum plus graceful cleanup. API IAM,
Firebase/App Check, proxy WebSocket support and model backend connectivity require
separate deployment verification; this factory does not create IAM policies.

## Browser protocol

Endpoint `wss://<gateway>/live/v1/session`. The browser cannot attach ordinary
Authorization headers to a WebSocket. Keep both tokens and resumption handles in
memory; never query strings, local storage, URL history or logs.

1. Within5s send JSON `{type:'auth',idToken,appCheckToken}`. Both nonempty tokens
   <=8192characters. Identity verification also has a bounded timeout.
2. Send `{type:'start',caseId,language:'en'|'hi',audio:{encoding:'pcm_s16le',
   sampleRateHz:16000,channels:1},resumeHandle?:opaqueHandle}` within5s after auth.
   No extra keys. Never pass a raw provider resumption handle.
3. Wait for `ready` before capture. Input is little-endian PCM16 mono at16kHz,
   binary frames640–1280bytes/even (20–40ms), at most64KB/s. The browser must
   resample actual microphone rate. `mute` stops upstream capture; already queued
   muted frames are discarded by the gateway.
4. Allowed controls: `{type:'text',text}` (1–4000characters),
   `{type:'mute',muted:boolean}`, `{type:'pong'}`, `{type:'end'}`. No client tool
   calls, arbitrary destinations, send/approval/hold actions or model parameters.

Server events:

| Type | Payload / browser action |
|---|---|
| ready | sessionId, outputAudio `{encoding:'pcm_s16le',sampleRateHz:24000,channels:1}`, limits.maxSessionSeconds<=600 |
| caption | role,user/assistant text,final:true,lang,turnId; show accessible final captions. Initial safety script is a deterministic visible caption, not proof of spoken fidelity. |
| binary | PCM16 mono24kHz output chunks<=4800bytes; AudioWorklet playback, bounded ring buffer |
| interrupted | Flush queued playback immediately |
| facts_delta | facts (canonical current fields),missingMinimum; refresh confirmed-fact UI |
| upload_requested | kind; show existing safe upload UI, not an arbitrary URL |
| processing_queued | jobId; observe existing job/case progress |
| plan_ready | planId after a scoped succeeded planning job, checked with heartbeat |
| distress_ack | level concern/urgent; pause collection and deadline pressure; show supportive text |
| session_resumption | opaque handle,expiresAt; replace memory-only handle |
| ping | Every20s; reply pong. Two missed pongs close4008. |
| error | Static code,message,retryable; no raw provider/error/credential data |
| closed | Static reason,then WebSocket close |

Close codes:1000normal,4001invalid framing/audio/control,4008heartbeat,
4401authentication,4403ownership/role/resume scope,4408session duration,
4429rate/session capacity,4500safety/tool/internal,4503upstream unavailable.
The browser may reconnect only on4503/network loss, at most3 times with backoff,
using an unexpired handle. Never reconnect on auth/safety/rate/end automatically.
A live old session cannot be forked with its resume handle. A brief reconnect race
can fail closed until the original lease releases; fall back visibly to text.

## Tools and durable boundaries

`agents/intake/live.py` exposes only record_facts,request_upload,flag_distress,
request_processing. Calls are owner-bound and bounded to300ms at the gateway;
heavy model processing stays in the worker. Tool call IDs are cached up to80 per
connection with body hashes; different-body replay is rejected. Domain planning
idempotency prevents duplicate jobs across new call IDs/reconnects. A timed-out
storage thread cannot be killed; the gateway closes rather than starting more
tools, and a permitted fact/enqueue mutation may finish afterward. There is no
approval/send/real-institution capability to finish afterward.

Facts use existing `merge_facts(...,confirmed=False)` validation; the model cannot
promote provenance or replace manually confirmed fields. Secrets are rejected
before fact persistence. Final text captions are scrubbed before durability and
indexed in the existing case transcript/event lists for normal deletion. Input
injection flags are durable; evidence/user content never grants tool permissions.
Distress pauses fact writes,uploads and planning, suppresses pending audio and
uses the existing safe emergency/trusted-person fallback. No hotline is guessed.

Leases are transactional in server-only `liveSessions/{id}` and
`liveUsers/{uidHash}`. Three active sessions per user apply across gateway
replicas. Case indexes `liveSessionRefs` and `liveResumeRefs` are written in the
same transaction before child records; each is bounded80. Resumptions are opaque
one-use tokens hashed as `liveResumptions/{hash}`; raw provider handles stay in
server-only records. They bind actor,case,language,max3 reconnects,120-second
resumption window,and original600-second/case TTL/access deadline.

**Parent integration required before enabling voice:** in the trusted case delete
transaction (including retention deletion), call:

```python
LiveSessionRegistry.cleanup_case(
    tx,
    case_id,
    {
        "sessions": case.get("liveSessionRefs", []),
        "resumptions": case.get("liveResumeRefs", []),
    },
)
```

Cleanup verifies referenced case IDs and removes user lease memberships without
exposing raw UIDs. Normal release prunes active case refs and empty user indexes.
Logical expiry strings enforce access but are NOT a configured Firestore TTL
policy; crashed orphan sessions/expired handles need case cleanup or a separately
implemented janitor. Existing client rules must continue to deny direct access to
all three top-level server-only collections. Test these rules before deployment.

## Safety and validation limits

Output audio is withheld until a complete output transcript is available and its
full text passes credential scrubbing and shared SafetyGuard. Missing transcript,
oversize audio/text,unsafe output or interruption discards the buffer. Distress
replaces normal collection text and discards normal audio. This prevents tested
unsafe transcripts from being played by this implementation; it DOES NOT prove
that native audio says exactly the transcript. Input audio reaches the model
before speech-derived secret detection; no raw audio is persisted by this code.
Partial captions are withheld pending finalization. These limitations must remain
visible in the M5 pre-play experiment and cannot be described as complete speech
DLP or a safety guarantee.

Not validated: actual configured Live model availability/backend/residency,
interruption/transcription event fidelity,Hindi speech,spoken first-action script,
audio/transcript alignment,first-reply p95<3s,300ms cloud tool latency,real browser
capture/playback/resumption,usage/cost accounting,load and deployed IAM. No shared
Settings/runtime/contracts/frontend were changed by T26A. The product voice gate
must remain false until parent integration plus measured acceptance evidence.

## Current3.8 tool-contract follow-up

After primary-source verification, the parent authorized this isolated follow-up:
all gateway tool responses include static server-owned `status`, `retryable:false`
and `message` alongside validated domain results. The prompt limits consecutive
tool calls to two. The gateway independently refuses a third tool mutation until
a safe completed assistant reply,counts every attempted tool (including refused
calls) against80/session,and returns an informative limit result rather than an
empty object. It never converts a raw provider error into model instructions.
A completed safe reply resets the consecutive counter; interrupted/unsafe output
does not. No provider inference was needed to verify these controls locally.
