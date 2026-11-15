"use client";
/* A small, SAFE markdown view for model answers (2026-10-20).
 *
 * The model writes "**Issue:**", "- point", "1. step" and "### Heading"; shown
 * as plain text the asterisks were visible. This turns those few forms into
 * React elements -- never HTML from the text (no innerHTML), so nothing in an
 * answer can inject markup. Anything else stays plain text. */
import { Fragment } from "react";

function inline(text, keyBase) {
    // **bold** and *italic* (2026-10-20: a closing "*This is general
    // information…*" showed its asterisks); everything else is literal.
    const out = [];
    const re = /\*\*([^*]+)\*\*|(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])/g;
    let last = 0, m, i = 0;
    while ((m = re.exec(text))) {
        if (m.index > last) out.push(text.slice(last, m.index));
        out.push(m[1] !== undefined
            ? <strong key={`${keyBase}-b${i++}`}>{m[1]}</strong>
            : <em key={`${keyBase}-i${i++}`}>{m[2]}</em>);
        last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
}

export default function RichText({ text = "" }) {
    const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let list = null;            // { ordered, items: [] }
    const flush = () => { if (list) { blocks.push(list); list = null; } };

    let table = null;           // { type: "table", rows: [[cell…]] }
    lines.forEach((raw) => {
        const line = raw.replace(/\s+$/, "");
        // A markdown table: "| a | b |" rows; the "|---|---|" rule is skipped.
        if (/^\s*\|.*\|\s*$/.test(line)) {
            flush();
            if (!table) { table = { type: "table", rows: [] }; blocks.push(table); }
            if (!/^\s*\|[\s:|-]+\|\s*$/.test(line)) table.rows.push(line.trim().slice(1, -1).split("|").map(c => c.trim()));
            return;
        }
        table = null;
        const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
        const num = /^\s*(\d{1,2})[.)]\s+(.*)$/.exec(line);
        const head = /^\s*#{1,4}\s+(.*)$/.exec(line);
        if (bullet || num) {
            const ordered = Boolean(num);
            if (!list || list.ordered !== ordered) { flush(); list = { type: "list", ordered, items: [], start: num ? Number(num[1]) : 1 }; }
            list.items.push(bullet ? bullet[1] : num[2]);
            return;
        }
        flush();
        if (head) blocks.push({ type: "head", text: head[1] });
        else if (!line.trim()) blocks.push({ type: "gap" });
        else blocks.push({ type: "p", text: line });
    });
    flush();

    return (
        <div data-rich-text style={{ whiteSpace: "normal" }}>
            {blocks.map((b, i) => {
                if (b.type === "gap") return <div key={i} style={{ height: 8 }} />;
                if (b.type === "head") return <div key={i} style={{ fontWeight: 800, margin: "6px 0 2px" }}>{inline(b.text.replace(/\*\*/g, ""), i)}</div>;
                if (b.type === "p") return <div key={i}>{inline(b.text, i)}</div>;
                if (b.type === "table") {
                    const [headRow, ...rest] = b.rows;
                    const cell = { padding: "6px 8px", borderBottom: "1px solid rgba(127,127,127,.25)", textAlign: "start", verticalAlign: "top" };
                    return (
                        <div key={i} style={{ overflowX: "auto", margin: "6px 0" }}>
                            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.95em" }}>
                                {headRow && <thead><tr>{headRow.map((c, j) => <th key={j} style={{ ...cell, fontWeight: 800 }}>{inline(c, `${i}-h${j}`)}</th>)}</tr></thead>}
                                <tbody>{rest.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j} style={cell}>{inline(c, `${i}-${k}-${j}`)}</td>)}</tr>)}</tbody>
                            </table>
                        </div>
                    );
                }
                const Tag = b.ordered ? "ol" : "ul";
                return (
                    <Tag key={i} start={b.ordered ? b.start : undefined} style={{ margin: "2px 0", paddingInlineStart: 22, listStyle: b.ordered ? "decimal" : "disc" }}>
                        {b.items.map((it, j) => <li key={j} style={{ margin: "2px 0" }}>{inline(it, `${i}-${j}`)}</li>)}
                    </Tag>
                );
            })}
        </div>
    );
}

export { Fragment };
