export default function ResultBox({ result }) {
  return (
    <div className="result-box">
      <h1>🎉 I guess you were thinking of:</h1>
      <h2>{result}</h2>
    </div>
  );
}