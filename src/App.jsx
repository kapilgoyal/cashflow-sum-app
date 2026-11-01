import { useState } from "react";

export default function App() {
  const [a, setA] = useState("2");
  const [b, setB] = useState("3");
  const [sum, setSum] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSum() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/sum", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ a: Number(a), b: Number(b) }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setSum(data.sum);
    } catch (err) {
      setSum(null);
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 360 }}>
      <h1>Sum</h1>
      <label>
        A{" "}
        <input
          type="number"
          value={a}
          onChange={(e) => setA(e.target.value)}
        />
      </label>
      <br />
      <label>
        B{" "}
        <input
          type="number"
          value={b}
          onChange={(e) => setB(e.target.value)}
        />
      </label>
      <br />
      <button
        type="button"
        onClick={handleSum}
        disabled={loading}
        style={{ marginTop: 12 }}
      >
        {loading ? "Adding…" : "Add"}
      </button>
      {sum !== null && <p>Sum: {sum}</p>}
      {error && <p style={{ color: "crimson" }}>Error: {error}</p>}
    </main>
  );
}
