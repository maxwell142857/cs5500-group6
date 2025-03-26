import { useState } from "react";
import ButtonGroup from "./components/ButtonGroup";
import ProgressBar from "./components/ProgressBar";
import QuestionBox from "./components/QuestionBox";
import ResultBox from "./components/ResultBox";
import "./styles/index.css";

export default function Game() {
  const [showIntro, setShowIntro] = useState(true);
  const [startTransition, setStartTransition] = useState(false);
  const [question, setQuestion] = useState("Is your character real?");
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);

  const handleStartGame = () => {
    setStartTransition(true); // trigger fade out
    setTimeout(() => {
      setShowIntro(false); // hide intro after animation
      setStartTransition(false); // reset
    }, 600); // match fadeOut duration
  };
  const happyGifs = ["/assets/happy1.gif", "/assets/happy2.gif"];
  const sadGifs = ["/assets/sad1.gif", "/assets/sad2.gif"];
  const notSureGifs = ["/assets/notsure1.gif", "/assets/notsure2.gif"];
  const [dogGif, setDogGif] = useState("/assets/notsure1.gif");

  const handleAnswer = (answer) => {
    if (answer === "yes") {
      const random = Math.floor(Math.random() * happyGifs.length);
      setDogGif(happyGifs[random]);
    } else if (answer === "no") {
      const random = Math.floor(Math.random() * sadGifs.length);
      setDogGif(sadGifs[random]);
    } else {
      const random = Math.floor(Math.random() * notSureGifs.length);
      setDogGif(notSureGifs[random]);
    }

    if (progress >= 80) {
      setIsFinished(true);
      setResult("Your character is Sherlock Holmes! 🕵️‍♂️");
    } else {
      setProgress(progress + 20);
      setQuestion(progress === 60 ? "Is your character fictional?" : "Is your character famous?");
    }
  };

  const resetGame = () => {
    setQuestion("Is your character real?");
    setProgress(0);
    setIsFinished(false);
    setResult(null);
    setDogGif("/assets/notsure1.gif");
    setShowIntro(true); // Bring back intro screen when playing again
  };

  return (
    <div className="game-container">
      {/* 🌈 Background Bubbles */}
      <div className="fun-background">
        {[...Array(20)].map((_, i) => <span key={i} />)}
      </div>

    {showIntro ? (
      <div className={`intro-screen ${startTransition ? "fade-out" : ""}`}>
        <h1 className="intro-title">🌟 Ready to Begin the Guessing Game?</h1>
        <button className="start-button" onClick={handleStartGame}>Start Game</button>
      </div>
    ) : (
      <div className="fade-in">
          {/* 🐶 Puppy Reaction */}
          <div className="dog-container">
            <img src={dogGif} alt="Dog Reaction" className="dog-gif" />
          </div>

          {/* 🎮 Game Interface */}
          <div className="game-box">
            <ProgressBar progress={progress} />
            {!isFinished ? (
              <>
                <QuestionBox question={question} />
                <ButtonGroup handleAnswer={handleAnswer} />
              </>
            ) : (
              <>
                <ResultBox result={result} />
                <button className="btn play-again" onClick={resetGame}>🔄 Play Again</button>
              </>
            )}
          </div>
        </div>
        
      )}
    </div>
  );
}