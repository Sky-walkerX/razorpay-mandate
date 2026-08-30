/**
 * Every figure in this interface comes from a seeded corpus, not a measured
 * evaluation. That is worth saying in the chrome, permanently, rather than in
 * a footnote someone can miss.
 */
export default function TestChip() {
  return (
    <span className="testchip">
      <i />
      Test mode<span className="x"> · synthetic run</span>
    </span>
  );
}
