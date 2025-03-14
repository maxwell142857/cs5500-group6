import { useState, useEffect } from "react";

export default function Game() {
  const [question, setQuestion] = useState("Are you ready");
  const [progress, setProgress] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [result, setResult] = useState(null);

  // 获取第一个问题
  useEffect(() => {
    fetchQuestion();
  }, []);

  const fetchQuestion = async () => {
    try {
      const response = await fetch("/api/next-question"); // 请求后端
      const data = await response.json();
      setQuestion(data.question);
      setProgress(data.progress);
    } catch (error) {
      console.error("获取问题失败", error);
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
      console.error("提交回答失败", error);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-screen space-y-6">
      {/* 进度条 */}
      <div className="w-64 bg-gray-200 h-2 rounded">
        <div className="bg-blue-500 h-full rounded" style={{ width: `${(progress / 20) * 100}%` }} />
      </div>

      {/* 显示问题 */}
      {!isFinished ? (
        <>
          <h1 className="text-2xl font-bold">{question}</h1>
          <div className="flex space-x-4">
            <button className="px-4 py-2 bg-green-500 text-white rounded" onClick={() => handleAnswer("yes")}>Yes</button>
            <button className="px-4 py-2 bg-red-500 text-white rounded" onClick={() => handleAnswer("no")}>No</button>
            <button className="px-4 py-2 bg-gray-500 text-white rounded" onClick={() => handleAnswer("not sure")}>Not Sure</button>
          </div>
        </>
      ) : (
        <h1 className="text-2xl font-bold">我猜你在想：{result} 🎉</h1>
      )}
    </div>
  );
}
