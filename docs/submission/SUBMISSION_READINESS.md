# Submission package status — 18 October 2026

Fresh hosted preflight passed after the earlier health probe failure; its
full-spec gate remains unknown. Real hosted core runs produced three VERIFIED
reports and signed PDF exports. Source guidance remains unreviewed draft content.
Voice automatic fact saving failed and stays disabled. The public results page
separates offline fixture numbers from unmeasured product quality scores.

## Organizer requirements checked today

https://aibuildercup.com/themes.html requires Google AI and deployment on Cloud
Run/GCP/Firebase, a proposal deck converted to PDF, an action video link on public
YouTube/Vimeo/Google Drive (three minutes), and English submission materials.
Judging weights listed: technical merit40%, problem/impact25%, innovation25%, UX10%.
Relay uses the BFSI theme. The page also lists unrelated social categories; use
the actual dashboard's available theme field rather than inventing a category.
The public site lists18October as the prototype deadline; the dashboard's exact
cutoff and any eligibility declarations still require the owner's review.

## Package

- Prototype: https://work-511514.web.app
- Evidence: https://work-511514.web.app/results
- Repository destination: https://github.com/varmaleena/Relay
- Deck: RELAY_DECK.pdf, six English slides; editable RELAY_DECK.pptx also provided.
- Raw actual recording: RELAY_DEMO.webm,100.88seconds, synthetic inputs only.
- Narrated/captioned recording: RELAY_DEMO_NARRATED.webm,100.83seconds, VP9/Opus,
  visible English captions and synthetic-narration disclosure.
- Public video: https://drive.google.com/file/d/1U6Ag1LrUGu6eN4uJwC-B0XncIogZwh5Y/view
- Public PDF: https://drive.google.com/file/d/16DkEH1BvfXshfo7Jm_zenFrzer9BHD9f/view

Narration is synthetic offline English speech, visibly disclosed. The recording
uses actual hosted responses and real waiting time. Neither video nor deck proves
general reliability, human legal review or official institution acceptance.

Publication review: initial509candidates, none above50MiB. Scanner matches were
a dependency SHA512 integrity string and the synthetic private-key rejection test.
Private credentials, CLI directories, temporary traces, installed dependencies
and built web assets are ignored. Publication uses a fresh clone and explicit
reviewed file paths, preserving remote history and the working checkout.

Code published to main at c47d4b5; follow-up commit includes final links
and CI formatting fixes. The narrated video is shared on Drive only, not copied
into GitHub. The public GitHub API confirmed private=false. Anonymous
downloads returned the actual WebM and the exact PDF SHA256 matching the local
deck. Drive Viewer/anyone-with-link settings were visibly saved with explicit
file-specific user approval. Human end-to-end listening review is not claimed.

The intermittent health failure was a10second probe timeout: request logs show
HTTP200 with12.768/15.629second latency, versus milliseconds when warm. Startup
CPU boost was already enabled. Preflight now has a bounded30second budget and
still rejects503/malformed responses. Its24 tests and the actual deployed check
passed. This accommodates observed cold starts; it does not claim latency improved
or the p95 target passed. No always-on instance/cost expansion was introduced.

The initial public CI run failed on two formatting-only test files. They were
formatted; full local lint and typecheck passed. Remote follow-up CI is a separate
gate whose actual outcome must be recorded, not assumed.

Remaining: owner review of portal eligibility/cutoff and actual submission. No
portal confirmation or binding declaration is fabricated. The package is a
text-first prototype with disclosed open feature/reliability/human-review gates.
