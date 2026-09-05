import { motion, useReducedMotion } from 'motion/react';
import { CONFORMANCE } from '@/data/conformance';

const EASE = [0.22, 0.61, 0.36, 1] as const;

/**
 * The conformance suite, which had been measured and rendered nowhere.
 *
 * It is the only evidence in this project with no model and no statistics in
 * it. Containment is a stochastic score over four arms with bootstrap
 * intervals; this is seventeen deterministic scripts and a count. So it is
 * reported as a count, never a percentage, and the three figures below are the
 * whole result rather than a summary of one.
 *
 * `vacuous` is the figure worth reading and the reason the other two mean
 * anything. Every attack runs a second time against a deliberately unhardened
 * gateway, and an attack whose witness does not succeed scores nothing rather
 * than counting as a block -- a suite that stops attacks which were never
 * possible is an empty room reporting 100% containment, which this project has
 * already shipped once.
 */
export default function ConformanceBand() {
  const reduced = useReducedMotion();

  return (
    <section id="conformance" className="border-b border-rule bg-bond py-20">
      <div className="mx-auto max-w-[1220px] px-8 max-sm:px-[18px]">
        <motion.div
          className="rounded-panel border border-rule bg-sheet p-8 shadow-sheet max-sm:p-6"
          initial={reduced ? false : { opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.45, ease: EASE }}
        >
          <div className="grid items-start gap-11 lg:grid-cols-[300px_minmax(0,1fr)] lg:gap-14">

            <div>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                Conformance suite
              </span>
              <h2 className="mt-2 text-[26px] font-semibold leading-[1.14] tracking-[-0.03em] text-ink max-sm:text-[22px]">
                Seventeen attacks.
                <br />
                None got through.
              </h2>

              <div className="mt-6 flex gap-7">
                <Figure n={CONFORMANCE.blocked} label="Blocked" tone="text-pass" />
                <Figure n={CONFORMANCE.escaped} label="Escaped" />
                <Figure n={CONFORMANCE.vacuous} label="Vacuous" />
              </div>

              <div className="mt-6 inline-flex items-center gap-[7px] rounded-full border border-rule bg-bond py-[5px] pl-[10px] pr-[13px]">
                <span className="size-[5px] rounded-full bg-pass" />
                <span className="font-mono text-[11px] text-ink-2">No model · no statistics</span>
              </div>
            </div>

            <div>
              <ul className="grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                {CONFORMANCE.attacks.map((a, i) => (
                  <motion.li
                    key={a.id}
                    className="rounded-full border border-pass-line bg-pass-soft px-3 py-[5px] text-[12px] leading-[1.35] text-pass"
                    initial={reduced ? false : { opacity: 0, y: 6 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: '-40px' }}
                    transition={{ duration: 0.3, delay: reduced ? 0 : i * 0.022, ease: EASE }}
                  >
                    {a.label}
                  </motion.li>
                ))}
              </ul>

              <p className="mt-5 max-w-[660px] text-[12.5px] leading-[1.55] text-ink-2">
                <b className="text-refer">Zero vacuous is the honest number.</b> Each attack runs
                twice — once against a deliberately unhardened gateway. If that run does not
                succeed, the attack was never possible, and it scores nothing rather than counting
                as a block.
              </p>
              <p className="mt-2 max-w-[660px] text-[12.5px] leading-[1.55] text-ink-3">
                The two race attacks fire {CONFORMANCE.raceTrials} concurrent trials each. Zero
                double-spends in {CONFORMANCE.raceTrials} puts the 95% upper bound near 1.5% —
                evidence of a lock, not proof of one.
              </p>
            </div>

          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Figure({ n, label, tone = 'text-ink' }: { n: number; label: string; tone?: string }) {
  return (
    <div>
      <div className={`text-[30px] font-semibold leading-none tracking-[-0.04em] ${tone}`}>{n}</div>
      <div className="mt-[7px] font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
        {label}
      </div>
    </div>
  );
}
