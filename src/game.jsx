import { useState, useEffect } from "react";

export default function Game() {
  const [question, setQuestion] = useState("Are you ready?");
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);

  // 获取第一个问题
  useEffect(() => {
    fetchQuestion();
  }, []);

  const fetchQuestion = async () => {
    try {
      const response = await fetch("/api/next-question");
      const data = await response.json();
      setQuestion(data.question);
      setProgress(data.progress);
    } catch (error) {
      console.error("Failed to fetch question", error);
    }
  };

  const handleAnswer = async (answer) => {
    try {
      const response = await fetch("/api/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      });

      const data = await response.json();

      if (data.isFinished) {
        setIsFinished(true);
        setResult(data.result);
      } else {
        setQuestion(data.question);
        setProgress(data.progress);
      }
    } catch (error) {
      console.error("Failed to submit answer", error);
    }
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100vh",
      background: "linear-gradient(to bottom, #e0f7fa, #80deea)",
      color: "#333",
      fontFamily: "Arial, sans-serif",
      textAlign: "center",
      padding: "20px"
    }}>
      {/* 进度条 */}
      <div style={{
        width: "80%",
        maxWidth: "400px",
        background: "#ddd",
        borderRadius: "10px",
        overflow: "hidden",
        boxShadow: "0px 2px 5px rgba(0, 0, 0, 0.2)",
        marginBottom: "20px"
      }}>
        <div style={{
          height: "10px",
          width: `${(progress / 20) * 100}%`,
          background: "#007bff",
          transition: "width 0.3s ease-in-out"
        }}></div>
      </div>

      {/* 显示问题 */}
      {!isFinished ? (
        <>
          <div style={{
            background: "#fff",
            padding: "20px",
            borderRadius: "10px",
            boxShadow: "0px 4px 10px rgba(0, 0, 0, 0.1)",
            maxWidth: "400px"
          }}>
            <h1 style={{ fontSize: "24px", fontWeight: "bold", marginBottom: "10px" }}>{question}</h1>
          </div>

          {/* 按钮 */}
          <div style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
            <button onClick={() => handleAnswer("yes")} style={buttonStyle("green")}>Yes</button>
            <button onClick={() => handleAnswer("no")} style={buttonStyle("red")}>No</button>
            <button onClick={() => handleAnswer("not sure")} style={buttonStyle("gray")}>Not Sure</button>
          </div>
        </>
      ) : (
        <div style={{
          background: "#fff",
          padding: "20px",
          borderRadius: "10px",
          boxShadow: "0px 4px 10px rgba(0, 0, 0, 0.1)",
          maxWidth: "400px"
        }}>
          <h1 style={{ fontSize: "26px", fontWeight: "bold", color: "#007bff" }}>🎉 I guess you were thinking of:</h1>
          <h2 style={{ fontSize: "30px", fontWeight: "bold", marginTop: "10px", color: "#28a745" }}>{result}</h2>
        </div>
      )}
    </div>
  );
}

// 按钮样式函数
const buttonStyle = (color) => ({
  padding: "10px 20px",
  fontSize: "18px",
  fontWeight: "bold",
  borderRadius: "8px",
  border: "none",
  color: "#fff",
  cursor: "pointer",
  transition: "background 0.3s ease-in-out",
  background: color === "green" ? "#28a745" : color === "red" ? "#dc3545" : "#6c757d",
  boxShadow: "0px 2px 5px rgba(0, 0, 0, 0.2)",
  outline: "none"
});

