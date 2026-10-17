import React, { useEffect, useRef, useState } from "react";
import Visuals from "./Visuals.jsx";
import Summary from "./Summary.jsx";

const SUGGESTIONS = [
  "Is WELL-0001 producing oil right now? When was it last inspected, and by whom?",
  "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
  "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks.",
  "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.",
  "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.",
  "Show a heatmap of 2026 spills by geographic area and month.",
];

function parseSseChunk(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() || "";
  for (const block of parts) {
    if (!block.trim()) continue;
    let event = "message";
    const dataLines = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) {
      try {
        events.push({ event, data: JSON.parse(dataLines.join("\n")) });
      } catch {
        /* ignore */
      }
    }
  }
  return { events, rest };
}

export default function App() {
  const [users, setUsers] = useState([]);
  const [userId, setUserId] = useState("U-201");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState([]);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    fetch("/users")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length) {
          setUsers(data);
          const mt = data.find((u) => /michael turner/i.test(u.name));
          if (mt) setUserId(mt.user_id);
        }
      })
      .catch(() => setUsers([]));
  }, []);

  function patchAssistant(idx, patch) {
    setMessages((m) =>
      m.map((msg, i) => (i === idx ? { ...msg, data: { ...msg.data, ...patch } } : msg))
    );
  }

  async function sendStream(text, assistantIdx) {
    const res = await fetch("/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question: text, user_id: userId }),
    });
    if (!res.ok || !res.body) throw new Error(`stream HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let streamed = "";
    let startedTokens = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseChunk(buf);
      buf = rest;
      for (const { event, data } of events) {
        if (event === "trace") {
          patchAssistant(assistantIdx, {
            trace: data.steps || [],
            facts_ms: data.facts_ms,
            cache_hit: !!data.cache_hit,
            streaming: true,
          });
        } else if (event === "facts") {
          // Show card/table/claims immediately; keep deterministic summary until tokens arrive
          patchAssistant(assistantIdx, {
            ...data,
            streaming: true,
          });
        } else if (event === "token") {
          if (data.replace && data.full != null) {
            streamed = data.full;
            startedTokens = true;
            patchAssistant(assistantIdx, { summary: streamed, streaming: true });
          } else {
            const piece = data.text || "";
            if (!startedTokens) {
              startedTokens = true;
              streamed = piece;
            } else {
              streamed += piece;
            }
            patchAssistant(assistantIdx, { summary: streamed, streaming: true });
          }
        } else if (event === "done") {
          const patch = {
            model: data.model,
            cache_hit: !!data.cache_hit,
            streaming: false,
            total_ms: data.total_ms,
            warnings: data.warnings,
          };
          if (data.summary) patch.summary = data.summary;
          patchAssistant(assistantIdx, patch);
        } else if (event === "error") {
          throw new Error(data.detail || "stream error");
        }
      }
    }
  }

  async function sendFallback(text, assistantIdx) {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, user_id: userId }),
    });
    const data = await res.json();
    patchAssistant(assistantIdx, { ...data, streaming: false });
  }

  async function send(q) {
    const text = (q ?? question).trim();
    if (!text || busy) return;
    setBusy(true);
    setQuestion("");

    const assistantIdx = messagesRef.current.length + 1; // user then assistant
    setMessages((m) => [
      ...m,
      { role: "user", text },
      {
        role: "assistant",
        data: {
          summary: "",
          claims: [],
          trace: ["Gathering grounded records…"],
          streaming: true,
          turbo: true,
        },
      },
    ]);

    try {
      await sendStream(text, assistantIdx);
    } catch (e) {
      try {
        await sendFallback(text, assistantIdx);
      } catch (e2) {
        patchAssistant(assistantIdx, {
          summary: `Request failed: ${e2.message || e.message}`,
          claims: [],
          qa: { ok: false },
          streaming: false,
        });
      }
    } finally {
      setBusy(false);
    }
  }

  const currentUser = users.find((u) => u.user_id === userId);

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="badge">Hacktoberfest 2026 · FlytBase</p>
          <h1 className="brand">AssetIQ</h1>
          <p className="thesis">The field records the facts. Gemma explains them.</p>
        </div>
        <div className="toolbar">
          <span className="turbo-pill" title="Facts first, then streaming explanation">
            Turbo
          </span>
          <label htmlFor="user">Operator</label>
          <select id="user" value={userId} onChange={(e) => setUserId(e.target.value)}>
            {users.length === 0 && <option value={userId}>{userId}</option>}
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.name} · {u.role}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="ghost"
            title="Clears this screen. Private memory for this operator stays on the server (Test 11)."
            onClick={() => setMessages([])}
          >
            New chat
          </button>
        </div>
      </header>

      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" onClick={() => send(s)} disabled={busy}>
            {s.slice(0, 48)}…
          </button>
        ))}
      </div>

      <div className="chat">
        {messages.length === 0 && (
          <div className="bubble assistant">
            <div className="meta">AssetIQ</div>
            <p>
              Ask about wells, downtime, spills, or compliance. Facts and charts land first; Gemma
              streams the explanation on top. Signed in as{" "}
              <strong>{currentUser?.name || userId}</strong> — private memory stays with this user.
            </p>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div className="bubble user" key={i}>
              <div className="meta">{currentUser?.name || userId}</div>
              <div>{m.text}</div>
            </div>
          ) : (
            <div className="bubble assistant" key={i}>
              <div className="meta">
                AssetIQ {m.data?.model ? `· ${m.data.model}` : ""}
                {m.data?.cache_hit ? " · cached" : ""}
                {typeof m.data?.facts_ms === "number" ? ` · facts ${m.data.facts_ms}ms` : ""}
                {m.data?.streaming ? " · streaming…" : ""}
              </div>
              {m.data?.trace?.length > 0 && (
                <ol className="trace">
                  {m.data.trace.map((step, j) => (
                    <li key={j}>{step}</li>
                  ))}
                </ol>
              )}
              {m.data?.summary ? (
                <Summary text={m.data.summary} visualType={m.data?.visual?.type} />
              ) : m.data?.streaming ? (
                <div>Computing…</div>
              ) : null}
              {m.data?.qa && (
                <span className={`qa-pill ${m.data.qa.ok ? "ok" : "bad"}`}>
                  QA {m.data.qa.ok ? "pass" : "flagged"} · unsupported {m.data.qa.unsupported_claims ?? 0} ·
                  missing cites {m.data.qa.evidence_missing ?? 0}
                </span>
              )}
              {m.data?.claims?.length > 0 && (
                <ul className="claims">
                  {m.data.claims.map((c, j) => (
                    <li key={j}>
                      <span className={`tag ${c.claim_type === "deterministic_fact" ? "fact" : c.claim_type}`}>
                        {c.claim_type}
                      </span>
                      {c.text}
                      {c.evidence?.length > 0 && (
                        <div style={{ fontSize: "0.8rem", color: "#5c6b5c" }}>
                          evidence: {c.evidence.filter(Boolean).join(" · ")}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <Visuals visual={m.data?.visual} />
            </div>
          )
        )}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about a well, area, spill, or rule…"
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {busy ? "Working…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
