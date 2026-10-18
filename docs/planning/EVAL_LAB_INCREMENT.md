# Read-only Evaluation Lab increment

18 October 2026. S10/T37 component increment; remaining T35/T36 evaluation gates
are recorded in eval/DATASET_CARD.md. This is a reviewer/judge surface, separate
from the victim's report journey.

EvalLab receives an exported typed EvalReport DTO through props. It performs no
network requests, authentication bypass, provider calls or background execution.
Parent integration owns the route, authorized read endpoint and report loading.
The five product-system columns remain visible with Not measured when evidence
is absent. A canned calculator fixture has its own labeled column and a prominent
notice that it is not measured Relay, baseline or ablation performance.

Measured numeric cells require a finite value, positive integer n and valid
finite 95% interval bounds. Unknown usage/timing/check counts remain visible.
Dataset/build/date identifiers, per-system model/prompt/config details, slices,
sanitized failure categories, limitation text and JSON/Markdown exports are
available. Export projection discards hidden undeclared case fields. Gallery
entries are restricted to synthetic case IDs and fixed safe failure categories;
no raw transcript/provider response is displayed. This does not implement the
full expected/actual raw-input inspection or free-text paired judging workflow.

No run button exists by default. A parent may explicitly inject a bounded
20-case Relay-only executor and an admin state; then a confirmation binds the
request to the displayed dataset hash. Concurrent clicks are locked, mutations
are not automatically retried, a changed report disables stale confirmation,
and accepted requests leave the existing metrics unchanged. These component
checks do not replace server-side admin authorization or prove an actual E40
executor/deployed Cloud Run Job exists. Parent should supply no executor until
those requirements and budget limits are implemented.

Validation: 18 browser checks passed across desktop/mobile, including English
and Hindi axe scans, overflow, labeling, absent confidence evidence, unknowns,
filtering, safe exports, confirmation/version races and no retry. The initial
shared5173 preview was unavailable; checks ran on a separate local5181 Vite
instance. TypeScript, locale/content3 and formatting passed. A small final CSS
correction uses the existing design-system border token and readable white
panels; final desktop/mobile English/Hindi axe/layout checks were repeated.
Screenshots are under .tmp/ui-review/eval-*.png. These are mocked component
checks and automated accessibility checks; no human usability, screen-reader
review, Hindi sign-off or actual product/model evaluation was performed.

User/judge gate: users can inspect what was actually measured and what remains
unknown without treating calculator fixtures as product proof. This supports
transparent technical evidence; it does not close the official innovation,
impact or comparative model-quality gates. Parent integration and actual
captured model/baseline/ablation results remain separate work.
