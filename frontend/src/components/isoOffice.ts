import type { CanvasAgentData, CanvasCharacter, CanvasDirection } from './officeCanvasEngine';

export const ISO_TILE_W = 64;
export const ISO_TILE_H = 32;

export interface IsoPoint {
  x: number;
  y: number;
}

export function tileToIso(tx: number, ty: number): IsoPoint {
  return { x: (tx - ty) * (ISO_TILE_W / 2), y: (tx + ty) * (ISO_TILE_H / 2) };
}

export function isoToTile(x: number, y: number): { tx: number; ty: number } {
  const a = x / (ISO_TILE_W / 2);
  const b = y / (ISO_TILE_H / 2);
  return { tx: (a + b) / 2, ty: (b - a) / 2 };
}

export function isoWorldBounds(cols: number, rows: number) {
  const corners = [tileToIso(0, 0), tileToIso(cols, 0), tileToIso(0, rows), tileToIso(cols, rows)];
  const xs = corners.map(corner => corner.x);
  const ys = corners.map(corner => corner.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

export type IsoRoomId = 'studio' | 'research' | 'meeting' | 'lounge' | 'control';
export type IsoAssetMotion = 'none' | 'monitor' | 'steam' | 'sway' | 'signal';

export interface IsoFloorProjection {
  origin: IsoPoint;
  colAxis: IsoPoint;
  rowAxis: IsoPoint;
}

export interface IsoSceneAsset {
  id: string;
  src: string;
  x: number;
  y: number;
  height: number;
  z?: number;
  motion?: IsoAssetMotion;
  activeSrc?: string;
}

export interface IsoRoomScene {
  id: IsoRoomId;
  label: { ru: string; en: string };
  shortLabel: { ru: string; en: string };
  description: { ru: string; en: string };
  background: 'day' | 'night';
  accent: string;
  tint: string;
  floor: IsoFloorProjection;
  assets: IsoSceneAsset[];
}

const SCENE_ROOT = '/iso-office-assets/scene';
const furniture = (name: string) => `${SCENE_ROOT}/furniture/${name}.webp`;
const appliance = (name: string) => `${SCENE_ROOT}/appliances/${name}.webp`;
const decoration = (name: string) => `${SCENE_ROOT}/decoration/${name}.webp`;
const culture = (name: string) => `${SCENE_ROOT}/culture/${name}.webp`;

const SHARED_FLOOR: IsoFloorProjection = {
  origin: { x: 44.7, y: 31.5 },
  colAxis: { x: 43.8, y: 25.2 },
  rowAxis: { x: -39.2, y: 25.8 },
};

const desk = (id: string, x: number, y: number, facing: 'left-front' | 'left-rear' | 'right-front' | 'right-rear' = 'left-front'): IsoSceneAsset => ({
  id,
  src: furniture(`standing-desk-${facing}`),
  x,
  y,
  height: 104,
  motion: 'monitor',
});

const plant = (id: string, name: 'monstera-plant' | 'snake-plant' | 'money-tree', x: number, y: number, height = 72): IsoSceneAsset => ({
  id,
  src: decoration(name),
  x,
  y,
  height,
  motion: 'sway',
});

const STUDIO_ASSETS: IsoSceneAsset[] = [
  desk('studio-desk-1', 41.7, 49.6, 'left-rear'),
  desk('studio-desk-2', 46.2, 52.2, 'left-front'),
  desk('studio-desk-3', 38.7, 54.7, 'right-front'),
  desk('studio-desk-4', 30.6, 64.1, 'left-rear'),
  desk('studio-desk-5', 35.2, 67.0, 'left-front'),
  desk('studio-desk-6', 27.2, 69.5, 'right-front'),
  desk('studio-desk-7', 58.2, 72.8, 'left-rear'),
  desk('studio-desk-8', 62.5, 75.3, 'left-front'),
  desk('studio-desk-9', 54.1, 78.0, 'right-front'),
  { id: 'studio-printer', src: decoration('printer-working'), x: 84.7, y: 57.0, height: 68, motion: 'signal' },
  { id: 'studio-filing', src: furniture('filling-closed'), x: 45.0, y: 56.5, height: 56 },
  plant('studio-plant-1', 'snake-plant', 43.2, 38.0, 63),
  plant('studio-plant-2', 'money-tree', 31.8, 71.0, 63),
  plant('studio-plant-3', 'monstera-plant', 91.0, 64.4, 74),
];

export const ISO_ROOMS: IsoRoomScene[] = [
  {
    id: 'studio',
    label: { ru: 'Инженерная студия', en: 'Engineering Studio' },
    shortLabel: { ru: 'Студия', en: 'Studio' },
    description: { ru: 'Разработка, тестирование и сборка', en: 'Build, test and delivery' },
    background: 'day',
    accent: '#60a5fa',
    tint: 'rgba(49, 94, 145, .04)',
    floor: SHARED_FLOOR,
    assets: STUDIO_ASSETS,
  },
  {
    id: 'research',
    label: { ru: 'Исследовательская лаборатория', en: 'Research Lab' },
    shortLabel: { ru: 'Лаборатория', en: 'Research' },
    description: { ru: 'Поиск, индексация и работа с моделями', en: 'Search, indexing and model work' },
    background: 'night',
    accent: '#9f8cff',
    tint: 'rgba(91, 69, 164, .12)',
    floor: SHARED_FLOOR,
    assets: [
      desk('research-desk-1', 39.2, 51.2, 'left-rear'),
      desk('research-desk-2', 47.1, 55.3, 'left-front'),
      desk('research-desk-3', 31.7, 59.2, 'right-front'),
      desk('research-desk-4', 52.0, 67.7, 'left-rear'),
      desk('research-desk-5', 42.6, 72.6, 'right-front'),
      { id: 'research-board', src: decoration('white-board'), x: 77.8, y: 42.0, height: 86, motion: 'signal' },
      { id: 'research-filing', src: furniture('filling-open'), x: 81.7, y: 58.5, height: 60 },
      plant('research-plant-1', 'monstera-plant', 88.6, 66.0, 78),
      plant('research-plant-2', 'snake-plant', 32.0, 42.0, 64),
    ],
  },
  {
    id: 'meeting',
    label: { ru: 'Переговорная', en: 'Strategy Room' },
    shortLabel: { ru: 'Переговорная', en: 'Strategy' },
    description: { ru: 'Планы, ревью и решения команды', en: 'Planning, reviews and team decisions' },
    background: 'day',
    accent: '#f2b36b',
    tint: 'rgba(172, 107, 45, .05)',
    floor: SHARED_FLOOR,
    assets: [
      desk('meeting-table-1', 43.0, 58.5, 'left-front'),
      desk('meeting-table-2', 50.5, 62.8, 'right-front'),
      desk('meeting-table-3', 35.5, 63.0, 'left-rear'),
      { id: 'meeting-board', src: culture('todo-board'), x: 79.0, y: 41.5, height: 66, motion: 'signal' },
      { id: 'meeting-bell', src: culture('bell'), x: 63.0, y: 39.0, height: 36, motion: 'signal' },
      plant('meeting-plant-1', 'money-tree', 28.2, 61.8, 64),
      plant('meeting-plant-2', 'monstera-plant', 83.5, 69.0, 76),
    ],
  },
  {
    id: 'lounge',
    label: { ru: 'Комната отдыха', en: 'Lounge' },
    shortLabel: { ru: 'Lounge', en: 'Lounge' },
    description: { ru: 'Пауза, кофе и ожидание новой задачи', en: 'Coffee, recovery and task waiting' },
    background: 'day',
    accent: '#56d6a7',
    tint: 'rgba(42, 127, 99, .06)',
    floor: SHARED_FLOOR,
    assets: [
      { id: 'lounge-coffee', src: appliance('coffee-off'), activeSrc: appliance('coffee-on'), x: 77.7, y: 51.5, height: 52, motion: 'steam' },
      desk('lounge-bar-1', 62.5, 59.0, 'left-front'),
      desk('lounge-bar-2', 54.2, 64.2, 'right-front'),
      plant('lounge-plant-1', 'monstera-plant', 86.8, 65.2, 80),
      plant('lounge-plant-2', 'money-tree', 31.5, 66.0, 66),
      plant('lounge-plant-3', 'snake-plant', 44.0, 47.0, 64),
    ],
  },
  {
    id: 'control',
    label: { ru: 'Центр управления', en: 'Control Room' },
    shortLabel: { ru: 'Control', en: 'Control' },
    description: { ru: 'Деплой, инциденты и проверка результатов', en: 'Deployments, incidents and validation' },
    background: 'night',
    accent: '#ff6f87',
    tint: 'rgba(158, 42, 68, .1)',
    floor: SHARED_FLOOR,
    assets: [
      desk('control-desk-1', 40.2, 56.0, 'left-rear'),
      desk('control-desk-2', 49.0, 61.2, 'left-front'),
      desk('control-desk-3', 32.0, 65.2, 'right-front'),
      { id: 'control-screen', src: culture('deploying-screen'), x: 87.8, y: 42.8, height: 72, motion: 'signal' },
      { id: 'control-printer', src: decoration('printer-broken'), activeSrc: decoration('printer-working'), x: 79.5, y: 58.0, height: 68, motion: 'signal' },
      plant('control-plant', 'snake-plant', 27.5, 59.0, 64),
    ],
  },
];

export const ISO_ROOM_BY_ID = Object.fromEntries(ISO_ROOMS.map(room => [room.id, room])) as Record<IsoRoomId, IsoRoomScene>;

const SPECIALIST_TO_SPRITE: Record<string, string> = {
  Frontend: 'Frontend-dev-1',
  Security: 'security-audit-1',
  Researcher: 'explore-1',
  Debugger: 'dev-1',
  DevOps: 'dev-2',
  'AI Eng': 'Claude-1',
  Architect: 'Claude-1',
  Reviewer: 'dev-1',
  Fullstack: 'dev-1',
  Tester: 'employee-3',
  DBA: 'employee-2',
  PerfEng: 'dev-2',
};
const SPRITE_POOL = ['employee-1', 'employee-2', 'employee-3', 'dev-1', 'dev-2', 'explore-1'];

export function hashIsoValue(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

export function isoCharacterBase(agent: Pick<CanvasAgentData, 'id' | 'name'>, specialist?: string | null): string {
  const identity = `${agent.id} ${agent.name}`.toLowerCase();
  if (identity.includes('jarvis') || identity.includes('claude') || identity.includes('hermes')) return 'Claude-1';
  if (specialist && SPECIALIST_TO_SPRITE[specialist]) return SPECIALIST_TO_SPRITE[specialist];
  return SPRITE_POOL[hashIsoValue(agent.id) % SPRITE_POOL.length];
}

export function isoDirectionSuffix(direction: CanvasDirection): string {
  if (direction === 'down') return 'front-left';
  if (direction === 'right') return 'front-right';
  if (direction === 'up') return 'rear-right';
  return 'rear-left';
}

export function isoCharacterAsset(agent: Pick<CanvasAgentData, 'id' | 'name'>, direction: CanvasDirection = 'down', specialist?: string | null) {
  return `${SCENE_ROOT}/characters/${isoCharacterBase(agent, specialist)}-${isoDirectionSuffix(direction)}.webp`;
}

export function roomForAgent(agent: CanvasAgentData, specialist?: string | null): IsoRoomId {
  if (agent.statusKind === 'error') return 'control';
  if (agent.statusKind === 'waiting' || agent.statusKind === 'paused' || agent.statusKind === 'offline') return 'lounge';
  const role = `${agent.role || ''} ${agent.agent_type || ''}`.toLowerCase();
  if (agent.parent_id || role.includes('orchestrator') || specialist === 'Architect' || specialist === 'Reviewer') return 'meeting';
  if (specialist === 'Researcher' || specialist === 'AI Eng' || specialist === 'DBA') return 'research';
  return 'studio';
}

export function projectCharacterToScene(character: CanvasCharacter, room: IsoRoomScene, cols: number, rows: number): IsoPoint {
  const col = Math.max(0, Math.min(1, (character.x / 16 - 1) / Math.max(1, cols - 3)));
  const row = Math.max(0, Math.min(1, (character.y / 16 - 1) / Math.max(1, rows - 3)));
  return {
    x: room.floor.origin.x + room.floor.colAxis.x * col + room.floor.rowAxis.x * row,
    y: room.floor.origin.y + room.floor.colAxis.y * col + room.floor.rowAxis.y * row,
  };
}

export function projectSceneToTile(point: IsoPoint, room: IsoRoomScene, cols: number, rows: number) {
  const { origin, colAxis, rowAxis } = room.floor;
  const px = point.x - origin.x;
  const py = point.y - origin.y;
  const determinant = colAxis.x * rowAxis.y - colAxis.y * rowAxis.x;
  if (Math.abs(determinant) < .0001) return null;
  const colRatio = (px * rowAxis.y - py * rowAxis.x) / determinant;
  const rowRatio = (colAxis.x * py - colAxis.y * px) / determinant;
  return {
    col: Math.max(1, Math.min(cols - 2, Math.round(1 + colRatio * (cols - 3)))),
    row: Math.max(1, Math.min(rows - 2, Math.round(1 + rowRatio * (rows - 3)))),
  };
}
