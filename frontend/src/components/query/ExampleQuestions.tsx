import "./query.css";

const EXAMPLES = [
  "Where is authentication implemented?",
  "How are sessions invalidated?",
  "Where is the database connection created?",
  "What handles token validation?",
  "Where are API errors mapped?",
];

export function ExampleQuestions({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="examples">
      <p className="examples__label">Example questions</p>
      <div className="examples__list">
        {EXAMPLES.map((q) => (
          <button key={q} type="button" className="examples__item" onClick={() => onPick(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
