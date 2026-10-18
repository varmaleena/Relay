export type TranscriptTurn = {
  turnId: string;
  role: "user" | "assistant";
  text: string;
  lang: string;
  ts?: string;
};
export function isTranscriptTurn(
  value: Record<string, unknown>,
): value is Record<string, unknown> & TranscriptTurn {
  return (
    typeof value.turnId === "string" &&
    ["user", "assistant"].includes(String(value.role)) &&
    typeof value.text === "string" &&
    typeof value.lang === "string"
  );
}
