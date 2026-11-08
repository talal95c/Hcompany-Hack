import { AppIcon } from "../appIcons";
import { RioBar, StatusTag } from "../cards";
import { type TutorialRow, ago, auth, navigate, useApi } from "../lib";

const IDEAS = ["Export a scene to FBX in Blender", "Run a Docker container", "Create a smart folder in Finder"];

export function HomePage() {
  const name = auth.useSession().data?.user.name?.split(" ")[0];
  const team = useApi<{ tutorials: TutorialRow[] }>("/tutorials");
  const goal = new URLSearchParams(window.location.search).get("goal") ?? "";
  const recent = team.data?.tutorials.slice(0, 3) ?? [];

  return (
    <div className="home">
      <div className="hello">
        <h1>What should {name ? `your team learn, ${name}` : "your team learn"}?</h1>
      </div>
      <RioBar initial={goal} key={goal} />
      <div className="ideas">
        {IDEAS.map((i) => (
          <button key={i} className="chip" onClick={() => navigate(`/home?goal=${encodeURIComponent(i)}`, true)}>
            {i}
          </button>
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
  );
}
