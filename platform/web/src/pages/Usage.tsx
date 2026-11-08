import { useMemo, useState } from "react";
import { navigate, useApi } from "../lib";
import { Head, Loading } from "../ui";

type Usage = {
  days: number;
  totals: { kind: string; n: number; empty: number }[];
  daily: { day: number; kind: string; n: number }[];
  queries: { query: string; n: number }[];
  gaps: { query: string; app: string | null; n: number; last: number }[];
  tutorials: { id: string; title: string | null; started: number; finished: number; skipped: number }[];
  skipped: { title: string | null; milestone: string | null; n: number }[];
};

const RANGES = [7, 30, 90];
const fmt = new Intl.NumberFormat("en");
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "—");

export function UsagePage() {
  const [days, setDays] = useState(30);
  const { data, error } = useApi<Usage>(`/usage?days=${days}`);
  const total = (k: string) => data?.totals.find((t) => t.kind === k)?.n ?? 0;
  const searches = total("search");
  const unanswered = data?.totals.find((t) => t.kind === "search")?.empty ?? 0;
  const started = total("tutorial_started");
  const finished = total("tutorial_finished");

  return (
    <>
      <Head title="Usage" sub="How your team learns with Rio, and what it could not answer.">
        <div className="seg" role="group" aria-label="Time range">
          {RANGES.map((d) => (
            <button key={d} className={d === days ? "is-on" : ""} onClick={() => setDays(d)} aria-pressed={d === days}>
              {d} days
            </button>
          ))}
        </div>
      </Head>
      {error ? (
        <div className="error">{error}</div>
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <div className="tiles">
            <Tile label="Questions asked" value={fmt.format(searches)} sub="Searches from Rio" />
            <Tile label="Unanswered" value={pct(unanswered, searches)} sub={`${fmt.format(unanswered)} with nothing in your knowledge`} />
            <Tile label="Tutorials started" value={fmt.format(started)} sub={`${fmt.format(total("milestone_done"))} milestones reached`} />
            <Tile label="Completion" value={pct(finished, started)} sub={`${fmt.format(finished)} finished`} />
          </div>
          <div className="charts">
            <Bars title="Questions per day" kind="search" usage={data} />
            <Bars title="Tutorials started per day" kind="tutorial_started" usage={data} />
          </div>

          <div className="grid2 section">
            <div>
              <div className="section__title">
                <h2>Knowledge gaps</h2>
                <span>Questions nothing answered</span>
              </div>
              {data.gaps.length ? (
                <table className="table">
                  <tbody>
                    {data.gaps.map((g) => (
                      <tr key={g.query}>
                        <td>
                          {g.query}
                          {g.app && <span className="faint"> · in {g.app}</span>}
                        </td>
                        <td className="num dim">{g.n}×</td>
                        <td className="actions">
                          <button className="btn btn--sm" onClick={() => navigate(`/home?goal=${encodeURIComponent(g.query)}`)}>
                            Create tutorial
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty">
                  <b>No gaps</b>Every question found an answer.
                </div>
              )}
            </div>
            <div>
              <div className="section__title">
                <h2>Top questions</h2>
              </div>
              {data.queries.length ? (
                <table className="table">
                  <tbody>
                    {data.queries.map((q) => (
                      <tr key={q.query}>
                        <td>{q.query}</td>
                        <td className="num dim">{q.n}×</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty">
                  <b>No questions yet</b>Questions asked in Rio appear here.
                </div>
              )}
            </div>
          </div>

          <div className="grid2 section">
            <div>
              <div className="section__title">
                <h2>Tutorials</h2>
              </div>
              {data.tutorials.length ? (
                <table className="table table--cards">
                  <thead>
                    <tr>
                      <th>Tutorial</th>
                      <th className="num">Started</th>
                      <th className="num">Finished</th>
                      <th className="num">Skips</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tutorials.map((t) => (
                      <tr key={t.id}>
                        <td>{t.title ?? t.id}</td>
                        <td className="num" data-label="Started">{t.started}</td>
                        <td className="num" data-label="Finished">{t.finished}</td>
                        <td className="num dim" data-label="Skips">{t.skipped}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty">
                  <b>No tutorial runs yet</b>Runs started in Rio appear here.
                </div>
              )}
            </div>
            <div>
              <div className="section__title">
                <h2>Where people get stuck</h2>
                <span>Most skipped milestones</span>
              </div>
              {data.skipped.length ? (
                <table className="table">
                  <tbody>
                    {data.skipped.map((s, i) => (
                      <tr key={i}>
                        <td>
                          <div className="cell-title">
                            <div style={{ minWidth: 0 }}>
                              <b>{s.milestone ?? "—"}</b>
                              <span>{s.title}</span>
                            </div>
                          </div>
                        </td>
                        <td className="num dim">{s.n}×</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty">
                  <b>Nobody skipped a milestone</b>Skipped milestones show where a tutorial needs work.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="tile">
      <div className="tile__label">{label}</div>
      <div className="tile__value">{value}</div>
      <div className="tile__sub">{sub}</div>
    </div>
  );
}

const DAY = 86_400_000;
const dayLabel = (d: number) => new Date(d * DAY).toLocaleDateString("en", { month: "short", day: "numeric" });

/** One series, one hue: thin bars from a single baseline, hover for the exact value. */
function Bars({ title, kind, usage }: { title: string; kind: string; usage: Usage }) {
  const [hover, setHover] = useState<number | null>(null);
  const series = useMemo(() => {
    const today = Math.floor(Date.now() / DAY);
    const counts = new Map(usage.daily.filter((d) => d.kind === kind).map((d) => [d.day, d.n]));
    return Array.from({ length: usage.days }, (_, i) => {
      const day = today - usage.days + 1 + i;
      return { day, n: counts.get(day) ?? 0 };
    });
  }, [usage, kind]);
  const max = Math.max(1, ...series.map((s) => s.n));
  const total = series.reduce((a, s) => a + s.n, 0);

  const W = 480;
  const H = 150;
  const top = 8;
  const bottom = 22;
  const left = 26;
  const plotH = H - top - bottom;
  const band = (W - left) / series.length;
  const bar = Math.min(24, Math.max(2, band - 2)); // capped thickness, 2px air between bars
  const y = (n: number) => top + plotH - (n / max) * plotH;
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);

  return (
    <div className="chart">
      <div className="chart__title">
        <b>{title}</b> · {fmt.format(total)} in {usage.days} days
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${title}: ${total} over ${usage.days} days`} onMouseLeave={() => setHover(null)}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={left} x2={W} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((t) => (
            <text key={t} x={left - 6} y={y(t) + 3.5} textAnchor="end">
              {t}
            </text>
          ))}
          {[0, Math.floor(series.length / 2), series.length - 1].map((i) => (
            <text key={i} x={left + band * i + band / 2} y={H - 6} textAnchor="middle">
              {dayLabel(series[i]!.day)}
            </text>
          ))}
        </g>
        {series.map((s, i) => {
          const x = left + band * i + (band - bar) / 2;
          const h = Math.max(0, y(0) - y(s.n));
          const r = Math.min(4, bar / 2, h);
          return (
            <g key={s.day} onMouseEnter={() => setHover(i)}>
              <rect className="hit" x={left + band * i} y={top} width={band} height={plotH} />
              {s.n > 0 && (
                <path
                  className={`bar ${hover === i ? "is-hover" : ""}`}
                  // rounded data-end, square at the baseline
                  d={`M${x},${y(0)} V${y(s.n) + r} Q${x},${y(s.n)} ${x + r},${y(s.n)} H${x + bar - r} Q${x + bar},${y(s.n)} ${x + bar},${y(s.n) + r} V${y(0)} Z`}
                />
              )}
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: `${((left + band * hover + band / 2) / W) * 100}%`, top: `${((y(series[hover]!.n) + 36) / H) * 150}px` }}>
          {dayLabel(series[hover]!.day)} · <b>{series[hover]!.n}</b>
        </div>
      )}
      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>
          {series.map((s) => (
            <tr key={s.day}>
              <th>{dayLabel(s.day)}</th>
              <td>{s.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
