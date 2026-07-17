export const OFFICE_TILE_SIZE = 16;
export const OFFICE_LAYOUT_STORAGE_KEY = 'hermes_canvas_office_layout_v2';

export type CanvasAgentStatus = 'working' | 'waiting' | 'error' | 'paused' | 'offline';
export type CanvasCharacterState = 'idle' | 'walk' | 'type' | 'read' | 'rest';
export type CanvasDirection = 'down' | 'left' | 'right' | 'up';
export type FurnitureKind = keyof typeof FURNITURE_CATALOG;
export type CanvasLifecycle = 'entering' | 'active' | 'leaving';
export type CanvasSpeechKind = 'info' | 'success' | 'error';

export interface CanvasSpeech {
  text: string;
  kind: CanvasSpeechKind;
  until: number;
}

export interface CanvasLiveTrace {
  agent: string;
  action: string;
  message: string;
  status?: string;
}

/** Keyword → specialist persona, mirroring the routing table from Claude-Office (bilingual). */
const SPECIALIST_RULES: Array<[RegExp, string]> = [
  [/debug|crash|traceback|exception|ошибк|баг|исключен|падени/i, 'Debugger'],
  [/review|pull request|\bpr\b|\bgit\b|commit|merge|ревью|коммит/i, 'Reviewer'],
  [/\bui\b|\bcss\b|design|layout|render|интерфейс|дизайн|вёрстк|верстк/i, 'Frontend'],
  [/\btest|coverage|\be2e\b|pytest|vitest|тест|покрыти/i, 'Tester'],
  [/auth|security|token|secret|credential|безопасн|авториз|секрет/i, 'Security'],
  [/deploy|docker|\bci\b|pipeline|container|деплой|контейнер|сборк/i, 'DevOps'],
  [/perf|latency|cache|optimi|profil|производит|кэш|оптимиз/i, 'PerfEng'],
  [/\bsql\b|database|sqlite|qdrant|\bdb\b|\bбд\b|база данных|запрос к базе/i, 'DBA'],
  [/search|research|analy|index|scrape|изуч|поиск|анализ|исследов|индекс/i, 'Researcher'],
  [/\bllm\b|prompt|embedding|inference|ollama|промпт|модел|инференс/i, 'AI Eng'],
  [/\bapi\b|rest|webhook|endpoint|request|интеграц|запрос/i, 'Fullstack'],
  [/architect|pattern|refactor|structure|архитектур|рефактор|структур/i, 'Architect'],
];

export function inferSpecialist(...parts: Array<string | undefined | null>): string | null {
  const haystack = parts.filter(Boolean).join(' ');
  if (!haystack.trim()) return null;
  for (const [pattern, role] of SPECIALIST_RULES) if (pattern.test(haystack)) return role;
  return null;
}

export interface CanvasAgentData {
  id: string;
  name: string;
  statusKind: CanvasAgentStatus;
  current_task?: string;
  last_action?: string;
  parent_id?: string | null;
}

export interface PlacedFurniture {
  id: string;
  kind: FurnitureKind;
  col: number;
  row: number;
}

export interface CanvasOfficeLayout {
  version: 1;
  cols: number;
  rows: number;
  tiles: number[];
  furniture: PlacedFurniture[];
}

interface FurnitureSpec {
  label: string;
  src: string;
  width: number;
  height: number;
  footprintW: number;
  footprintH: number;
  blocks: boolean;
  seat?: 'work' | 'lounge';
  electronics?: boolean;
  animated?: string[];
}

const ASSET_ROOT = '/pixel-agents-assets/furniture';

export const FURNITURE_CATALOG = {
  DESK_FRONT: { label: 'Desk', src: `${ASSET_ROOT}/DESK/DESK_FRONT.png`, width: 48, height: 32, footprintW: 3, footprintH: 2, blocks: true },
  PC_FRONT_OFF: { label: 'Computer', src: `${ASSET_ROOT}/PC/PC_FRONT_OFF.png`, width: 16, height: 32, footprintW: 1, footprintH: 2, blocks: false, electronics: true, animated: [`${ASSET_ROOT}/PC/PC_FRONT_ON_1.png`, `${ASSET_ROOT}/PC/PC_FRONT_ON_2.png`, `${ASSET_ROOT}/PC/PC_FRONT_ON_3.png`] },
  CUSHIONED_CHAIR_BACK: { label: 'Office chair', src: `${ASSET_ROOT}/CUSHIONED_CHAIR/CUSHIONED_CHAIR_BACK.png`, width: 16, height: 16, footprintW: 1, footprintH: 1, blocks: false, seat: 'work' },
  DOUBLE_BOOKSHELF: { label: 'Bookshelf', src: `${ASSET_ROOT}/DOUBLE_BOOKSHELF/DOUBLE_BOOKSHELF.png`, width: 32, height: 32, footprintW: 2, footprintH: 2, blocks: true },
  SOFA_FRONT: { label: 'Sofa', src: `${ASSET_ROOT}/SOFA/SOFA_FRONT.png`, width: 32, height: 16, footprintW: 2, footprintH: 1, blocks: true },
  COFFEE_TABLE: { label: 'Coffee table', src: `${ASSET_ROOT}/COFFEE_TABLE/COFFEE_TABLE.png`, width: 32, height: 32, footprintW: 2, footprintH: 2, blocks: true },
  WHITEBOARD: { label: 'Whiteboard', src: `${ASSET_ROOT}/WHITEBOARD/WHITEBOARD.png`, width: 32, height: 32, footprintW: 2, footprintH: 2, blocks: false },
  PLANT: { label: 'Plant', src: `${ASSET_ROOT}/PLANT/PLANT.png`, width: 16, height: 32, footprintW: 1, footprintH: 2, blocks: true },
  LARGE_PLANT: { label: 'Large plant', src: `${ASSET_ROOT}/LARGE_PLANT/LARGE_PLANT.png`, width: 32, height: 48, footprintW: 2, footprintH: 3, blocks: true },
  CLOCK: { label: 'Clock', src: `${ASSET_ROOT}/CLOCK/CLOCK.png`, width: 16, height: 32, footprintW: 1, footprintH: 2, blocks: false },
  CUSHIONED_BENCH: { label: 'Bench', src: `${ASSET_ROOT}/CUSHIONED_BENCH/CUSHIONED_BENCH.png`, width: 16, height: 16, footprintW: 1, footprintH: 1, blocks: false, seat: 'lounge' },
  SMALL_PAINTING: { label: 'Painting', src: `${ASSET_ROOT}/SMALL_PAINTING/SMALL_PAINTING.png`, width: 16, height: 32, footprintW: 1, footprintH: 2, blocks: false },
} as const satisfies Record<string, FurnitureSpec>;

export interface CanvasCharacter {
  agent: CanvasAgentData;
  col: number;
  row: number;
  x: number;
  y: number;
  direction: CanvasDirection;
  state: CanvasCharacterState;
  path: Array<{ col: number; row: number }>;
  frame: number;
  frameTimer: number;
  palette: number;
  seat: { col: number; row: number; purpose: 'work' | 'lounge' } | null;
  wanderTimer: number;
  spawnTimer: number;
  lifecycle: CanvasLifecycle;
  speech: CanvasSpeech | null;
  specialist: string | null;
  activeUntil: number;
  removeAt: number | null;
}

function hashString(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

function tileKey(col: number, row: number) {
  return `${col},${row}`;
}

export function cloneOfficeLayout(layout: CanvasOfficeLayout): CanvasOfficeLayout {
  return { ...layout, tiles: [...layout.tiles], furniture: layout.furniture.map(item => ({ ...item })) };
}

export function createDefaultCanvasLayout(): CanvasOfficeLayout {
  const cols = 28;
  const rows = 22;
  const tiles = Array.from({ length: cols * rows }, (_, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    if (col === 0 || row === 0 || col === cols - 1 || row === rows - 1) return 0;
    const horizontalWall = row === 11 && ![5, 6, 15, 16, 22, 23].includes(col);
    const upperDivider = col === 18 && row < 11 && ![8, 9].includes(row);
    const lowerDivider = col === 18 && row > 11 && ![13, 14].includes(row);
    if (horizontalWall || upperDivider || lowerDivider) return 0;
    if (col >= 18 && row >= 11) return 4;
    if (col >= 18) return 2;
    if (row >= 11) return 7;
    return 1;
  });
  const furniture: PlacedFurniture[] = [];
  const place = (kind: FurnitureKind, col: number, row: number) => furniture.push({ id: `default-${furniture.length}`, kind, col, row });

  place('DOUBLE_BOOKSHELF', 3, 1); place('DOUBLE_BOOKSHELF', 7, 1); place('CLOCK', 11, 1); place('WHITEBOARD', 19, 1); place('SMALL_PAINTING', 24, 1);
  place('PLANT', 1, 3); place('LARGE_PLANT', 25, 3); place('PLANT', 16, 8); place('PLANT', 1, 17); place('PLANT', 25, 18);

  [[2, 4], [7, 4], [12, 4], [2, 12], [7, 12], [12, 12]].forEach(([col, row]) => {
    place('DESK_FRONT', col, row); place('PC_FRONT_OFF', col + 1, row); place('CUSHIONED_CHAIR_BACK', col + 1, row + 2);
  });

  place('COFFEE_TABLE', 21, 6); place('CUSHIONED_BENCH', 20, 6); place('CUSHIONED_BENCH', 23, 6); place('CUSHIONED_BENCH', 21, 8); place('CUSHIONED_BENCH', 22, 8);
  place('SOFA_FRONT', 19, 14); place('SOFA_FRONT', 23, 14); place('COFFEE_TABLE', 21, 16);
  [[19, 18], [20, 18], [21, 19], [22, 19], [23, 18], [24, 18]].forEach(([col, row]) => place('CUSHIONED_BENCH', col, row));
  return { version: 1, cols, rows, tiles, furniture };
}

export function normalizeCanvasLayout(value: unknown): CanvasOfficeLayout {
  if (!value || typeof value !== 'object') return createDefaultCanvasLayout();
  const candidate = value as Partial<CanvasOfficeLayout>;
  const cols = Math.max(12, Math.min(64, Number(candidate.cols) || 28));
  const rows = Math.max(10, Math.min(64, Number(candidate.rows) || 18));
  if (!Array.isArray(candidate.tiles) || candidate.tiles.length !== cols * rows) return createDefaultCanvasLayout();
  const furniture = Array.isArray(candidate.furniture) ? candidate.furniture.filter((item): item is PlacedFurniture => {
    if (!item || !FURNITURE_CATALOG[item.kind as FurnitureKind] || !Number.isInteger(item.col) || !Number.isInteger(item.row)) return false;
    const spec = FURNITURE_CATALOG[item.kind as FurnitureKind];
    return item.col >= 0 && item.row >= 0 && item.col + spec.footprintW <= cols && item.row + spec.footprintH <= rows;
  }) : [];
  return { version: 1, cols, rows, tiles: candidate.tiles.map(tile => Math.max(0, Math.min(9, Number(tile) || 0))), furniture };
}

export function getBlockedTiles(layout: CanvasOfficeLayout) {
  const blocked = new Set<string>();
  layout.tiles.forEach((tile, index) => {
    if (tile === 0) blocked.add(tileKey(index % layout.cols, Math.floor(index / layout.cols)));
  });
  layout.furniture.forEach(item => {
    const spec = FURNITURE_CATALOG[item.kind];
    if (!spec.blocks) return;
    for (let row = 0; row < spec.footprintH; row += 1) for (let col = 0; col < spec.footprintW; col += 1) blocked.add(tileKey(item.col + col, item.row + row));
  });
  return blocked;
}

export function getWallMask(layout: CanvasOfficeLayout, col: number, row: number) {
  let mask = 0;
  const isWall = (nextCol: number, nextRow: number) => nextCol >= 0 && nextRow >= 0 && nextCol < layout.cols && nextRow < layout.rows && layout.tiles[nextRow * layout.cols + nextCol] === 0;
  if (isWall(col, row - 1)) mask |= 1;
  if (isWall(col + 1, row)) mask |= 2;
  if (isWall(col, row + 1)) mask |= 4;
  if (isWall(col - 1, row)) mask |= 8;
  return mask;
}

export function findOfficePath(layout: CanvasOfficeLayout, start: { col: number; row: number }, target: { col: number; row: number }) {
  const blocked = getBlockedTiles(layout);
  blocked.delete(tileKey(start.col, start.row));
  if (blocked.has(tileKey(target.col, target.row))) return [];
  const queue: Array<{ col: number; row: number }> = [start];
  const previous = new Map<string, { col: number; row: number } | null>([[tileKey(start.col, start.row), null]]);
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const current = queue[cursor];
    if (current.col === target.col && current.row === target.row) break;
    for (const next of [{ col: current.col + 1, row: current.row }, { col: current.col - 1, row: current.row }, { col: current.col, row: current.row + 1 }, { col: current.col, row: current.row - 1 }]) {
      const key = tileKey(next.col, next.row);
      if (next.col < 0 || next.row < 0 || next.col >= layout.cols || next.row >= layout.rows || blocked.has(key) || previous.has(key)) continue;
      previous.set(key, current);
      queue.push(next);
    }
  }
  if (!previous.has(tileKey(target.col, target.row))) return [];
  const path: Array<{ col: number; row: number }> = [];
  let step: { col: number; row: number } | null = target;
  while (step && (step.col !== start.col || step.row !== start.row)) {
    path.unshift(step);
    step = previous.get(tileKey(step.col, step.row)) ?? null;
  }
  return path;
}

function directionTo(from: { col: number; row: number }, to: { col: number; row: number }): CanvasDirection {
  if (to.col > from.col) return 'right';
  if (to.col < from.col) return 'left';
  if (to.row < from.row) return 'up';
  return 'down';
}

/** Monotonic seconds advanced by update(dt); used for speech expiry and lifecycle timing. */
const SPEECH_TTL = 6;

export class CanvasOfficeEngine {
  layout: CanvasOfficeLayout;
  characters = new Map<string, CanvasCharacter>();
  clock = 0;
  door: { col: number; row: number };

  constructor(layout = createDefaultCanvasLayout()) {
    this.layout = cloneOfficeLayout(layout);
    this.door = this.findDoor();
  }

  setLayout(layout: CanvasOfficeLayout) {
    this.layout = cloneOfficeLayout(layout);
    this.door = this.findDoor();
    this.reassignSeats();
  }

  /** Nearest walkable tile to the bottom-centre of the floor — where agents enter and exit. */
  private findDoor(): { col: number; row: number } {
    const blocked = getBlockedTiles(this.layout);
    const centre = Math.floor(this.layout.cols / 2);
    for (let row = this.layout.rows - 2; row >= 1; row -= 1) {
      for (let spread = 0; spread < this.layout.cols; spread += 1) {
        for (const col of [centre + spread, centre - spread]) {
          if (col > 0 && col < this.layout.cols - 1 && !blocked.has(tileKey(col, row))) return { col, row };
        }
      }
    }
    return { col: 1, row: this.layout.rows - 2 };
  }

  setAgents(agents: CanvasAgentData[]) {
    const ids = new Set(agents.map(agent => agent.id));
    // Agents that dropped off the roster walk out through the door before they are removed.
    this.characters.forEach(character => {
      if (!ids.has(character.agent.id) && character.lifecycle !== 'leaving') {
        character.lifecycle = 'leaving';
        character.seat = null;
        character.path = findOfficePath(this.layout, character, this.door);
        character.state = character.path.length ? 'walk' : 'idle';
      }
    });
    const occupied = new Set([...this.characters.values()].map(character => tileKey(character.col, character.row)));
    agents.forEach(agent => {
      const current = this.characters.get(agent.id);
      if (current) {
        const wasWorking = current.agent.statusKind === 'working';
        current.agent = agent;
        if (current.lifecycle === 'leaving') current.lifecycle = 'active';
        if (!current.specialist) current.specialist = inferSpecialist(agent.current_task, agent.last_action);
        if (!wasWorking && agent.statusKind === 'working') this.sendToSeat(current);
        return;
      }
      // Newcomers walk in through the door rather than teleporting to a random tile.
      const { col, row } = this.door;
      occupied.add(tileKey(col, row));
      this.characters.set(agent.id, {
        agent, col, row, x: col * OFFICE_TILE_SIZE + 8, y: row * OFFICE_TILE_SIZE + 8,
        direction: 'up', state: 'walk', path: [], frame: 0, frameTimer: 0,
        palette: hashString(agent.id) % 6, seat: null, wanderTimer: 1 + (hashString(agent.id) % 30) / 10, spawnTimer: .7,
        lifecycle: 'entering', speech: null, specialist: inferSpecialist(agent.current_task, agent.last_action),
        activeUntil: 0, removeAt: null,
      });
    });
    this.reassignSeats();
  }

  private seats() {
    const seats: Array<{ col: number; row: number; purpose: 'work' | 'lounge' }> = [];
    this.layout.furniture.forEach(item => {
      const spec = FURNITURE_CATALOG[item.kind] as FurnitureSpec;
      const floor = this.layout.tiles[item.row * this.layout.cols + item.col];
      if (spec.seat === 'work' || (spec.seat === 'lounge' && floor === 4)) seats.push({ col: item.col, row: item.row, purpose: spec.seat });
      if (item.kind === 'SOFA_FRONT') {
        const seatFloor = this.layout.tiles[(item.row + 1) * this.layout.cols + item.col];
        if (seatFloor === 4) for (let offset = 0; offset < spec.footprintW; offset += 1) seats.push({ col: item.col + offset, row: item.row + 1, purpose: 'lounge' });
      }
    });
    return seats;
  }

  private wantsLounge(character: CanvasCharacter) {
    return character.agent.statusKind === 'waiting' || character.agent.statusKind === 'paused' || character.agent.statusKind === 'offline';
  }

  private reassignSeats() {
    const seats = this.seats();
    const occupied = new Set<string>();
    [...this.characters.values()].sort((a, b) => Number(b.agent.statusKind === 'working') - Number(a.agent.statusKind === 'working') || a.agent.id.localeCompare(b.agent.id)).forEach(character => {
      const purpose = character.agent.statusKind === 'working' ? 'work' : this.wantsLounge(character) ? 'lounge' : null;
      let seat = purpose && character.seat?.purpose === purpose ? seats.find(item => item.col === character.seat?.col && item.row === character.seat.row && !occupied.has(tileKey(item.col, item.row))) : undefined;
      if (!seat && purpose) {
        const pool = seats.filter(item => item.purpose === purpose);
        const start = hashString(character.agent.id) % pool.length;
        for (let offset = 0; offset < pool.length; offset += 1) {
          const candidate = pool[(start + offset) % pool.length];
          if (!occupied.has(tileKey(candidate.col, candidate.row))) { seat = candidate; break; }
        }
      }
      character.seat = seat || null;
      if (seat) occupied.add(tileKey(seat.col, seat.row));
      if (purpose) this.sendToSeat(character);
      else { character.path = []; character.state = 'idle'; }
    });
  }

  private sendToSeat(character: CanvasCharacter) {
    if (!character.seat) { character.state = character.agent.statusKind === 'working' ? 'type' : 'idle'; return; }
    if (character.col === character.seat.col && character.row === character.seat.row) {
      character.path = [];
      character.direction = character.seat.purpose === 'lounge' ? 'down' : 'up';
      character.state = character.seat.purpose === 'lounge' ? 'rest' : this.isReading(character) ? 'read' : 'type';
      return;
    }
    character.path = findOfficePath(this.layout, character, character.seat);
    if (character.path.length) character.state = 'walk';
  }

  private isReading(character: CanvasCharacter) {
    return /read|search|research|analyse|analyze|index|review|изуч|поиск|анализ/i.test(`${character.agent.current_task || ''} ${character.agent.last_action || ''}`);
  }

  private randomWalkable(character: CanvasCharacter) {
    const blocked = getBlockedTiles(this.layout);
    const candidates: Array<{ col: number; row: number }> = [];
    for (let row = 1; row < this.layout.rows - 1; row += 1) for (let col = 1; col < this.layout.cols - 1; col += 1) if (!blocked.has(tileKey(col, row))) candidates.push({ col, row });
    if (!candidates.length) return;
    const target = candidates[(hashString(character.agent.id) + Math.floor(performance.now() / 3000)) % candidates.length];
    const path = findOfficePath(this.layout, character, target);
    if (path.length) { character.path = path; character.state = 'walk'; }
  }

  moveAgentTo(id: string, col: number, row: number) {
    const character = this.characters.get(id);
    if (!character) return false;
    const path = findOfficePath(this.layout, character, { col, row });
    if (!path.length) return false;
    character.path = path;
    character.state = 'walk';
    return true;
  }

  /** Attach a live speech bubble (and infer specialist) from an orchestrator trace. */
  applyTrace(trace: CanvasLiveTrace) {
    const needle = (trace.agent || '').trim().toLowerCase();
    if (!needle) return;
    const character = [...this.characters.values()].find(item => {
      const name = (item.agent.name || '').trim().toLowerCase();
      return name === needle || name.includes(needle) || needle.includes(name) || item.agent.id.toLowerCase() === needle;
    });
    if (!character) return;
    const kind: CanvasSpeechKind = trace.status === 'error' ? 'error' : trace.status === 'success' ? 'success' : 'info';
    const text = (trace.message || trace.action || '').split('\n')[0].trim();
    if (text) character.speech = { text: text.slice(0, 90), kind, until: this.clock + SPEECH_TTL };
    character.activeUntil = this.clock + SPEECH_TTL;
    const specialist = inferSpecialist(trace.action, trace.message, character.agent.current_task);
    if (specialist) character.specialist = specialist;
  }

  update(dt: number) {
    this.clock += dt;
    const toRemove: string[] = [];
    this.characters.forEach(character => {
      character.spawnTimer = Math.max(0, character.spawnTimer - dt);
      character.frameTimer += dt;
      if (character.frameTimer >= .18) { character.frameTimer = 0; character.frame = (character.frame + 1) % 4; }
      if (character.speech && this.clock >= character.speech.until) character.speech = null;
      if (character.lifecycle === 'entering' && (character.col !== this.door.col || character.row !== this.door.row)) character.lifecycle = 'active';
      if (character.lifecycle === 'leaving' && !character.path.length) { toRemove.push(character.agent.id); return; }
      if (character.path.length) {
        const target = character.path[0];
        character.direction = directionTo(character, target);
        const targetX = target.col * OFFICE_TILE_SIZE + 8;
        const targetY = target.row * OFFICE_TILE_SIZE + 8;
        const distance = Math.hypot(targetX - character.x, targetY - character.y);
        const amount = Math.min(distance, dt * 44);
        if (distance <= 1 || amount >= distance) {
          character.x = targetX; character.y = targetY; character.col = target.col; character.row = target.row; character.path.shift();
          if (!character.path.length) {
            if (character.seat && character.col === character.seat.col && character.row === character.seat.row) {
              character.direction = character.seat.purpose === 'lounge' ? 'down' : 'up';
              character.state = character.seat.purpose === 'lounge' ? 'rest' : this.isReading(character) ? 'read' : 'type';
            } else character.state = 'idle';
          }
        } else {
          character.x += ((targetX - character.x) / distance) * amount;
          character.y += ((targetY - character.y) / distance) * amount;
          character.state = 'walk';
        }
        return;
      }
      if (character.agent.statusKind === 'working') {
        this.sendToSeat(character);
        return;
      }
      if (this.wantsLounge(character)) {
        this.sendToSeat(character);
        return;
      }
      character.state = 'idle';
      if (character.agent.statusKind === 'error') return;
      character.wanderTimer -= dt;
      if (character.wanderTimer <= 0) {
        this.randomWalkable(character);
        character.wanderTimer = 4 + (hashString(character.agent.id + String(character.frame)) % 50) / 10;
      }
    });
    toRemove.forEach(id => this.characters.delete(id));
  }
}
