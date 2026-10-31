export type CrewCard = {id: string; name: string; job: string; role: string; dept: string; rarity: string; cost: number; stats: number[]; mission?: string; move: string; lesson: string};
export type Fighter = CrewCard & {hp: number; max: number; stamina: number; cooldown: number};
export type Foe = {id: string; name: string; type: string; hp: number; max: number; power: number; story: string; dept: string; weak: number; pattern: string[]};
export type BattleState = {version: number; id: string; practice: boolean; tutorial: number; round: number; turns: number; status: string; active: number; enemy: number; team: Fighter[]; foes: Foe[]; log: string[]};
declare const engine: {
  start(cards: CrewCard[], id: string, lineup?: string[], practice?: boolean): BattleState;
  draw(id: string, rng?: () => number): Foe[];
  act(state: BattleState, action: {kind: string; index?: number}, rng?: () => number): BattleState;
  intent(state: BattleState): string;
  blocked(state: BattleState, kind: string): string | null;
  moves: Record<string, {name: string; cost: number; stat?: number}>;
  preview(state: BattleState, kind: string): {damage: number; notes: string};
  skill(card: CrewCard): string[];
  briefing(id: string, lineup: Foe[], team?: CrewCard[], practice?: boolean): {title: string; scene: string; objective: string; lesson: string; question: string; stakes: string};
};
export default engine;
