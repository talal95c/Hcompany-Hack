import { MotionConfig, motion, useReducedMotion } from "motion/react";
import { AppIcon } from "../appIcons";
import { RioBar, StatusTag } from "../cards";
import { type TutorialRow, ago, auth, navigate, useApi } from "../lib";

const IDEAS = ["Export a scene to FBX in Blender", "Run a Docker container", "Create a smart folder in Finder"];

export function HomePage() {
  const reduced = useReducedMotion();
  const enter = (delay: number) => ({
    initial: { opacity: 0, y: reduced ? 0 : 12, filter: reduced ? "none" : "blur(6px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { duration: reduced ? 0 : 0.65, delay: reduced ? 0 : delay },
  });
  const name = auth.useSession().data?.user.name?.split(" ")[0];
  const team = useApi<{ tutorials: TutorialRow[] }>("/tutorials");
  const goal = new URLSearchParams(window.location.search).get("goal") ?? "";
  const recent = team.data?.tutorials.slice(0, 3) ?? [];

  return (
    <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 300, damping: 28 }}>
    <div className="home">
      <div className="home__atmosphere" aria-hidden="true"><span /><span /></div>
      <div className="hello">
        <h1 aria-label={`What should your team learn${name ? `, ${name}` : ""}?`}>
          {`What should your team learn${name ? `, ${name}` : ""}?`.split(" ").map((word, index) => (
            <motion.span className="home__word" key={index} aria-hidden="true" {...enter(index * 0.045)}>{word}{" "}</motion.span>
          ))}
        </h1>
      </div>
      <motion.div className="home__prompt" {...enter(0.22)}><RioBar initial={goal} key={goal} /></motion.div>
      <div className="ideas">
        {IDEAS.map((i, index) => (
          <motion.button {...enter(0.35 + index * 0.08)} whileHover={reduced ? undefined : { y: -3 }} whileTap={reduced ? undefined : { scale: 0.97 }} key={i} className="chip" onClick={() => navigate(`/home?goal=${encodeURIComponent(i)}`, true)}>
            {i}
          </motion.button>
        ))}
      </div>

      {recent.length > 0 && (
        <div className="recent">
          <div className="recent__title">Recent</div>
          {recent.map((t) => (
            <a
              key={t.id}
              className="recent__row"
              href={`/t/${t.id}`}
              onClick={(e) => {
                e.preventDefault();
                navigate(`/t/${t.id}`);
              }}
            >
              <AppIcon name={t.app} />
              <span className="recent__name">{t.tutorial?.title ?? t.title ?? t.input}</span>
              <StatusTag t={t} />
              <span className="recent__when">{ago(t.updatedAt)}</span>
            </a>
          ))}
        </div>
      )}
    </div>
    </MotionConfig>
  );
}
