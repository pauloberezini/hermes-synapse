import { describe, expect, it } from 'vitest';
import type { CanvasAgentData, CanvasCharacter } from './officeCanvasEngine';
import {
  ISO_ROOM_BY_ID,
  ISO_ROOMS,
  isoCharacterAsset,
  projectCharacterToScene,
  projectSceneToTile,
  roomForAgent,
} from './isoOffice';

const agent = (statusKind: CanvasAgentData['statusKind'], role = ''): CanvasAgentData => ({
  id: `${statusKind}-${role}`,
  name: 'Test Agent',
  statusKind,
  role,
});

describe('isometric office routing', () => {
  it('keeps every activity in one of the five coherent rooms', () => {
    expect(ISO_ROOMS).toHaveLength(5);
    expect(roomForAgent(agent('error'))).toBe('control');
    expect(roomForAgent(agent('waiting'))).toBe('lounge');
    expect(roomForAgent(agent('working', 'orchestrator'))).toBe('meeting');
    expect(roomForAgent(agent('working'), 'Researcher')).toBe('research');
    expect(roomForAgent(agent('working'), 'Frontend')).toBe('studio');
  });

  it('uses directional optimized character assets', () => {
    expect(isoCharacterAsset(agent('working'), 'up')).toMatch(
      /^\/iso-office-assets\/scene\/characters\/.+-rear-right\.webp$/,
    );
  });

  it('maps engine coordinates into and back from the room floor', () => {
    const character = {
      agent: agent('working'),
      x: 16 * 9,
      y: 16 * 7,
    } as CanvasCharacter;
    const scene = projectCharacterToScene(character, ISO_ROOM_BY_ID.studio, 28, 22);
    const tile = projectSceneToTile(scene, ISO_ROOM_BY_ID.studio, 28, 22);

    expect(tile).toEqual({ col: 9, row: 7 });
  });
});
