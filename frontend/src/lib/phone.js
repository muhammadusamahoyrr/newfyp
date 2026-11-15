// Phone fields show a fixed "+92" prefix, but people still type "0300…",
// "300 1234567" or a full "+92 300…". Store one shape: "+92" followed by the
// digits only (e.g. +923001234567), the same form utils/validators.py accepts.
// Blank stays null so an optional field is not saved as just "+92".
export function toPkPhone(raw) {
  const s = String(raw ?? "").trim();
  if (!s) return null;
  let digits = s.replace(/\D/g, "");
  if (s.startsWith("+") || digits.startsWith("92")) digits = digits.replace(/^92/, "");
  digits = digits.replace(/^0+/, "");
  return digits ? `+92${digits}` : null;
}
