import { useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { AppIcon } from "../appIcons";
import { RioBar, StatusTag } from "../cards";
import { type TutorialRow, ago, auth, navigate, useApi } from "../lib";

const IDEAS = [
  "Export a scene to FBX in Blender", "Run a Docker container", "Create a smart folder in Finder",
  "Build a pivot table in Excel", "Make a component in Figma", "Mask a layer in Photoshop",
  "Debug a project in VS Code", "Build a database in Notion", "Cut a sequence in Premiere",
  "Resolve a merge conflict in Git", "Animate a camera in Blender", "Create a chart in Excel",
];

export function HomePage() {
  const reduced = useReducedMotion();
  const [group, setGroup] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [chipsFocused, setChipsFocused] = useState(false);
  const [inputActive, setInputActive] = useState(false);
  useEffect(() => {
    if (hovered || chipsFocused || inputActive) return;
    const timer = window.setInterval(() => setGroup((i) => (i + 1) % (IDEAS.length / 3)), 4000);
    return () => window.clearInterval(timer);
  }, [hovered, chipsFocused, inputActive]);
  const enter = (delay: number) => ({
    initial: { opacity: 0, y: reduced ? 0 : 12, filter: "blur(6px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { type: "tween" as const, duration: 0.65, delay },
  });
  const name = auth.useSession().data?.user.name?.split(" ")[0];
  const team = useApi<{ tutorials: TutorialRow[] }>("/tutorials");
  const goal = new URLSearchParams(window.location.search).get("goal") ?? "";
  const recent = team.data?.tutorials.slice(0, 3) ?? [];

  return (
    <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 300, damping: 28 }}>
    <div className="home">
      <div className="home__atmosphere" aria-hidden="true"><span /><span /><span /></div>
      <div className="hello">
        <h1 aria-label={`What should your team learn${name ? `, ${name}` : ""}?`}>
          {`What should your team learn${name ? `, ${name}` : ""}?`.split(" ").map((word, index) => (
            <motion.span className="home__word" key={index} aria-hidden="true"
              initial={{ opacity: 0, y: reduced ? 0 : 24, filter: "blur(12px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={reduced ? { type: "tween", duration: 0.7, delay: index * 0.075 } : { type: "spring", duration: 0.7, bounce: 0.12, delay: index * 0.075 }}
            >{word}{" "}</motion.span>
          ))}
        </h1>
      </div>
      <motion.div className="home__prompt" {...enter(0.4)}><RioBar initial={goal} key={goal} onActiveChange={setInputActive} /></motion.div>
      <div className="ideas" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
        onFocus={() => setChipsFocused(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setChipsFocused(false); }}>
        {IDEAS.slice(group * 3, group * 3 + 3).map((idea, index) => (
          <motion.button layout={!reduced} {...enter(0.55 + index * 0.08)}
            transition={{ layout: { type: "spring", stiffness: 170, damping: 24, delay: reduced ? 0 : index * 0.08 } }}
            whileHover={reduced ? undefined : { y: -3 }} whileTap={reduced ? undefined : { scale: 0.97 }} key={index} className="chip" aria-label={idea} onClick={() => navigate(`/home?goal=${encodeURIComponent(idea)}`, true)}>
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span key={idea} className="home__idea-text" aria-hidden="true"
                initial={{ opacity: 0, filter: "blur(8px)", y: reduced ? 0 : 5 }}
                animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
                exit={{ opacity: 0, filter: "blur(8px)", y: reduced ? 0 : -5 }}
                transition={{ type: "tween", duration: 0.45, delay: index * 0.08 }}
              >{idea}</motion.span>
            </AnimatePresence>
          </motion.button>
        ))}
      </div>

      {recent.length > 0 && (
        <div className="recent">
          <div className="recent__title">Recent</div>
          {recent.map((t, index) => (
            <motion.a
              {...enter(0.5 + index * 0.1)}
              whileHover={reduced ? undefined : { y: -3, backgroundColor: "rgba(255,255,255,0.7)" }}
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
            </motion.a>
          ))}
        </div>
      )}
    </div>
    </MotionConfig>
  );
}
