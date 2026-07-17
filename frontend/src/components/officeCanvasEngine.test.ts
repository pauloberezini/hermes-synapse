import { describe, expect, it } from 'vitest';
import { CanvasOfficeEngine, createDefaultCanvasLayout, findOfficePath, getBlockedTiles, getWallMask, inferSpecialist, normalizeCanvasLayout } from './officeCanvasEngine';

describe('canvas office engine', () => {
  it('finds routes around walls and blocking furniture', () => {
    const layout = createDefaultCanvasLayout();
    const path = findOfficePath(layout, { col: 1, row: 16 }, { col: 3, row: 6 });
    expect(path.length).toBeGreaterThan(0);
    const blocked = getBlockedTiles(layout);
    expect(path.every(tile => !blocked.has(`${tile.col},${tile.row}`))).toBe(true);
    expect(findOfficePath(layout, { col: 1, row: 16 }, { col: 0, row: 16 })).toEqual([]);
  });

  it('builds connected interior walls with walkable doorways', () => {
    const layout = createDefaultCanvasLayout();
    expect(layout.tiles[11 * layout.cols + 1]).toBe(0);
    expect(layout.tiles[11 * layout.cols + 5]).not.toBe(0);
    expect(layout.tiles[5 * layout.cols + 18]).toBe(0);
    expect(layout.tiles[8 * layout.cols + 18]).not.toBe(0);
    expect(getWallMask(layout, 0, 0)).toBe(6);
  });

  it('assigns agents to seats and moves active agents into a work animation', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents([{ id: 'research', name: 'Research Agent', statusKind: 'working', current_task: 'Research documentation' }]);
    for (let frame = 0; frame < 500; frame += 1) engine.update(.05);
    const character = engine.characters.get('research');
    expect(character?.seat).not.toBeNull();
    expect(character?.path).toHaveLength(0);
    expect(character?.state).toBe('read');
  });

  it('sends agents without work to unique lounge seats', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents(Array.from({ length: 9 }, (_, index) => ({ id: `idle-${index}`, name: `Idle ${index}`, statusKind: index % 3 === 0 ? 'waiting' : index % 3 === 1 ? 'paused' : 'offline' })));
    for (let frame = 0; frame < 900; frame += 1) engine.update(.05);
    const characters = [...engine.characters.values()];
    expect(characters.every(character => character.seat?.purpose === 'lounge')).toBe(true);
    expect(new Set(characters.map(character => `${character.col},${character.row}`)).size).toBe(9);
    expect(characters.every(character => character.state === 'rest')).toBe(true);
  });

  it('spawns newcomers at the door and lets them enter', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents([{ id: 'a1', name: 'Alpha', statusKind: 'working' }]);
    const character = engine.characters.get('a1');
    expect(character?.col).toBe(engine.door.col);
    expect(character?.row).toBe(engine.door.row);
    expect(character?.lifecycle).toBe('entering');
    for (let frame = 0; frame < 400; frame += 1) engine.update(.05);
    expect(engine.characters.get('a1')?.lifecycle).toBe('active');
  });

  it('walks removed agents out through the door before deleting them', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents([{ id: 'a1', name: 'Alpha', statusKind: 'working' }]);
    for (let frame = 0; frame < 300; frame += 1) engine.update(.05);
    engine.setAgents([]);
    expect(engine.characters.get('a1')?.lifecycle).toBe('leaving');
    for (let frame = 0; frame < 400; frame += 1) engine.update(.05);
    expect(engine.characters.has('a1')).toBe(false);
  });

  it('attaches a live speech bubble from a matching trace and expires it', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents([{ id: 'research', name: 'Research Agent', statusKind: 'working' }]);
    engine.update(.05);
    engine.applyTrace({ agent: 'Research Agent', action: 'web_search', message: 'Searching arxiv for papers', status: 'success' });
    const character = engine.characters.get('research');
    expect(character?.speech?.text).toContain('Searching');
    expect(character?.speech?.kind).toBe('success');
    expect(character?.specialist).toBe('Researcher');
    for (let frame = 0; frame < 200; frame += 1) engine.update(.05);
    expect(engine.characters.get('research')?.speech).toBeNull();
  });

  it('maps keywords to specialist personas', () => {
    expect(inferSpecialist('fix the crash', 'traceback')).toBe('Debugger');
    expect(inferSpecialist('обнови вёрстку', undefined)).toBe('Frontend');
    expect(inferSpecialist('rotate the auth token')).toBe('Security');
    expect(inferSpecialist('just chatting')).toBeNull();
  });

  it('keeps large agent rosters and rejects malformed saved layouts', () => {
    const engine = new CanvasOfficeEngine();
    engine.setAgents(Array.from({ length: 55 }, (_, index) => ({ id: `agent-${index}`, name: `Agent ${index}`, statusKind: index % 2 ? 'waiting' : 'working' })));
    expect(engine.characters.size).toBe(55);
    expect(normalizeCanvasLayout({ cols: 28, rows: 18, tiles: [] })).toEqual(createDefaultCanvasLayout());
    const layout = createDefaultCanvasLayout();
    const normalized = normalizeCanvasLayout({ ...layout, furniture: [{ id: 'outside', kind: 'DESK_FRONT', col: 99, row: 99 }] });
    expect(normalized.furniture).toEqual([]);
  });
});
