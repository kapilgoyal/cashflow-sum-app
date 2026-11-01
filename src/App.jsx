import { useState } from "react";

export default function App() {
  const [a, setA] = useState("2");
  const [b, setB] = useState("3");
  const [sum, setSum] = useState(null);

  function handleSum() {
    setSum(Number(a) + Number(b));
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
      <button type="button" onClick={handleSum} style={{ marginTop: 12 }}>
        Add
      </button>
      {sum !== null && <p>Sum: {sum}</p>}
    </main>
  );
}
