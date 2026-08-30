export default function SyntheticNote() {
  return (
    <p className="synth">
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M8 1.8 1.5 13.2h13L8 1.8Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        <path d="M8 6.2v3.1M8 11.2v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span>
        <b>Synthetic run.</b> Every figure here comes from a seeded test-mode corpus,
        not a measured evaluation. The four-arm sweep has not been run; when it is,
        this console reads from <span className="mono">results/scores.json</span> and
        nowhere else.
      </span>
    </p>
  );
}
