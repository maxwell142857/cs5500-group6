export default function ButtonGroup({ handleAnswer }) {
    return (
      <div className="button-group">
        <button className="btn green" onClick={() => handleAnswer("yes")}>Yes</button>
        <button className="btn red" onClick={() => handleAnswer("no")}>No</button>
        <button className="btn gray" onClick={() => handleAnswer("not sure")}>Not Sure</button>
      </div>
    );
  }
  