// Quantity typed by a Brazilian user. Kept apart from editor.js so it can be tested.
//   "1.234,56" -> 1234.56   "0,05" -> 0.05   "1500" -> 1500
//   "1.500"    -> 1500 (dot groups thousands, as in pt-BR)   "0.05", "1.5" -> decimals
// Anything else (letters, "1.23,4", "1,2,3") is NaN; empty is null.
function parseQuantity(text) {
  const t = String(text).trim().replace(/\s/g, "");
  if (!t) return null;
  if (t.includes(",")) {
    if (!/^(\d{1,3}(\.\d{3})+|\d+),\d+$/.test(t)) return NaN;
    return Number(t.replace(/\./g, "").replace(",", "."));
  }
  if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(t)) return Number(t.replace(/\./g, ""));
  if (/^\d+(\.\d+)?$/.test(t)) return Number(t);
  return NaN;
}

// How a quantity is written back into the input: no thousands dots, so editing it
// (e.g. appending a digit) can never turn 1.500 into 1,5000.
function formatQuantityInput(value) {
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 8, useGrouping: false });
}

if (typeof module !== "undefined") module.exports = { parseQuantity, formatQuantityInput };
