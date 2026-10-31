export interface BaseArtifact {
  id: string;
  title: string;
  createdAt: string;
}

export interface ChartArtifact extends BaseArtifact {
  type: "chart";

  data: {
    label: string;
    value: number;
  }[];
}

export interface ScorecardArtifact extends BaseArtifact {
  type: "scorecard";

  score: number;

  status:
    | "good"
    | "warning"
    | "critical";
}

export interface WorkflowArtifact extends BaseArtifact {
  type: "workflow";

  steps: string[];
}

export interface SlideArtifact extends BaseArtifact {
  type: "slide";

  headline: string;

  content: string;
}

export type Artifact =
  | ChartArtifact
  | ScorecardArtifact
  | WorkflowArtifact
  | SlideArtifact;