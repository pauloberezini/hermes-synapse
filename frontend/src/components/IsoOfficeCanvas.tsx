import { Beaker, Code2, Coffee, Monitor, Palette, Presentation } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CanvasOfficeEngine,
  createDefaultCanvasLayout,
  inferSpecialist,
  type CanvasAgentData,
  type CanvasCharacter,
  type CanvasLiveTrace,
} from './officeCanvasEngine';
import {
  hashIsoValue,
  isoCharacterAsset,
  ISO_ROOMS,
  ISO_ROOM_BY_ID,
  projectCharacterToScene,
  projectSceneToTile,
  roomForAgent,
  type IsoPoint,
  type IsoRoomId,
  type IsoSceneAsset,
} from './isoOffice';
import { OFFICE_THEMES, type OfficeThemeKey } from './PixelOfficeCanvas';

interface IsoOfficeCanvasProps {
  agents: CanvasAgentData[];
  selectedAgentId: string;
  onSelectAgent: (id: string, trigger: HTMLElement) => void;
  zoom: number;
  onZoom: (zoom: number) => void;
  language: 'en' | 'ru';
  liveTrace?: (CanvasLiveTrace & { ts: number }) | null;
  theme?: OfficeThemeKey;
  onTheme?: (theme: OfficeThemeKey) => void;
}

interface SceneRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const ROOM_DAY = '/iso-office-assets/rooms/office-day.webp';
const ROOM_NIGHT = '/iso-office-assets/rooms/office-night.webp';
const ROOM_ASPECT = 2400 / 1792;
const STATUS_COLORS = {
  working: '#3ee6a4',
  waiting: '#f3c969',
  error: '#ff667f',
  paused: '#aa8cff',
  offline: '#8995aa',
} as const;
const SPEECH_COLORS = { info: '#6ba6ff', success: '#3ee6a4', error: '#ff667f' } as const;
const ROOM_ICONS = {
  studio: Code2,
  research: Beaker,
  meeting: Presentation,
  lounge: Coffee,
  control: Monitor,
};
const ROOM_STORAGE_KEY = 'hermes_iso_room_v3';
const SPRITE_BASE_HEIGHT = 82;

function imageFor(cache: Map<string, HTMLImageElement>, src: string) {
  let image = cache.get(src);
  if (!image) {
    image = new Image();
    image.decoding = 'async';
    image.src = src;
    cache.set(src, image);
  }
  return image;
}

function fitScene(width: number, height: number, zoom: number, camera: IsoPoint): SceneRect {
  const availableWidth = Math.max(1, width - 24);
  const availableHeight = Math.max(1, height - 24);
  const fitWidth = Math.min(availableWidth, availableHeight * ROOM_ASPECT);
  const fitHeight = fitWidth / ROOM_ASPECT;
  const sceneWidth = fitWidth * zoom;
  const sceneHeight = fitHeight * zoom;
  return {
    x: (width - sceneWidth) / 2 + camera.x,
    y: (height - sceneHeight) / 2 + camera.y,
    width: sceneWidth,
    height: sceneHeight,
  };
}

function scenePoint(rect: SceneRect, point: IsoPoint) {
  return {
    x: rect.x + rect.width * point.x / 100,
    y: rect.y + rect.height * point.y / 100,
  };
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines = 2) {
  const words = text.trim().split(/\s+/);
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines) break;
    } else {
      line = candidate;
    }
  }
  if (lines.length < maxLines && line) lines.push(line);
  if (lines.join(' ').split(/\s+/).length < words.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].replace(/[.,;:\s]+$/, '')}…`;
  }
  return lines;
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, safeRadius);
}

function roomForCharacter(character: CanvasCharacter) {
  return roomForAgent(character.agent, character.specialist);
}

function initialRoom(): IsoRoomId {
  const saved = localStorage.getItem(ROOM_STORAGE_KEY);
  return saved && saved in ISO_ROOM_BY_ID ? saved as IsoRoomId : 'studio';
}

function drawFurniture(
  ctx: CanvasRenderingContext2D,
  cache: Map<string, HTMLImageElement>,
  rect: SceneRect,
  asset: IsoSceneAsset,
  time: number,
) {
  const active = asset.activeSrc && Math.floor(time / 900 + hashIsoValue(asset.id) % 3) % 2 === 1;
  const image = imageFor(cache, active ? asset.activeSrc! : asset.src);
  if (!image.complete || !image.naturalWidth) return;
  const unit = rect.width / 800;
  const height = asset.height * unit;
  const width = height * image.naturalWidth / image.naturalHeight;
  const anchor = scenePoint(rect, asset);
  const phase = time / 1000 + hashIsoValue(asset.id) % 7;
  const sway = asset.motion === 'sway' ? Math.sin(phase * .75) * .012 : 0;
  const pulse = asset.motion === 'monitor' ? 1 + Math.sin(phase * 3) * .004 : 1;

  ctx.save();
  ctx.translate(anchor.x, anchor.y);
  ctx.rotate(sway);
  ctx.scale(pulse, pulse);
  ctx.shadowColor = 'rgba(4, 8, 18, .28)';
  ctx.shadowBlur = 3 * unit;
  ctx.shadowOffsetY = 2 * unit;
  ctx.drawImage(image, -width / 2, -height, width, height);
  ctx.restore();

  if (asset.motion === 'monitor') {
    const glow = (Math.sin(phase * 2.6) + 1) / 2;
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    ctx.globalAlpha = .08 + glow * .08;
    ctx.fillStyle = '#78ccff';
    ctx.fillRect(anchor.x - width * .14, anchor.y - height * .69, width * .28, height * .18);
    ctx.restore();
  }
  if (asset.motion === 'steam' && active) {
    ctx.save();
    ctx.strokeStyle = 'rgba(225, 242, 255, .55)';
    ctx.lineWidth = Math.max(1, unit);
    for (let index = 0; index < 3; index += 1) {
      const offset = ((time / 24 + index * 11) % 26) * unit;
      ctx.globalAlpha = Math.max(0, .7 - offset / (42 * unit));
      ctx.beginPath();
      ctx.arc(anchor.x + (index - 1) * 4 * unit, anchor.y - height - offset, 3 * unit, Math.PI * .2, Math.PI * 1.2);
      ctx.stroke();
    }
    ctx.restore();
  }
  if (asset.motion === 'signal') {
    const glow = (Math.sin(phase * 2.2) + 1) / 2;
    ctx.save();
    ctx.globalAlpha = .08 + glow * .07;
    ctx.fillStyle = '#91ddff';
    ctx.beginPath();
    ctx.ellipse(anchor.x, anchor.y - height * .55, width * .32, height * .25, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

export function IsoOfficeCanvas({
  agents,
  selectedAgentId,
  onSelectAgent,
  zoom,
  onZoom,
  language,
  liveTrace,
  theme = 'hermes',
  onTheme,
}: IsoOfficeCanvasProps) {
  const engineRef = useRef(new CanvasOfficeEngine(createDefaultCanvasLayout()));
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const imagesRef = useRef(new Map<string, HTMLImageElement>());
  const spritesRef = useRef(new Map<string, { x: number; y: number; width: number; height: number }>());
  const sceneRectRef = useRef<SceneRect>({ x: 0, y: 0, width: 1, height: 1 });
  const cameraRef = useRef<IsoPoint>({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; cameraX: number; cameraY: number; moved: boolean } | null>(null);
  const hoveredRef = useRef('');
  const roomChangedAtRef = useRef(0);
  const [roomId, setRoomIdState] = useState<IsoRoomId>(initialRoom);
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const palette = OFFICE_THEMES[theme] ?? OFFICE_THEMES.hermes;
  const room = ISO_ROOM_BY_ID[roomId];

  const roomCounts = useMemo(() => {
    const counts = Object.fromEntries(ISO_ROOMS.map(item => [item.id, 0])) as Record<IsoRoomId, number>;
    agents.forEach(agent => {
      const specialist = inferSpecialist(agent.current_task, agent.last_action, agent.role);
      counts[roomForAgent(agent, specialist)] += 1;
    });
    return counts;
  }, [agents]);

  const setRoomId = (next: IsoRoomId) => {
    if (next === roomId) return;
    setRoomIdState(next);
    localStorage.setItem(ROOM_STORAGE_KEY, next);
    cameraRef.current = { x: 0, y: 0 };
    roomChangedAtRef.current = performance.now();
  };

  useEffect(() => {
    engineRef.current.setAgents(agents);
  }, [agents]);

  useEffect(() => {
    if (liveTrace) engineRef.current.applyTrace(liveTrace);
  }, [liveTrace]);

  useEffect(() => {
    if (!selectedAgentId) return;
    const character = engineRef.current.characters.get(selectedAgentId);
    if (character) setRoomId(roomForCharacter(character));
    // roomId is intentionally omitted: selection, not room navigation, drives this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgentId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const shell = shellRef.current;
    if (!canvas || !shell) return;
    let frameId = 0;
    let lastTime = 0;

    const resize = () => {
      const bounds = shell.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(bounds.width * dpr));
      const height = Math.max(1, Math.round(bounds.height * dpr));
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(shell);
    resize();

    const render = (time: number) => {
      const dt = lastTime ? Math.min(.05, (time - lastTime) / 1000) : 0;
      lastTime = time;
      const engine = engineRef.current;
      engine.update(dt);
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const rect = fitScene(canvas.width, canvas.height, zoom, cameraRef.current);
      sceneRectRef.current = rect;
      const unit = rect.width / 800;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#07101d';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const backgroundSrc = room.background === 'night' ? ROOM_NIGHT : ROOM_DAY;
      const background = imageFor(imagesRef.current, backgroundSrc);
      if (background.complete && background.naturalWidth) {
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(background, rect.x, rect.y, rect.width, rect.height);
      } else {
        ctx.fillStyle = '#111d2d';
        ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
      }

      ctx.save();
      ctx.fillStyle = room.tint;
      ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
      const transitionAge = roomChangedAtRef.current ? time - roomChangedAtRef.current : 1000;
      if (transitionAge < 420) {
        ctx.globalAlpha = Math.max(0, 1 - transitionAge / 420);
        ctx.fillStyle = '#08111f';
        ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
      }
      ctx.restore();

      const light = ctx.createRadialGradient(
        rect.x + rect.width * .51,
        rect.y + rect.height * .54,
        rect.width * .02,
        rect.x + rect.width * .51,
        rect.y + rect.height * .54,
        rect.width * .34,
      );
      light.addColorStop(0, room.background === 'night' ? 'rgba(100, 164, 255, .065)' : 'rgba(255, 226, 159, .08)');
      light.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = light;
      ctx.fillRect(rect.x, rect.y, rect.width, rect.height);

      const drawables: Array<{ depth: number; layer: number; draw: () => void }> = [];
      room.assets.forEach(asset => {
        drawables.push({
          depth: asset.z ?? asset.y,
          layer: 0,
          draw: () => drawFurniture(ctx, imagesRef.current, rect, asset, time),
        });
      });

      spritesRef.current.clear();
      engine.characters.forEach(character => {
        if (roomForCharacter(character) !== room.id) return;
        const point = projectCharacterToScene(character, room, engine.layout.cols, engine.layout.rows);
        drawables.push({
          depth: point.y,
          layer: 1,
          draw: () => {
            const anchor = scenePoint(rect, point);
            const moving = character.state === 'walk';
            const phase = time / 1000 * (moving ? 10 : 2.2) + hashIsoValue(character.agent.id) % 11;
            const bob = moving ? Math.abs(Math.sin(phase)) * 3.2 * unit : Math.sin(phase) * .8 * unit;
            const lean = moving ? Math.sin(phase) * .018 : 0;
            const restScale = character.state === 'rest' ? .96 : 1;
            const image = imageFor(imagesRef.current, isoCharacterAsset(character.agent, character.direction, character.specialist));
            const spriteHeight = SPRITE_BASE_HEIGHT * unit * restScale;
            const spriteWidth = image.naturalHeight ? spriteHeight * image.naturalWidth / image.naturalHeight : spriteHeight * .49;
            const drawX = anchor.x - spriteWidth / 2;
            const drawY = anchor.y - spriteHeight - bob;
            const selected = selectedAgentId === character.agent.id;
            const hovered = hoveredRef.current === character.agent.id;

            ctx.save();
            ctx.beginPath();
            ctx.ellipse(anchor.x, anchor.y + 1.5 * unit, spriteWidth * .42, spriteWidth * .16, 0, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(5, 9, 17, .38)';
            ctx.fill();
            if (selected || hovered) {
              ctx.lineWidth = Math.max(1.5, unit * 1.2);
              ctx.strokeStyle = selected ? room.accent : 'rgba(231, 240, 255, .72)';
              ctx.shadowColor = selected ? room.accent : 'transparent';
              ctx.shadowBlur = selected ? 9 * unit : 0;
              ctx.stroke();
            }
            ctx.restore();

            ctx.save();
            ctx.translate(anchor.x, anchor.y - bob);
            ctx.rotate(lean);
            ctx.globalAlpha = character.lifecycle === 'leaving' ? .6 : Math.max(.25, 1 - character.spawnTimer / .7);
            ctx.shadowColor = 'rgba(3, 7, 14, .42)';
            ctx.shadowBlur = 3 * unit;
            ctx.shadowOffsetY = 2 * unit;
            if (image.complete && image.naturalWidth) {
              ctx.drawImage(image, -spriteWidth / 2, -spriteHeight, spriteWidth, spriteHeight);
            }
            ctx.restore();

            spritesRef.current.set(character.agent.id, { x: drawX, y: drawY, width: spriteWidth, height: spriteHeight });
            ctx.beginPath();
            ctx.arc(anchor.x + spriteWidth * .38, drawY + spriteHeight * .16, Math.max(2.3, 2.5 * unit), 0, Math.PI * 2);
            ctx.fillStyle = '#07101d';
            ctx.fill();
            ctx.beginPath();
            ctx.arc(anchor.x + spriteWidth * .38, drawY + spriteHeight * .16, Math.max(1.4, 1.45 * unit), 0, Math.PI * 2);
            ctx.fillStyle = STATUS_COLORS[character.agent.statusKind];
            ctx.fill();

            const effectName = character.agent.statusKind === 'error'
              ? 'build-failed'
              : character.state === 'rest'
                ? 'sleeping'
                : character.state === 'type'
                  ? 'typing'
                  : character.speech?.kind === 'success'
                    ? 'thumb-up'
                    : '';
            if (effectName) {
              const effect = imageFor(imagesRef.current, `/iso-office-assets/scene/effects/${effectName}.webp`);
              if (effect.complete && effect.naturalWidth) {
                const effectSize = 22 * unit;
                const float = Math.sin(time / 360 + hashIsoValue(character.agent.id)) * 2 * unit;
                ctx.drawImage(effect, anchor.x + spriteWidth * .2, drawY - 18 * unit + float, effectSize, effectSize);
              }
            }

            if (character.speech) {
              ctx.save();
              ctx.font = `600 ${Math.max(10, 10 * unit)}px Inter, sans-serif`;
              const lines = wrapText(ctx, character.speech.text, 152 * unit, 2);
              const lineHeight = 14 * unit;
              const width = Math.max(...lines.map(line => ctx.measureText(line).width), 52 * unit) + 18 * unit;
              const height = lines.length * lineHeight + 15 * unit;
              const x = anchor.x - width / 2;
              const y = drawY - height - 12 * unit;
              roundedRect(ctx, x, y, width, height, 5 * unit);
              ctx.fillStyle = 'rgba(247, 249, 252, .97)';
              ctx.shadowColor = 'rgba(2, 8, 18, .4)';
              ctx.shadowBlur = 10 * unit;
              ctx.fill();
              ctx.shadowBlur = 0;
              ctx.fillStyle = SPEECH_COLORS[character.speech.kind];
              ctx.fillRect(x, y, width, 2.5 * unit);
              ctx.beginPath();
              ctx.moveTo(anchor.x - 5 * unit, y + height);
              ctx.lineTo(anchor.x + 5 * unit, y + height);
              ctx.lineTo(anchor.x, y + height + 6 * unit);
              ctx.closePath();
              ctx.fillStyle = 'rgba(247, 249, 252, .97)';
              ctx.fill();
              ctx.fillStyle = '#152033';
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              lines.forEach((line, index) => ctx.fillText(line, anchor.x, y + 9 * unit + index * lineHeight + lineHeight / 2));
              ctx.restore();
            }

            if (selected || hovered) {
              ctx.save();
              ctx.font = `700 ${Math.max(10, 10.5 * unit)}px Inter, sans-serif`;
              const label = character.agent.name;
              const width = Math.min(190 * unit, ctx.measureText(label).width + 22 * unit);
              const x = anchor.x - width / 2;
              const y = character.speech ? drawY : drawY - 15 * unit;
              roundedRect(ctx, x, y, width, 19 * unit, 3 * unit);
              ctx.fillStyle = 'rgba(7, 15, 28, .94)';
              ctx.fill();
              ctx.fillStyle = selected ? room.accent : '#f2f6ff';
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillText(label, anchor.x, y + 9.5 * unit, width - 10 * unit);
              ctx.restore();
            }
          },
        });
      });

      drawables.sort((left, right) => left.depth - right.depth || left.layer - right.layer).forEach(item => item.draw());

      ctx.save();
      ctx.strokeStyle = 'rgba(126, 157, 204, .16)';
      ctx.lineWidth = Math.max(1, unit);
      ctx.strokeRect(rect.x + .5, rect.y + .5, rect.width - 1, rect.height - 1);
      ctx.restore();
      frameId = requestAnimationFrame(render);
    };

    frameId = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [palette.accent, room, selectedAgentId, zoom]);

  const pickCharacter = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return '';
    const bounds = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = (clientX - bounds.left) * dpr;
    const y = (clientY - bounds.top) * dpr;
    let best = '';
    let bestY = -Infinity;
    spritesRef.current.forEach((box, id) => {
      if (x >= box.x && x <= box.x + box.width && y >= box.y && y <= box.y + box.height && box.y > bestY) {
        best = id;
        bestY = box.y;
      }
    });
    return best;
  };

  const pickTile = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const bounds = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const rect = sceneRectRef.current;
    const point = {
      x: ((clientX - bounds.left) * dpr - rect.x) / rect.width * 100,
      y: ((clientY - bounds.top) * dpr - rect.y) / rect.height * 100,
    };
    return projectSceneToTile(point, room, engineRef.current.layout.cols, engineRef.current.layout.rows);
  };

  return (
    <div ref={shellRef} className="pixel-canvas-shell iso-canvas-shell iso-scene-shell" style={{ '--iso-room-accent': room.accent } as React.CSSProperties}>
      <canvas
        ref={canvasRef}
        className="pixel-office-canvas iso-scene-canvas"
        role="img"
        aria-label={language === 'ru' ? `Изометрический офис: ${room.label.ru}` : `Isometric office: ${room.label.en}`}
        tabIndex={0}
        onWheel={event => {
          event.preventDefault();
          onZoom(Math.max(.7, Math.min(1.65, zoom + (event.deltaY < 0 ? .08 : -.08))));
        }}
        onPointerDown={event => {
          const hit = pickCharacter(event.clientX, event.clientY);
          if (hit) {
            onSelectAgent(hit, event.currentTarget);
            return;
          }
          if (event.button === 2 && selectedAgentId) {
            const tile = pickTile(event.clientX, event.clientY);
            if (tile) engineRef.current.moveAgentTo(selectedAgentId, tile.col, tile.row);
            return;
          }
          dragRef.current = {
            x: event.clientX,
            y: event.clientY,
            cameraX: cameraRef.current.x,
            cameraY: cameraRef.current.y,
            moved: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          hoveredRef.current = pickCharacter(event.clientX, event.clientY);
          if (!dragRef.current) return;
          const dpr = window.devicePixelRatio || 1;
          const dx = (event.clientX - dragRef.current.x) * dpr;
          const dy = (event.clientY - dragRef.current.y) * dpr;
          dragRef.current.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
          cameraRef.current = {
            x: dragRef.current.cameraX + dx,
            y: dragRef.current.cameraY + dy,
          };
        }}
        onPointerLeave={() => {
          hoveredRef.current = '';
        }}
        onPointerUp={event => {
          dragRef.current = null;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          dragRef.current = null;
        }}
        onContextMenu={event => event.preventDefault()}
      />

      <div className="iso-room-heading" aria-live="polite">
        <span>{language === 'ru' ? room.shortLabel.ru : room.shortLabel.en}</span>
        <strong>{language === 'ru' ? room.label.ru : room.label.en}</strong>
        <small>{language === 'ru' ? room.description.ru : room.description.en}</small>
      </div>

      <nav className="iso-room-switcher" aria-label={language === 'ru' ? 'Комнаты офиса' : 'Office rooms'}>
        {ISO_ROOMS.map(item => {
          const Icon = ROOM_ICONS[item.id];
          return (
            <button
              key={item.id}
              type="button"
              className={room.id === item.id ? 'is-active' : ''}
              onClick={() => setRoomId(item.id)}
              aria-pressed={room.id === item.id}
              title={language === 'ru' ? item.label.ru : item.label.en}
            >
              <Icon size={16} />
              <span>{language === 'ru' ? item.shortLabel.ru : item.shortLabel.en}</span>
              <b>{roomCounts[item.id]}</b>
            </button>
          );
        })}
      </nav>

      {onTheme && (
        <div className="pixel-theme-switcher">
          <button
            type="button"
            className={`pixel-theme-toggle${themeMenuOpen ? ' is-active' : ''}`}
            onClick={() => setThemeMenuOpen(value => !value)}
            title={language === 'ru' ? 'Цвет интерфейса' : 'Interface colour'}
            aria-haspopup="true"
            aria-expanded={themeMenuOpen}
            style={{ '--theme-accent': palette.accent } as React.CSSProperties}
          >
            <Palette size={16} />
          </button>
          {themeMenuOpen && (
            <div className="pixel-theme-menu" role="menu">
              {(Object.keys(OFFICE_THEMES) as OfficeThemeKey[]).map(key => (
                <button
                  key={key}
                  type="button"
                  role="menuitemradio"
                  aria-checked={theme === key}
                  className={theme === key ? 'is-active' : ''}
                  onClick={() => {
                    onTheme(key);
                    setThemeMenuOpen(false);
                  }}
                >
                  <span className="pixel-theme-dot" style={{ background: OFFICE_THEMES[key].accent }} />
                  {OFFICE_THEMES[key].label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="pixel-canvas-status iso-canvas-status" aria-hidden="true">
        <span>LIVE</span>
        <i />
        {roomCounts[room.id]}
      </div>
    </div>
  );
}
