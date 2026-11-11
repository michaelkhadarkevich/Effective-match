// Bar-Ilan "מאזן לימודים" parser for pdf.js text content (browser + node).
// The PDF's David font stores Hebrew as codes 0x9A..0xB4 (= א..ת, in cp1255 order minus 0x46);
// the bold variant also stores some punctuation by glyph id.
function maazanParse(pages) {
  const BOLD_PUNCT = { 0x06: '"', 0x0a: "'", 0x0b: "(", 0x0c: ")", 0x10: ",", 0x11: "-", 0x12: ".",
                       0x13: "/", 0x1e: ":", 0xd0: "–" };
  const HEB = /[א-ת]/;
  const LTR = /[0-9A-Za-z][0-9A-Za-z.\-/:,_]*[0-9A-Za-z]|[0-9A-Za-z]/g;
  const MIRROR = { "(": ")", ")": "(", "[": "]", "]": "[" };
  const BORDERS = [38, 72, 108, 398, 442, 509, 563];
  const COLS = ["grade", "credits", "name", "type", "code", "year"];
  const GEM = Object.fromEntries([..."אבגדהוזחטיכלמנסעפצקרשת"].map((c, i) =>
    [c, [1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,200,300,400][i]]));
  const HEADER = { "ת.לימודים": "degree", "מסלול": "track", "ש.ליעוץ": "advisory_year",
                   "רמת אנגלית": "english_level", "רמת עברית": "hebrew_level", "סטטוס": "status",
                   "שם": "name" };            // ID ("זיהוי") is deliberately never extracted
  const LABELS = new Set([...Object.keys(HEADER), "זיהוי"]);

  const decodeChar = (ch) => {
    const c = ch.charCodeAt(0);
    if (c >= 0x9a && c <= 0xb4) return String.fromCharCode(c - 0x9a + 0x5d0);
    if (BOLD_PUNCT[c] !== undefined) return BOLD_PUNCT[c];
    if (c < 0x20 || (c >= 0x80 && c < 0xa0) || c === 0xf8ff) return "";
    return ch;
  };
  const toLogical = (v) => {
    if (!HEB.test(v)) return v;
    const s = [...v].reverse().map((c) => MIRROR[c] || c).join("");
    return s.replace(LTR, (m) => [...m].reverse().join(""));
  };
  const rtlJoin = (spans) => spans.slice().sort((a, b) => b.x1 - a.x1).map((s) => s.text).join("")
    .replace(/\s+/g, " ").trim();
  const yearToGreg = (hy) => {
    const ls = [...(hy || "")].filter((c) => GEM[c]);
    return ls.length ? 5000 + ls.reduce((a, c) => a + GEM[c], 0) - 3761 : null;
  };

  const out = { meta: {}, sections: [], courses: [] };
  let section = null, inTable = false, lastRow = null, specY = null;

  // pages: [{items: textContent.items, glyphs: [{unicode, originalCharCode}] from showText ops}]
  pages.forEach(({ items, glyphs }, pageNo) => {
    // pdf.js renders code 0xA0 (= ז) as a space; recover it by aligning text chars with glyphs
    // (pdf.js may move a space into its own item, so find each item's whole char sequence in the glyph stream)
    let j = 0;
    const isWs = (c) => /\s/.test(c || "");
    const fixItem = (str) => {
      const chars = [...str];
      if (!chars.some(isWs) || chars.every(isWs)) return chars.map(decodeChar).join("");
      const same = (g, ch) => g && (g.unicode === ch || (isWs(g.unicode) && isWs(ch)));
      const from = Math.max(0, j - 40);
      for (let s = from; s <= glyphs.length - chars.length; s++) {
        if (chars.every((ch, i) => same(glyphs[s + i], ch))) {
          j = s + chars.length;
          return chars.map((ch, i) => isWs(ch) && glyphs[s + i].originalCharCode === 0xa0 ? "ז" : decodeChar(ch)).join("");
        }
      }
      return chars.map(decodeChar).join("");  // not found: keep spaces as spaces
    };
    const spans = items.filter((it) => it.str).map((it) => {
      const text = toLogical(fixItem(it.str));
      const x0 = it.transform[4];
      return { x0, x1: x0 + it.width, y: Math.round(it.transform[5]), text };
    }).filter((s) => s.text && s.x1 > s.x0);

    // group into rows (top to bottom)
    spans.sort((a, b) => b.y - a.y || b.x1 - a.x1);
    const rows = [];
    for (const s of spans) {
      const r = rows[rows.length - 1];
      if (r && Math.abs(r[0].y - s.y) <= 2) r.push(s); else rows.push([s]);
    }

    for (const row of rows) {
      const line = rtlJoin(row);
      if (!line) continue;

      if (!out.sections.length && !inTable) {
        for (const s of row) {
          const lab = s.text.trim().replace(/:$/, "").trim();
          if (HEADER[lab]) {
            const left = row.filter((v) => v.x1 <= s.x0 + 1);
            const stop = Math.max(0, ...left.filter((v) => LABELS.has(v.text.trim().replace(/:$/, "").trim()))
              .map((v) => v.x1));
            let val = left.filter((v) => v.x0 >= stop);
            if (HEADER[lab] === "name") val = val.filter((v) => v.x0 > 300);  // ID sits on the left half
            out.meta[HEADER[lab]] = rtlJoin(val);
          }
        }
        if (line.includes("התמחויות")) { specY = row[0].y; out.meta.specializations = line.split(":").slice(1).join(":").trim(); }
        else if (specY !== null && specY - row[0].y > 0 && specY - row[0].y < 12) out.meta.specializations += " " + line;
      }

      const sum = line.match(/מינ'\s*נ"ז\s*:?\s*([\d.]+).*?מקס'\s*נ"ז\s*:?\s*([\d.]+).*?שנצברו\s*:?\s*([\d.]+)/);
      if (sum && section) {
        Object.assign(section, { min_credits: +sum[1], max_credits: +sum[2], earned_credits: +sum[3] });
        continue;
      }
      const sec = line.match(/^(\d{1,8})\s*-\s*(.+)$/);
      if (sec && !row.some((s) => s.x1 <= BORDERS[2])) {
        section = { section_code: sec[1], section_name: sec[2].trim() };
        out.sections.push(section);
        continue;
      }
      if (line.startsWith("קבוצות קורס ללא שיוך")) {
        section = { section_code: "unassigned", section_name: line };
        out.sections.push(section);
        continue;
      }

      const cells = Object.fromEntries(COLS.map((c) => [c, []]));
      for (const s of row) {
        const xc = (s.x0 + s.x1) / 2;
        COLS.forEach((c, i) => { if (xc >= BORDERS[i] && xc < BORDERS[i + 1]) cells[c].push(s); });
      }
      for (const c of COLS) cells[c] = rtlJoin(cells[c]);
      // a ז at the edge of a text item can come through as a bare space; a year never ends in '"'
      if (/^[א-ת]+"$/.test(cells.year)) cells.year += "ז";

      if (cells.name === "שם" && cells.code === "קוד") { inTable = true; continue; }
      if (!inTable || !section || !COLS.some((c) => cells[c])) continue;

      if (!/^\d{4,6}(-\d{2})?$/.test(cells.code)) {
        if (out.courses.length && !cells.code && !cells.credits && lastRow &&
            lastRow.page === pageNo && lastRow.y - row[0].y > 0 && lastRow.y - row[0].y < 12) {
          const prev = out.courses[out.courses.length - 1];
          for (const c of ["name", "type"]) if (cells[c]) prev[c] = `${prev[c]} ${cells[c]}`.trim();
        }
        continue;
      }
      lastRow = { page: pageNo, y: row[0].y };
      const [base, grp] = cells.code.split("-");
      const g = cells.grade;
      out.courses.push({
        section_code: section.section_code, section_name: section.section_name,
        year_hebrew: cells.year, year: yearToGreg(cells.year), code: cells.code,
        course_id: base, group: grp || null, type: cells.type, name: cells.name,
        credits: /^[\d.]+$/.test(cells.credits) ? +cells.credits : null,
        grade_raw: g, grade: /^\d+$/.test(g) ? +g : null,
        status: g.startsWith("נ") ? "failed" : g === "עובר" ? "pass" : g === "פטור" ? "exempt"
          : /^\d+$/.test(g) ? "graded" : !cells.year ? "requirement" : "no_grade",
      });
    }
  });
  if (out.meta.name) out.meta.name = out.meta.name.replace(/\d{5,}/g, "").trim();  // never keep an ID number
  const used = new Set(out.courses.map((c) => c.section_code));
  out.sections = out.sections.filter((s) => "min_credits" in s || used.has(s.section_code));
  for (const s of out.sections) if ("min_credits" in s) s.remaining_credits = Math.max(0, s.min_credits - s.earned_credits);
  return out;
}

// One row per course: lecture/exercise/lab merged, credits summed, sorted by year.
function maazanCourseList(courses) {
  const keep = courses.filter((c) => c.status !== "requirement" && c.type !== "ש.מחלקה");
  const by = new Map();
  keep.forEach((c, i) => { if (!by.has(c.course_id)) by.set(c.course_id, { rows: [], order: i }); by.get(c.course_id).rows.push(c); });
  const list = [...by.entries()].map(([id, { rows, order }]) => {
    const lect = rows.find((r) => r.type === "הרצאה") || rows[0];
    const graded = rows.filter((r) => r.grade !== null);
    const raw = rows.map((r) => r.grade_raw).filter(Boolean);
    const years = rows.map((r) => r.year).filter(Boolean);
    return {
      course_id: id, name: lect.name,
      grade: graded.length ? String(Math.max(...graded.map((r) => r.grade))) : (raw[0] || ""),
      credits: rows.reduce((a, r) => a + (r.credits || 0), 0),
      year: rows.map((r) => r.year_hebrew).find(Boolean) || "",
      _y: years.length ? Math.min(...years) : 9999, _o: order,
    };
  });
  list.sort((a, b) => a._y - b._y || a._o - b._o);
  return list.map(({ _y, _o, ...r }) => r);
}

if (typeof module !== "undefined") module.exports = { maazanParse, maazanCourseList };
