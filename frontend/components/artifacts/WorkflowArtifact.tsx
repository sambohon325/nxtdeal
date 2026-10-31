import { WorkflowArtifact } from "@/types/artifacts";

export default function Workflow({
  artifact,
}: {
  artifact: WorkflowArtifact;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <div className="font-medium mb-4">
        {artifact.title}
      </div>

      <div className="space-y-2">
        {artifact.steps.map((step, index) => (
          <div
            key={index}
            className="bg-zinc-800 p-2 rounded"
          >
            {step}
          </div>
        ))}
      </div>
    </div>
  );
}