export default function ResultBox({ result }) {
  return (
    <div className="result-box">
      <h2 className="result-text">🎯 I guess you were thinking of:</h2>
      <p className="result-text">{result}</p>
    </div>
  );
}