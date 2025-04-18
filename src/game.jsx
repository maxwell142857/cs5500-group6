import { useState } from "react";
import ButtonGroup from "./components/ButtonGroup";
import ProgressBar from "./components/ProgressBar";
import QuestionBox from "./components/QuestionBox";
import ResultBox from "./components/ResultBox";
import "./styles/index.css";

const DOMAINS = [
  { id: "person", label: "Person" },
  { id: "animal", label: "Animal" },
  { id: "movie", label: "Movie" },
  { id: "food", label: "Food" },
  { id: "country", label: "Country" }
];

export default function Game() {
  const [sessionId, setSessionId] = useState(null);
  const [questionId, setQuestionId] = useState(null);
  const [showIntro, setShowIntro] = useState(true);
  const [startTransition, setStartTransition] = useState(false);
  const [question, setQuestion] = useState(null);
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState("person");
  const [apiErrors, setApiErrors] = useState(0);
  const [shouldRetry, setShouldRetry] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [correctAnswer, setCorrectAnswer] = useState("");

  const handleStartGame = async () => {
    setStartTransition(true);
    setError(null);
    setIsLoading(true);
    setApiErrors(0);
    setShouldRetry(false);
    
    setTimeout(() => {
      setStartTransition(false);
    }, 600);
  
    try {
      const res = await fetch("http://127.0.0.1:8000/api/start-game", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: selectedDomain,
          user_id: 1
        }),
      });
  
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to start game");
      }
  
      const data = await res.json();
      setSessionId(data.session_id);
  
      await getNextQuestion(data.session_id);
      setShowIntro(false);
    } catch (error) {
      console.error("Error during game start:", error);
      setError("Unable to connect to the game server. Please make sure the backend is running and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const getNextQuestion = async (sid) => {
    try {
      const qRes = await fetch(`http://127.0.0.1:8000/api/get-question/${sid}`);
      if (!qRes.ok) {
        const errorData = await qRes.json();
        throw new Error(errorData.detail || "Failed to get question");
      }
      
      const qData = await qRes.json();
      
      // Check if we're getting emergency/fallback questions
      const emergencyPhrases = [
        "commonly used",
        "considered popular",
        "most people know about",
        "found in many countries"
      ];
      
      if (emergencyPhrases.some(phrase => qData.question?.toLowerCase().includes(phrase))) {
        setApiErrors(prev => prev + 1);
        if (apiErrors > 2) { // If we get 3 emergency questions in a row
          setShouldRetry(true);
          throw new Error("The game is currently using fallback questions. Please try again later.");
        }
      } else {
        setApiErrors(0); // Reset if we get a normal question
      }

      setQuestion(qData.question);
      setQuestionId(qData.question_id);
      setProgress(qData.questions_asked);
      return qData;
    } catch (error) {
      throw error;
    }
  };

  const happyGifs = ["/assets/happy1.gif", "/assets/happy2.gif"];
  const sadGifs = ["/assets/sad1.gif", "/assets/sad2.gif"];
  const notSureGifs = ["/assets/notsure1.gif", "/assets/notsure2.gif"];
  const [dogGif, setDogGif] = useState("/assets/notsure1.gif");

  const handleAnswer = async (answer) => {
    setError(null);
    setIsLoading(true);
    const gifList = answer === "yes" ? happyGifs : answer === "no" ? sadGifs : notSureGifs;
    setDogGif(gifList[Math.floor(Math.random() * gifList.length)]);
  
    try {
      const answerRes = await fetch("http://127.0.0.1:8000/api/submit-answer", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          question_id: questionId,
          answer: answer === "not sure" ? "maybe" : answer,
        }),
      });

      if (!answerRes.ok) {
        const errorData = await answerRes.json();
        throw new Error(errorData.detail || "Failed to submit answer");
      }

      const answerData = await answerRes.json();

      if (answerData.should_guess) {
        const guessRes = await fetch(`http://127.0.0.1:8000/api/make-guess/${sessionId}`);
        if (!guessRes.ok) {
          const errorData = await guessRes.json();
          throw new Error(errorData.detail || "Failed to make guess");
        }
        const guessData = await guessRes.json();
        setResult(guessData.guess);
        setIsFinished(true);
      } else {
        await getNextQuestion(sessionId);
      }
    } catch (error) {
      console.error("Error during answer submission:", error);
      setError(error.message || "An error occurred while processing your answer. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleGuessResult = async (wasCorrect) => {
    setIsLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/submit-result", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          was_correct: wasCorrect,
          actual_entity: correctAnswer || undefined,
          entity_type: selectedDomain
        }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to submit result");
      }

      // Start a new game
      resetGame();
    } catch (error) {
      console.error("Error submitting result:", error);
      setError("Failed to submit result. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const resetGame = () => {
    setSessionId(null);
    setQuestionId(null);
    setQuestion(null);
    setResult(null);
    setProgress(0);
    setIsFinished(false);
    setError(null);
    setDogGif("/assets/notsure1.gif");
    setShowFeedback(false);
    setCorrectAnswer("");
    setShowIntro(true);
  };

  return (
    <div className="game-container">
      {/* 🌈 Background Bubbles */}
      <div className="fun-background">
        {[...Array(20)].map((_, i) => <span key={i} />)}
      </div>

      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)} className="error-close">×</button>
        </div>
      )}

      {showIntro ? (
        <div className={`intro-screen ${startTransition ? "fade-out" : ""}`}>
          <h1 className="intro-title">🌟 Welcome to the Guessing Game!</h1>
          <div className="domain-selector">
            <p>Select what you want me to guess:</p>
            <select 
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
              className="domain-select"
              disabled={isLoading}
            >
              {DOMAINS.map(domain => (
                <option key={domain.id} value={domain.id}>
                  {domain.label}
                </option>
              ))}
            </select>
          </div>
          <p className="intro-message">
            Think of a {DOMAINS.find(d => d.id === selectedDomain)?.label.toLowerCase()} and I'll try to guess it!
          </p>
          <button 
            className="start-button" 
            onClick={handleStartGame}
            disabled={isLoading}
          >
            {isLoading ? "Starting..." : "Start Game"}
          </button>
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
                <ButtonGroup handleAnswer={handleAnswer} disabled={isLoading} />
                {isLoading && <div className="loading-overlay">Thinking...</div>}
              </>
            ) : (
              <>
                <ResultBox result={result} />
                {!showFeedback ? (
                  <div className="feedback-section">
                    <p>Was I correct?</p>
                    <div className="button-group">
                      <button 
                        className="btn green" 
                        onClick={() => handleGuessResult(true)}
                        disabled={isLoading}
                      >
                        Yes!
                      </button>
                      <button 
                        className="btn red" 
                        onClick={() => setShowFeedback(true)}
                        disabled={isLoading}
                      >
                        No
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="feedback-section">
                    <p>What was the correct answer?</p>
                    <input
                      type="text"
                      value={correctAnswer}
                      onChange={(e) => setCorrectAnswer(e.target.value)}
                      placeholder={`Enter the correct ${selectedDomain}`}
                      className="answer-input"
                    />
                    <div className="button-group">
                      <button 
                        className="btn submit-answer" 
                        onClick={() => handleGuessResult(false)}
                        disabled={!correctAnswer.trim() || isLoading}
                      >
                        Submit Answer
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {shouldRetry && (
        <div className="retry-message">
          <p>The game is currently using backup questions. This might mean:</p>
          <ul>
            <li>The AI service is temporarily unavailable</li>
            <li>The backend is experiencing connectivity issues</li>
            <li>The system is still learning about this category</li>
          </ul>
          <p>Would you like to:</p>
          <div className="button-group">
            <button 
              className="btn continue" 
              onClick={() => {
                setShouldRetry(false);
                setApiErrors(0);
              }}
            >
              Continue Anyway
            </button>
            <button 
              className="btn try-again" 
              onClick={() => {
                resetGame();
                setShowIntro(true);
              }}
            >
              Try Again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}