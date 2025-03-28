import { useState } from "react";
import ButtonGroup from "./components/ButtonGroup";
import ProgressBar from "./components/ProgressBar";
import QuestionBox from "./components/QuestionBox";
import ResultBox from "./components/ResultBox";
import "./styles/index.css";

export default function Game() {
  const [sessionId, setSessionId] = useState(null);
  const [questionId, setQuestionId] = useState(null);
  const [showIntro, setShowIntro] = useState(true);
  const [startTransition, setStartTransition] = useState(false);
  const [question, setQuestion] = useState("Is your character real?");
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);

  const handleStartGame = async () => {
    setStartTransition(true);
    setTimeout(() => {
      setStartTransition(false);
    }, 600);
  
    try {
      const res = await fetch("http://127.0.0.1:8000/api/start-game", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: "person",
          user_id: 1,
          voice_enabled: false,
          voice_language: "en"
        }),
      });
  
      const data = await res.json();
  
      if (!res.ok) {
        console.error("Start game failed:", data);
        return;
      }
  
      setSessionId(data.session_id);
  
      const qRes = await fetch(`http://127.0.0.1:8000/api/get-question/${data.session_id}`);
      const qData = await qRes.json();
      setQuestion(qData.question);
      setQuestionId(qData.question_id);  // store the question_id
      setProgress(qData.questions_asked);
  
      setShowIntro(false);
    } catch (error) {
      console.error("Network error during start game:", error);
    }
  };
  
  
  const happyGifs = ["/assets/happy1.gif", "/assets/happy2.gif"];
  const sadGifs = ["/assets/sad1.gif", "/assets/sad2.gif"];
  const notSureGifs = ["/assets/notsure1.gif", "/assets/notsure2.gif"];
  const [dogGif, setDogGif] = useState("/assets/notsure1.gif");

  const handleAnswer = async (answer) => {
    const gifList = answer === "yes" ? happyGifs : answer === "no" ? sadGifs : notSureGifs;
    setDogGif(gifList[Math.floor(Math.random() * gifList.length)]);
  
    try {
      await fetch("http://127.0.0.1:8000/api/submit-answer", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          question_id: questionId,
          answer: answer,
        }),
      });
  
      const res = await fetch(`http://127.0.0.1:8000/api/get-question/${sessionId}`);
      const data = await res.json();

      if (data.should_guess) {
        const guessRes = await fetch(`http://127.0.0.1:8000/api/make-guess/${sessionId}`);
        const guessData = await guessRes.json();
        setResult(guessData.guess);
        setIsFinished(true);
      } else {
        setQuestion(data.question);
        setQuestionId(data.question_id);
        setProgress(data.questions_asked);
      }
    } catch (error) {
      console.error("Error submitting answer:", error);
    }
  };
  

  const resetGame = () => {
    setSessionId(null);
    setQuestionId(null);
    setQuestion(null)
    setResult(null);
    setProgress(0);
    setIsFinished(false);
    setDogGif("/assets/notsure1.gif");
    handleStartGame();
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