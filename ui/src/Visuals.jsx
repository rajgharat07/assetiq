import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
} from "recharts";

const COLORS = ["#2d4a3e", "#c9a227", "#e07a5f", "#1a2e1a", "#5c6b5c"];

export default function Visuals({ visual }) {
  if (!visual || visual.type === "none" || !visual.data) return null;

  if (visual.type === "status_card") {
    const d = visual.data;
    return (
      <div className="visual">
        <h4>{visual.title || "Status"}</h4>
        <div className="status-card">
          <div className="cell">
            <div className="label">Producing</div>
            <div className="value">{d.producing ? "Yes" : "No"}</div>
          </div>
          <div className="cell">
            <div className="label">Δ wellhead</div>
            <div className="value">{d.delta_c ?? "—"} °C</div>
          </div>
          <div className="cell">
            <div className="label">Threshold</div>
            <div className="value">{d.threshold_c ?? "—"} °C</div>
          </div>
          <div className="cell">
            <div className="label">Recorded</div>
            <div className="value">{d.recorded_status ?? "—"}</div>
          </div>
          <div className="cell">
            <div className="label">Inspection</div>
            <div className="value" style={{ fontSize: "0.95rem" }}>
              {d.inspection_id ?? "—"}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (visual.type === "table") {
    const rows = Array.isArray(visual.data) ? visual.data : [];
    const cols =
      visual.columns?.length > 0
        ? visual.columns
        : rows[0]
          ? Object.keys(rows[0])
          : [];
    return (
      <div className="visual">
        <h4>{visual.title || "Table"}</h4>
        <table className="data">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c}>{String(r[c] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (visual.type === "line") {
    const rows = Array.isArray(visual.data) ? visual.data : [];
    return (
      <div className="visual">
        <h4>{visual.title || "Line chart"}</h4>
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#c5beae" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="wellhead_temp_c" name="Wellhead °C" stroke="#2d4a3e" strokeWidth={2} dot />
              <Line type="monotone" dataKey="ambient_temp_c" name="Air °C" stroke="#e07a5f" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p style={{ fontSize: "0.85rem", color: "#5c6b5c" }}>
          Not producing on:{" "}
          {rows
            .filter((r) => r.producing === false)
            .map((r) => r.date)
            .join(", ") || "none"}
        </p>
      </div>
    );
  }

  if (visual.type === "bar" || visual.type === "pie") {
    const rows = Array.isArray(visual.data) ? visual.data : [];
    const dataKey = rows[0]?.days != null ? "days" : rows[0]?.value != null ? "value" : "days";
    const nameKey = rows[0]?.well != null ? "well" : "name";
    return (
      <div className="visual">
        <h4>{visual.title || "Comparison"}</h4>
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#c5beae" />
              <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey={dataKey} name="Days">
                {rows.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (visual.type === "map") {
    const pins = Array.isArray(visual.data) ? visual.data : [];
    return (
      <div className="visual">
        <h4>{visual.title || "Map"}</h4>
        <div className="map-pins">
          {pins.map((p, i) => (
            <div key={i} className="cell" style={{ border: "1px solid #c5beae", padding: "0.4rem 0.5rem", background: "white" }}>
              <strong>{p.well}</strong> — {p.date} — {p.bbl} bbl
              <div style={{ fontSize: "0.85rem", color: "#5c6b5c" }}>
                {p.lat}, {p.lon}
              </div>
            </div>
          ))}
        </div>
        <p style={{ fontSize: "0.8rem", color: "#5c6b5c", marginTop: "0.5rem" }}>
          Pin list (lat/lon from well metadata). Full basemap polish is optional.
        </p>
      </div>
    );
  }

  if (visual.type === "heatmap") {
    const payload = visual.data || {};
    const months = payload.months || [];
    const rows = payload.rows || [];
    const monthNames = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return (
      <div className="visual">
        <h4>{visual.title || "Heatmap"}</h4>
        <table className="data">
          <thead>
            <tr>
              <th>Area</th>
              {months.map((m) => (
                <th key={m}>{monthNames[m] || m}</th>
              ))}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.area}>
                <td>{r.area}</td>
                {months.map((m) => {
                  const v = r[`m${m}`] ?? 0;
                  const bg = `rgba(45, 74, 62, ${Math.min(0.15 + v * 0.1, 0.85)})`;
                  return (
                    <td key={m} style={{ background: bg, color: v > 4 ? "#fff" : "#1a2e1a", textAlign: "center" }}>
                      {v}
                    </td>
                  );
                })}
                <td>
                  <strong>{r.total}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return null;
}
