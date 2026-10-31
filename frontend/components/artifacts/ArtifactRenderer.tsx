import {
  Artifact,
} from "@/types/artifacts";

import Scorecard from "./ScorecardArtifact";
import Workflow from "./WorkflowArtifact";

export default function ArtifactRenderer({
  artifact,
}: {
  artifact: Artifact;
}) {
  switch (artifact.type) {
    case "scorecard":
      return (
        <Scorecard
          artifact={artifact}
        />
      );

    case "workflow":
      return (
        <Workflow
          artifact={artifact}
        />
      );

    default:
      return null;
  }
}