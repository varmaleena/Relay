# ADR0011: gated Live and reviewer integration

Date:18October2026. Status: development implementation; acceptance gates open.

The source specification proposes a separate ADK BIDI Live gateway. The current
development increment mounts the bounded Google GenAI SDK WebSocket gateway in
the existing API. It reuses the explicitly approved public HTTPS service and
verifies Firebase ID/App Check in the first frame; case ownership, origin, expiry,
session capacity and deletion remain domain guards. This is an explicit deviation
from ADK BIDI and separate-service deployment, not completion of that requirement.
No additional public service or browser model credential is introduced.

Voice stays disabled by default. A single synthetic model greeting demonstrated
project streaming access only. Real microphone/Hindi, spoken safety fidelity,
audio/transcript alignment, interruption/resumption, latency and hosted load remain
unverified. Buffered audio is not a complete speech safety guarantee. A separate
gateway remains available as a later isolation/deployment change if required.

Pack Studio uses a separate reviewer Firebase session and server availability
flags. Extraction produces unverified candidates. Publication requires a named
human decision, explicit canonical configuration and checklist; a missing canonical
draft blocks publication. This intentionally exposes the current form-authoring and
human-review gaps instead of deriving executable conditions from model output.

Main-API synthetic tests cover mounted WebSocket behavior and deletion, Studio
worker dispatch, reviewer organization denial and publication validation. These
tests establish software boundaries, not source accuracy or human usability.
