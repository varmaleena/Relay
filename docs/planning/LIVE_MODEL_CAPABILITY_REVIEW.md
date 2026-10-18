# Live model capability review

17 October 2026. Scope: current official Google documentation, installed SDK source
inspection and read-only ADC publisher catalog metadata for work-511514. The initial review made no Live connection. A subsequently authorized single
synthetic Live probe is recorded at the end; no resource/API/quota mutation,
audio recording or credential output occurred.
Only synthetic future probes are proposed. User's Gemini3.x requirement remains;
there is no silent2.5 fallback.

## Candidate and evidence strength

**Recommended probe candidate: `gemini-3.8-live`, location `us-central1`, a separate
ADC-backed enterprise/Vertex client.** This is documented and catalog-listed. The initial metadata review did not
prove streaming access; the subsequent single-connection result below proves
one basic setup/output for this project, not full gateway readiness. Do not reuse the global
text client's location or mark the browser feature available yet.

The official Cloud model page (updated16October) lists this exact identifier as GA
(released24September2026), supports Live,function calling and system instructions,
and lists model availability/PayGo in us,eu,us-central1. Its ML-processing row lists
us/eu. Input/output audio formats are16-bit little-endian PCM at16kHz/24kHz. Global
and asia-south1 are not listed. The page lists structured output and thinking as
unsupported. This establishes published capabilities, not project access or
Mumbai processing. [Cloud model specifications](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-live).

The Cloud developer guide (updated15October) demonstrates ADC,`enterprise=True`,
us-central1 and the exact model. It requires informative status/retryable/message
tool results,exact matching function-call IDs,and a prompt cap of two consecutive
tool calls. It directs omission of legacy affective/proactivity flags. The guide
also describes asynchronous tool behavior and transcription; it is not a license
to run heavy tools inside the streaming conversation. [Cloud developer guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-live).

The Gemini Developer API guide supports AUDIO modality with output transcription,
lists Hindi,and says to omit thinkingLevel for default3.8Live. Its Extended
Thinking variant is a different model/configuration. These are cross-checks only:
Developer API availability/keys are not evidence of Cloud entitlement,Cloud
residency or an appropriate substitute backend. The Cloud page's “thinking not
supported” and Developer API's “interleaved reasoning” descriptions should not be
resolved by adding a thinking setting; omit it. [Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).

Express mode is not a fallback: Google's express-mode documentation excludes the
dedicated3.8Live model. Retain full project/ADC mode rather than introducing an
API key or changing service terms. [Express-mode limitations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/express-mode/overview?hl=en).

## Actual read-only catalog result

Used existing ignored workspace ADC (`CLOUDSDK_CONFIG=.local/gcloud`) and the
existing `scripts.list_models.discover_models` implementation: SDK2.30.1,
`enterprise`/Vertex backend,publisher `query_base=True`,APIv1beta1,pageSize100,
maxPages3,15-second HTTP timeout,one HTTP attempt. No response bodies beyond
model identifiers/version/capability metadata were printed.

| Query | Pages / entries | Complete? | Exact gemini-3.8-live |
|---|---|---|---|
| us-central1 initial bounded page |1/100|No;truncated=true|Not in first page; no absence conclusion permitted|
| us-central1 bounded continuation run |2/131|Yes;truncated=false|Present: publishers/google/models/gemini-3.8-live,version default|
| global |1/30|Yes;truncated=false|Absent|

The complete us-central1 result included19 filtered Gemini3/Live entries; global
had18. All returned supportedActions,inputTokenLimit,outputTokenLimit fields for
these entries were null. The regional list also contained gemini-live-2.5-flash-native-audio;
that does not override the project's exclusion. Transcribe/Translate/TTS entries
are not a conversational-native-audio replacement. No exact3.8ExtendedThinking
entry was observed. The older PLATFORM_VERIFICATION.md global catalog result had28
entries and no3.8Live; the current30-entry global result still does not establish it.
Catalog differences can reflect serving surfaces/updates; absence is not a proof
that every possible invocation fails, while presence is not entitlement.

Reproduce metadata only (no inference):

```powershell
$env:CLOUDSDK_CONFIG = Join-Path (Get-Location) '.local/gcloud'
.venv\Scripts\python.exe scripts/list_models.py --project work-511514 --location us-central1 --page-size 100 --max-pages 3 --timeout-seconds 15
```

## Installed SDK compatibility and location separation

Local inspect-only evidence: google-genai2.30.1 `Client` accepts enterprise,
vertexai,credentials,project,location,http_options. An offline client using
AnonymousCredentials (never sent anywhere) reports default APIv1beta1. Installed
`AsyncLive.connect` uses the Cloud LlmBidiService/BidiGenerateContent WebSocket
path for project/ADC mode,reads setup_complete before yielding AsyncSession,and
accepts LiveConnectConfig. Session methods send_client_content,
send_realtime_input,send_tool_response,receive exist. No package upgrade is
required on this evidence alone.

Use an explicitly configured Live client separate from work-511514/global text
reasoning. Stored demo data/compute may remain Mumbai; this candidate's processing
must be disclosed as US/multi-region per actual selected endpoint/support. It
cannot be described as India-resident processing. Root accepted us-central1 only
as a bounded probe candidate. API version,language/tool behavior,capacity and
streaming access still require an actual connection. Current implementation's
capabilities_verified flag is a trusted runtime assertion,not an automatic test.

## Proposed one-connection probe — NOT executed

One connection only,maximum25seconds including setup/receive/cleanup,one synthetic
text input,no tools/retrieval/video/microphone,one short audio reply,zero retries
and no fallback model/location. Do not run if budget/ADC preflight fails. Keep
raw audio in memory only; count/discard bytes and never write/play it. Stop after
one complete response,512transcript characters,128server messages or128000audio
bytes,whichever comes first. Store only attempt count,model/location,setup bool,
audio/transcript presence/counts,turn-complete flag,elapsed time,bounded numeric
usage if supplied,and typed/sanitized failure code. Never print credentials,
headers,provider session ID,resumption handle,raw error or model output.

```python
# PLAN ONLY: root must separately authorize/run the one paid connection.
import asyncio
from google import genai
from google.genai import types

async def probe():
    result = dict(attempts=1, setup=False, audioBytes=0,
                  transcriptChars=0, turnComplete=False, messages=0)
    async with asyncio.timeout(25):
        client = genai.Client(
            enterprise=True, project='work-511514', location='us-central1',
            http_options=types.HttpOptions(
                api_version='v1beta1', timeout=15000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        try:
            async with client.aio.live.connect(
                model='gemini-3.8-live',
                config=types.LiveConnectConfig(
                    response_modalities=[types.Modality.AUDIO],
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    system_instruction='Reply briefly. Say only the requested greeting.',
                ),
            ) as session:
                result['setup'] = bool(session.setup_complete)
                if not result['setup']:
                    return result
                await session.send_client_content(
                    turns=types.Content(role='user', parts=[types.Part(text='Say only: Hello Relay.')]),
                    turn_complete=True,
                )
                async for message in session.receive():
                    result['messages'] += 1
                    content = message.server_content
                    if content:
                        if content.output_transcription:
                            result['transcriptChars'] += len(content.output_transcription.text or '')
                        if content.model_turn:
                            for part in content.model_turn.parts or []:
                                if part.inline_data:
                                    result['audioBytes'] += len(part.inline_data.data or b'')
                        result['turnComplete'] = bool(content.turn_complete)
                    if (result['turnComplete'] or result['messages'] >= 128
                        or result['audioBytes'] >= 128000 or result['transcriptChars'] >= 512):
                        break
        finally:
            await client.aio.aclose()
    return result
```

Wrap the snippet with root's existing sanitized diagnostics and elapsed/usage
recording before actual execution; do not print a raw exception. The byte/event
bounds stop reception,not a hard token/billing cap. No numeric rupee estimate is
asserted without dated Cloud Live pricing. One successful greeting establishes
one connection and one output only. It does not establish speech input,EN/HI
extraction parity,tool invocation,resumption,first-action spoken fidelity,audio
safety,private gateway deployment or a p95 target. Follow-up experiments need
separate bounded scope,retained failures and human review required by ADR0003.

The parent separately authorized a scoped T26A follow-up after this discovery.
Tool status/retryable/message responses and the explicit two-consecutive-tool
limit are now implemented and tested offline. No Live connection was made. Keep
voice unavailable until root integrates and verifies the actual deployed path.


## Authorized actual single-connection probe r1

Executed17October2026 after root explicitly authorized exactly one bounded
synthetic greeting connection. Existing ADC,work-511514,us-central1,enterprise
client,v1beta1,gemini-3.8-live. One connection; no retries/fallbacks; a25-second
parent-process supervisor and21-second async phase deadline plus bounded cleanup.
No microphone,tools,real user data,audio file,transcript content,credential,
provider session ID,resumption handle or raw error was persisted.

| Recorded field | Actual result |
|---|---|
| Connection attempts | 1 |
| Setup complete | True |
| Received post-setup events | 11 |
| Inline output audio bytes counted/discarded | 51842 |
| Output transcript characters counted/discarded | 12 |
| Response turn complete | True |
| Measured provider phase seconds (excludes Python imports) | 5.234 |
| Failure | None |

Reported usage: prompt15,response36,thoughts34,total85 tokens. These are the
provider fields,not a derived invoice or exact rupee charge; no token-priced cost
is invented. The thought count does not justify adding a thinking setting that
the model documentation says to omit. No cleanup timeout was reported.

Result: one authenticated ADC-backed setup and one completed synthetic text-to-
audio/transcription response passed. Audio bytes were not played or retained,so
spoken wording/semantic alignment is not established. N=1 cannot establish p95,
reliability or speech accuracy. No Hindi/audio input,tools,resumption,browser
AudioWorklet,full safety experiment,private gateway deployment or feature enable
was tested. Stop after this attempt; follow-ups need separately bounded scope.

Sanitized artifact: `.tmp/live-capability-probe-r1.json`; SHA256
`d6579b00d1762ea43cde769e68cff600a18337a885f1cf0ab96dc097daa6daa2`.
