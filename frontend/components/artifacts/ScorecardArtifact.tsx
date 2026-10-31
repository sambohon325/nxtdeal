import { ScorecardArtifact } from "@/types/artifacts";

export default function Scorecard({
  artifact,
}: {
  artifact: ScorecardArtifact;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <div className="text-zinc-500 text-sm">
        {artifact.title}
      </div>

      <div className="text-5xl font-bold mt-2">
        {artifact.score}
      </div>

      <div className="text-zinc-400 mt-2">
        {artifact.status}
      </div>
    </div>
  );
}
