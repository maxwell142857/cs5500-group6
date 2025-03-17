import { useState } from "react";
import QuestionBox from "./components/QuestionBox";
import ProgressBar from "./components/ProgressBar";
import ResultBox from "./components/ResultBox";
import ButtonGroup from "./components/ButtonGroup";

export default function Game() {
  const [question, setQuestion] = useState("Is your character real?");
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);

  // Simulated game logic
  const handleAnswer = (answer) => {
    console.log(`User answered: ${answer}`);
    if (progress >= 80) {
      setIsFinished(true);
      setResult("Your character is Sherlock Holmes! 🕵️‍♂️");
    } else {
      setProgress(progress + 20);
      setQuestion(progress === 60 ? "Is your character fictional?" : "Is your character famous?");
    }
  };

  return (
    <div className="game-container">
      <ProgressBar progress={progress} />
      {!isFinished ? (
        <>
          <QuestionBox question={question} />
          <ButtonGroup handleAnswer={handleAnswer} />
        </>
      ) : (
        <ResultBox result={result} />
      )}
    </div>
  );
}
