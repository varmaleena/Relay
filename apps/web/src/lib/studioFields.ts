import type { Pack, PackDraft, PackDraftItem } from "../generated/contracts";

export const draftGroups = [
  "recipients",
  "deadlines",
  "liabilityRules",
  "sequencing",
  "forms",
  "crisisSupport",
] as const;
export type StudioRule = PackDraftItem & {
  group: (typeof draftGroups)[number];
};
export function studioRules(draft: PackDraft): StudioRule[] {
  return draftGroups.flatMap((group) =>
    (draft[group] || []).map((item) => ({ ...item, group })),
  );
}
export const studioFields: Record<
  string,
  Array<{ key: string; options?: string[]; kind?: "integer" | "list" }>
> = {
  recipients: [
    { key: "name" },
    {
      key: "recipientType",
      options: [
        "bank",
        "national_cyber_authority",
        "police",
        "payment_app",
        "telecom",
        "platform",
        "ombudsman",
        "reimbursement_scheme",
        "support_org",
      ],
    },
  ],
  deadlines: [
    { key: "appliesTo", kind: "list" },
    {
      key: "fromEvent",
      options: [
        "",
        "payment_timestamp",
        "discovery_timestamp",
        "report_timestamp",
      ],
    },
    { key: "duration" },
    { key: "wording" },
    { key: "obligation", options: ["mandatory", "advisory", "unclear"] },
    { key: "consequence" },
  ],
  liabilityRules: [
    { key: "summary" },
    { key: "eligibility" },
    { key: "coverage" },
    { key: "limits" },
    { key: "conditions" },
  ],
  sequencing: [
    { key: "recipientName" },
    { key: "order", kind: "integer" },
    { key: "rationale" },
    { key: "formFields", kind: "list" },
  ],
  crisisSupport: [{ key: "name" }, { key: "channel" }],
};
export function editableCandidate(item: StudioRule): boolean {
  return (
    item.body.id === item.id &&
    Array.isArray(item.body.sourceRefs) &&
    Array.isArray(item.body.evidenceSpans) &&
    !!studioFields[item.group]
  );
}
export function editedCandidate(
  item: StudioRule,
  values: Record<string, string>,
): Record<string, unknown> {
  if (!editableCandidate(item))
    throw new Error("Complete immutable source proof required");
  const body = { ...item.body };
  for (const field of studioFields[item.group])
    if (field.key in values) {
      const text = values[field.key];
      if (text.length > 2000) throw new Error("Field too long");
      if (field.options && !field.options.includes(text))
        throw new Error("Unknown structured option");
      if (field.kind === "integer") {
        if (text && !/^(?:[1-9]|[12][0-9]|30)$/.test(text))
          throw new Error("Order must be1–30");
        body[field.key] = text ? Number(text) : null;
      } else if (field.kind === "list") {
        const items = text
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
        if (items.length > 30) throw new Error("Too many list entries");
        body[field.key] = items;
      } else
        body[field.key] =
          text ||
          (field.key === "fromEvent" || field.key === "duration" ? null : "");
    }
  return body;
}
export function packDiff(
  previous: Pack,
  current: Pack,
): Array<{ field: string; before: string; after: string }> {
  return (Object.keys(current) as Array<keyof Pack>)
    .filter(
      (key) => JSON.stringify(previous[key]) !== JSON.stringify(current[key]),
    )
    .map((key) => ({
      field: key,
      before: JSON.stringify(previous[key] ?? null),
      after: JSON.stringify(current[key] ?? null),
    }));
}
