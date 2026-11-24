// Quantity typed by the user, in the page's language. Kept apart from editor.js so it can
// be tested with Node.
//   Portuguese: "1.234,56" -> 1234.56   "0,05" -> 0.05   "1.500" -> 1500 (dot groups
//               thousands)   "0.05", "1.5" -> decimals
//   English:    "1,234.56" -> 1234.56   "0.05" -> 0.05   "1,500" -> 1500 (comma groups
//               thousands)   "1.500" -> 1.5
// Anything else (letters, "1.23,4", "1,2,3") is NaN; empty is null.
const pageLang = () => (typeof LANG !== "undefined" ? LANG : "pt");

function parseQuantity(text, lang = pageLang()) {
  const t = String(text).trim().replace(/\s/g, "");
  if (!t) return null;
  if (lang === "en") {
    if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) return Number(t.replace(/,/g, ""));
    if (/^\d+(\.\d+)?$/.test(t)) return Number(t);
    return NaN;
  }
  if (t.includes(",")) {
    if (!/^(\d{1,3}(\.\d{3})+|\d+),\d+$/.test(t)) return NaN;
    return Number(t.replace(/\./g, "").replace(",", "."));
  }
  if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(t)) return Number(t.replace(/\./g, ""));
  if (/^\d+(\.\d+)?$/.test(t)) return Number(t);
  return NaN;
}

// How a quantity is written back into the input: no thousands separators, so editing it
// (e.g. appending a digit) can never turn 1.500 into 1,5000.
function formatQuantityInput(value, lang = pageLang()) {
  return value.toLocaleString(lang === "en" ? "en-GB" : "pt-BR", { maximumFractionDigits: 8, useGrouping: false });
}

if (typeof module !== "undefined") module.exports = { parseQuantity, formatQuantityInput };
