import * as validation from '../../shared/api-validation';

export interface ExperienceContext {
  company_mission: string | null;
  team_purpose: string | null;
  contribution: string | null;
  impact: string | null;
  challenges: string | null;
  learnings: string | null;
  tools: string[];
  evidence: string[];
}
export function parseExperienceContext(value: unknown): ExperienceContext {
  const row = value == null ? {} : validation.object(value);
  return {
    company_mission: validation.optionalText(row['company_mission'] ?? null),
    team_purpose: validation.optionalText(row['team_purpose'] ?? null),
    contribution: validation.optionalText(row['contribution'] ?? null),
    impact: validation.optionalText(row['impact'] ?? null),
    challenges: validation.optionalText(row['challenges'] ?? null),
    learnings: validation.optionalText(row['learnings'] ?? null),
    tools: validation.list(row['tools'] ?? [], validation.text),
    evidence: validation.list(row['evidence'] ?? [], validation.text),
  };
}
