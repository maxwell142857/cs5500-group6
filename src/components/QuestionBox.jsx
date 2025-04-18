export default function QuestionBox({ question }) {
  return (
    <div className="question-box">
      <p className="question-text">{question || "Loading question..."}</p>
    </div>
  );
}