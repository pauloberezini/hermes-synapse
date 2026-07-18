import { Palette } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CanvasOfficeEngine,
  createDefaultCanvasLayout,
  FURNITURE_CATALOG,
  normalizeCanvasLayout,
  OFFICE_LAYOUT_STORAGE_KEY,
  type CanvasAgentData,
  type CanvasCharacter,
  type CanvasLiveTrace,
} from './officeCanvasEngine';
import {
  FURNITURE_ISO,
  furnitureDepth,
  ISO_TILE_H,
  ISO_TILE_W,
  isoToTile,
  isoWorldBounds,
  loadIsoManifest,
  tileToIso,
  type IsoAssetManifest,
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

const CHARACTER_ASSETS = Array.from({ length: 6 }, (_, index) => `/pixel-agents-assets/characters/char_${index}.png`);
const STATUS_COLORS = { working: '#2ecc71', waiting: '#f4c430', error: '#ff4d5e', paused: '#b06ef7', offline: '#7d8aa5' } as const;
const SPEECH_COLORS = { info: '#4f6ef7', success: '#2ecc71', error: '#ff4d5e' } as const;
const SPECIALIST_COLORS: Record<string, string> = {
  Debugger: '#ff6b6b', Reviewer: '#c792ea', Frontend: '#4fc3f7', Tester: '#ffd166', Security: '#ff5e8a',
  DevOps: '#5ad1c0', PerfEng: '#ffa94d', DBA: '#8d9eff', Researcher: '#63e6be', 'AI Eng': '#b197fc', Fullstack: '#74c0fc', Architect: '#ffc078',
};
const MAX_WALL_H = 46;

// Isometric character sprites from the MIT-licensed Claude-Office project (see
// public/iso-office-assets/CREDITS.md). Each character has four directional poses.
const ISO_CHAR_ROOT = '/iso-office-assets/characters';
const ISO_CHAR_ASPECT = 432 / 880;
const SPECIALIST_TO_SPRITE: Record<string, string> = {
  Frontend: 'Frontend-dev-1', Security: 'security-audit-1', Researcher: 'explore-1', Debugger: 'dev-1',
  DevOps: 'dev-2', 'AI Eng': 'Claude-1', Architect: 'Claude-1', Reviewer: 'dev-1', Fullstack: 'dev-1',
  Tester: 'employee-3', DBA: 'employee-2', PerfEng: 'dev-2',
};
const SPRITE_POOL = ['employee-1', 'employee-2', 'employee-3', 'dev-1', 'dev-2', 'explore-1'];

function hashString(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) { hash ^= value.charCodeAt(index); hash = Math.imul(hash, 16777619); }
  return Math.abs(hash);
}

function isoSpriteBase(character: CanvasCharacter): string {
  const id = character.agent.id.toLowerCase();
  const name = (character.agent.name || '').toLowerCase();
  if (id === 'jarvis' || name.includes('jarvis') || name.includes('claude')) return 'Claude-1';
  if (character.specialist && SPECIALIST_TO_SPRITE[character.specialist]) return SPECIALIST_TO_SPRITE[character.specialist];
  return SPRITE_POOL[hashString(character.agent.id) % SPRITE_POOL.length];
}

function isoDirSuffix(direction: CanvasCharacter['direction']): string {
  if (direction === 'down') return 'front-left';
  if (direction === 'right') return 'front-right';
  if (direction === 'up') return 'rear-right';
  return 'rear-left';
}

function loadStoredLayout() {
  try {
    return normalizeCanvasLayout(JSON.parse(localStorage.getItem(OFFICE_LAYOUT_STORAGE_KEY) || 'null'));
  } catch {
    return createDefaultCanvasLayout();
  }
}

function imageFor(cache: Map<string, HTMLImageElement>, src: string) {
  let image = cache.get(src);
  if (!image) {
    image = new Image();
    image.src = src;
    cache.set(src, image);
  }
  return image;
}

function wrapPixelText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number) {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (ctx.measureText(candidate).width > maxWidth && line) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines) break;
    } else line = candidate;
  }
  if (lines.length < maxLines && line) lines.push(line);
  const consumed = lines.join(' ').split(/\s+/).length;
  if (lines.length === maxLines && consumed < words.length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[.,;:\s]+$/, '')}…`;
  }
  return lines;
}

/** Slightly lighten/darken a hex colour for isometric face shading. */
function shade(hex: string, amount: number) {
  const value = hex.replace('#', '');
  const num = parseInt(value.length === 3 ? value.replace(/(.)/g, '$1$1') : value, 16);
  const r = Math.max(0, Math.min(255, ((num >> 16) & 255) + amount));
  const g = Math.max(0, Math.min(255, ((num >> 8) & 255) + amount));
  const b = Math.max(0, Math.min(255, (num & 255) + amount));
  return `rgb(${r},${g},${b})`;
}

export function IsoOfficeCanvas({ agents, selectedAgentId, onSelectAgent, zoom, onZoom, language, liveTrace, theme = 'hermes', onTheme }: IsoOfficeCanvasProps) {
  const initialLayout = useMemo(() => loadStoredLayout(), []);
  const engineRef = useRef(new CanvasOfficeEngine(initialLayout));
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const imagesRef = useRef(new Map<string, HTMLImageElement>());
  const cameraRef = useRef({ x: 0, y: 0 });
  const viewportRef = useRef({ originX: 0, originY: 0, scale: 1 });
  const spritesRef = useRef(new Map<string, { x: number; y: number; w: number; h: number }>());
  const dragRef = useRef<{ x: number; y: number; cameraX: number; cameraY: number; moved: boolean } | null>(null);
  const hoveredRef = useRef('');
  const manifestRef = useRef<IsoAssetManifest | null>(null);
  const palette = OFFICE_THEMES[theme] ?? OFFICE_THEMES.hermes;
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);

  useEffect(() => { engineRef.current.setAgents(agents); }, [agents]);
  useEffect(() => { if (liveTrace) engineRef.current.applyTrace(liveTrace); }, [liveTrace]);
  useEffect(() => { void loadIsoManifest().then(manifest => { manifestRef.current = manifest; }); }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const shell = shellRef.current;
    if (!canvas || !shell) return;
    let frameId = 0;
    let lastTime = 0;
    const resize = () => {
      const rect = shell.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(rect.width * dpr));
      const height = Math.max(1, Math.round(rect.height * dpr));
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
      const layout = engine.layout;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.fillStyle = palette.background;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const bounds = isoWorldBounds(layout.cols, layout.rows);
      const pad = 24;
      const worldW = bounds.maxX - bounds.minX;
      const worldH = (bounds.maxY - bounds.minY) + MAX_WALL_H;
      const fit = Math.max(.35, Math.min((canvas.width - pad * 2) / worldW, (canvas.height - pad * 2) / worldH));
      const scale = fit * zoom;
      const originX = (canvas.width - worldW * scale) / 2 - bounds.minX * scale + cameraRef.current.x;
      const originY = (canvas.height - worldH * scale) / 2 + MAX_WALL_H * scale + cameraRef.current.y;
      viewportRef.current = { originX, originY, scale };

      const proj = (tx: number, ty: number) => {
        const iso = tileToIso(tx, ty);
        return { X: originX + iso.x * scale, Y: originY + iso.y * scale };
      };
      const halfW = (ISO_TILE_W / 2) * scale;
      const halfH = (ISO_TILE_H / 2) * scale;

      // ── Floor pass (flat, no mutual occlusion) ──
      layout.tiles.forEach((tile, index) => {
        if (tile === 0) return;
        const col = index % layout.cols;
        const row = Math.floor(index / layout.cols);
        const top = proj(col, row);
        const base = tile === 4 ? '#3a3342' : tile === 7 ? '#26424a' : tile === 2 ? '#2b3550' : '#323b4c';
        ctx.beginPath();
        ctx.moveTo(top.X, top.Y);
        ctx.lineTo(top.X + halfW, top.Y + halfH);
        ctx.lineTo(top.X, top.Y + halfH * 2);
        ctx.lineTo(top.X - halfW, top.Y + halfH);
        ctx.closePath();
        ctx.fillStyle = base;
        ctx.fill();
        if (palette.floorWash !== 'rgba(24,31,44,.0)') { ctx.fillStyle = palette.floorWash; ctx.fill(); }
        ctx.strokeStyle = 'rgba(0,0,0,.18)';
        ctx.lineWidth = Math.max(.5, scale * .5);
        ctx.stroke();
      });

      // ── Depth-sorted solids (walls, furniture, characters) ──
      const drawBox = (col: number, row: number, fw: number, fh: number, heightPx: number, top: string, left: string, right: string) => {
        const h = heightPx * scale;
        const A = proj(col, row);         // back
        const B = proj(col + fw, row);    // right
        const C = proj(col + fw, row + fh); // front
        const D = proj(col, row + fh);    // left
        // left face
        ctx.beginPath();
        ctx.moveTo(D.X, D.Y); ctx.lineTo(C.X, C.Y); ctx.lineTo(C.X, C.Y - h); ctx.lineTo(D.X, D.Y - h); ctx.closePath();
        ctx.fillStyle = left; ctx.fill();
        // right face
        ctx.beginPath();
        ctx.moveTo(C.X, C.Y); ctx.lineTo(B.X, B.Y); ctx.lineTo(B.X, B.Y - h); ctx.lineTo(C.X, C.Y - h); ctx.closePath();
        ctx.fillStyle = right; ctx.fill();
        // top face
        ctx.beginPath();
        ctx.moveTo(A.X, A.Y - h); ctx.lineTo(B.X, B.Y - h); ctx.lineTo(C.X, C.Y - h); ctx.lineTo(D.X, D.Y - h); ctx.closePath();
        ctx.fillStyle = top; ctx.fill();
      };

      const drawables: Array<{ depth: number; layer: number; draw: () => void }> = [];

      // Walls: far edges (row 0 / col 0) full height; interior dividers as cubicle height; near edges omitted so the room is open.
      layout.tiles.forEach((tile, index) => {
        if (tile !== 0) return;
        const col = index % layout.cols;
        const row = Math.floor(index / layout.cols);
        const isFar = row === 0 || col === 0;
        const isNear = row === layout.rows - 1 || col === layout.cols - 1;
        if (isNear && !isFar) return;
        const height = isFar ? MAX_WALL_H : 20;
        drawables.push({ depth: col + row, layer: 0, draw: () => drawBox(col, row, 1, 1, height, shade(palette.wallTint, 18), shade(palette.wallTint, -22), shade(palette.wallTint, 6)) });
      });

      // Furniture volumes.
      layout.furniture.forEach(item => {
        const spec = FURNITURE_CATALOG[item.kind];
        const vol = FURNITURE_ISO[item.kind];
        drawables.push({
          depth: furnitureDepth(item.kind, item.col, item.row),
          layer: 1,
          draw: () => drawBox(item.col, item.row, spec.footprintW, spec.footprintH, vol.height, vol.top, vol.dark, vol.light),
        });
      });

      // Characters as upright billboards.
      const drawCharacter = (character: CanvasCharacter, tx: number, ty: number) => {
        const ground = proj(tx, ty);
        const gy = ground.Y + halfH; // sit on the tile centre
        const isoSrc = `${ISO_CHAR_ROOT}/${isoSpriteBase(character)}-${isoDirSuffix(character.direction)}.png`;
        const image = imageFor(imagesRef.current, isoSrc);
        const spriteH = 58 * scale;
        const spriteW = spriteH * ISO_CHAR_ASPECT;
        const drawX = ground.X - spriteW / 2;
        const drawY = gy - spriteH;
        const selected = selectedAgentId === character.agent.id;
        const hovered = hoveredRef.current === character.agent.id;
        // ground shadow
        ctx.beginPath();
        ctx.ellipse(ground.X, gy, spriteW * .42, spriteW * .18, 0, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(0,0,0,.34)'; ctx.fill();
        if (selected || hovered) {
          ctx.beginPath();
          ctx.ellipse(ground.X, gy, spriteW * (selected ? .5 : .44), spriteW * (selected ? .22 : .19), 0, 0, Math.PI * 2);
          ctx.strokeStyle = selected ? palette.accent : 'rgba(230,235,245,.6)';
          ctx.lineWidth = Math.max(1, scale); ctx.stroke();
        }
        if (character.spawnTimer > 0) ctx.globalAlpha = Math.max(.2, 1 - character.spawnTimer / .7);
        if (character.lifecycle === 'leaving') ctx.globalAlpha = Math.min(ctx.globalAlpha, .55);
        if (image.complete && image.naturalWidth) ctx.drawImage(image, drawX, drawY, spriteW, spriteH);
        else {
          const fallback = imageFor(imagesRef.current, CHARACTER_ASSETS[character.palette]);
          if (fallback.complete && fallback.naturalWidth) ctx.drawImage(fallback, 0, 0, 16, 32, ground.X - 8 * scale, gy - 30 * scale, 16 * scale, 30 * scale);
          else { ctx.fillStyle = '#7d8aa5'; ctx.fillRect(ground.X - 6 * scale, gy - 26 * scale, 12 * scale, 26 * scale); }
        }
        ctx.globalAlpha = 1;
        spritesRef.current.set(character.agent.id, { x: drawX, y: drawY, w: spriteW, h: spriteH });
        // status dot
        ctx.fillStyle = STATUS_COLORS[character.agent.statusKind];
        ctx.fillRect(ground.X - 1.5 * scale, gy + 1 * scale, 3 * scale, Math.max(1, scale));

        if (character.specialist && (selected || hovered || character.speech)) {
          const chipColor = SPECIALIST_COLORS[character.specialist] || palette.accent;
          ctx.font = `700 ${Math.max(8, 4.5 * scale)}px Inter, sans-serif`;
          const chipW = ctx.measureText(character.specialist).width + 8 * scale;
          const chipX = ground.X - chipW / 2;
          const chipY = gy + 4 * scale;
          ctx.fillStyle = 'rgba(8,12,18,.9)'; ctx.fillRect(chipX, chipY, chipW, 8 * scale);
          ctx.fillStyle = chipColor; ctx.fillRect(chipX, chipY, Math.max(1, 1.5 * scale), 8 * scale);
          ctx.fillStyle = chipColor; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(character.specialist, chipX + chipW / 2 + scale, chipY + 4 * scale);
        }

        if (character.speech) {
          const accent = SPEECH_COLORS[character.speech.kind];
          ctx.font = `600 ${Math.max(8, 4.6 * scale)}px Inter, sans-serif`;
          const maxWidth = 100 * scale;
          const lines = wrapPixelText(ctx, character.speech.text, maxWidth - 8 * scale, 2);
          const lineH = Math.max(8, 6 * scale);
          const boxW = Math.min(maxWidth, Math.max(...lines.map(line => ctx.measureText(line).width)) + 8 * scale);
          const boxH = lines.length * lineH + 5 * scale;
          const boxX = ground.X - boxW / 2;
          const boxY = drawY - boxH - 6 * scale;
          ctx.fillStyle = 'rgba(243,245,248,.97)'; ctx.fillRect(boxX, boxY, boxW, boxH);
          ctx.fillStyle = accent; ctx.fillRect(boxX, boxY, boxW, Math.max(1, 1.5 * scale));
          ctx.beginPath();
          ctx.moveTo(ground.X - 3 * scale, boxY + boxH); ctx.lineTo(ground.X + 3 * scale, boxY + boxH); ctx.lineTo(ground.X, boxY + boxH + 4 * scale); ctx.closePath();
          ctx.fillStyle = 'rgba(243,245,248,.97)'; ctx.fill();
          ctx.fillStyle = '#141821'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          lines.forEach((line, i) => ctx.fillText(line, ground.X, boxY + 4 * scale + i * lineH + lineH / 2));
        } else if (character.agent.statusKind !== 'working') {
          const glyph = character.agent.statusKind === 'waiting' ? '…' : character.agent.statusKind === 'error' ? '!' : character.agent.statusKind === 'paused' ? 'Ⅱ' : 'Z';
          ctx.fillStyle = '#f3f5f8'; ctx.fillRect(ground.X + 3 * scale, drawY - 2 * scale, 9 * scale, 8 * scale);
          ctx.fillStyle = STATUS_COLORS[character.agent.statusKind];
          ctx.font = `800 ${Math.max(7, 5 * scale)}px monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(glyph, ground.X + 7.5 * scale, drawY + 2 * scale);
        }

        if (selected || hovered) {
          ctx.font = `700 ${Math.max(9, 5 * scale)}px Inter, sans-serif`;
          const label = character.agent.name;
          const width = Math.min(180 * scale, ctx.measureText(label).width + 12 * scale);
          const labelY = drawY - (character.speech ? 0 : 12 * scale);
          ctx.fillStyle = selected ? 'rgba(28,24,58,.96)' : 'rgba(8,12,18,.92)';
          ctx.fillRect(ground.X - width / 2, labelY, width, 10 * scale);
          if (selected) { ctx.fillStyle = palette.accent; ctx.fillRect(ground.X - width / 2, labelY, width, Math.max(1, scale)); }
          ctx.fillStyle = '#e6ebf5'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(label, ground.X, labelY + 5 * scale, width - 6 * scale);
        }
      };

      spritesRef.current.clear();
      engine.characters.forEach(character => {
        drawables.push({ depth: character.x / 16 + character.y / 16, layer: 2, draw: () => drawCharacter(character, character.x / 16, character.y / 16) });
      });

      drawables.sort((a, b) => a.depth - b.depth || a.layer - b.layer).forEach(item => item.draw());
      frameId = requestAnimationFrame(render);
    };
    frameId = requestAnimationFrame(render);
    return () => { cancelAnimationFrame(frameId); observer.disconnect(); };
  }, [language, selectedAgentId, theme, zoom]);

  const pickCharacter = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return '';
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = (clientX - rect.left) * dpr;
    const y = (clientY - rect.top) * dpr;
    let best = '';
    let bestY = -Infinity;
    spritesRef.current.forEach((box, id) => {
      if (x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h && box.y > bestY) { best = id; bestY = box.y; }
    });
    return best;
  };

  const pickTile = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const { originX, originY, scale } = viewportRef.current;
    const x = ((clientX - rect.left) * dpr - originX) / scale;
    const y = ((clientY - rect.top) * dpr - originY) / scale - ISO_TILE_H / 2;
    const { tx, ty } = isoToTile(x, y);
    const col = Math.floor(tx);
    const row = Math.floor(ty);
    const layout = engineRef.current.layout;
    if (col < 0 || row < 0 || col >= layout.cols || row >= layout.rows) return null;
    return { col, row };
  };

  return (
    <div ref={shellRef} className="pixel-canvas-shell iso-canvas-shell">
      <canvas
        ref={canvasRef}
        className="pixel-office-canvas"
        role="img"
        aria-label={language === 'ru' ? 'Изометрический офис агентов' : 'Isometric agent office'}
        tabIndex={0}
        onWheel={event => { event.preventDefault(); onZoom(Math.max(.6, Math.min(1.8, zoom + (event.deltaY < 0 ? .1 : -.1)))); }}
        onPointerDown={event => {
          const hit = pickCharacter(event.clientX, event.clientY);
          if (hit) { onSelectAgent(hit, event.currentTarget); return; }
          if (event.button === 2 && selectedAgentId) { const tile = pickTile(event.clientX, event.clientY); if (tile) engineRef.current.moveAgentTo(selectedAgentId, tile.col, tile.row); return; }
          dragRef.current = { x: event.clientX, y: event.clientY, cameraX: cameraRef.current.x, cameraY: cameraRef.current.y, moved: false };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          hoveredRef.current = pickCharacter(event.clientX, event.clientY);
          if (!dragRef.current) return;
          const dpr = window.devicePixelRatio || 1;
          const dx = (event.clientX - dragRef.current.x) * dpr;
          const dy = (event.clientY - dragRef.current.y) * dpr;
          dragRef.current.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
          cameraRef.current = { x: dragRef.current.cameraX + dx, y: dragRef.current.cameraY + dy };
        }}
        onPointerUp={event => { dragRef.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { dragRef.current = null; }}
        onContextMenu={event => event.preventDefault()}
      />
      {onTheme && (
        <div className="pixel-theme-switcher">
          <button type="button" className={`pixel-theme-toggle${themeMenuOpen ? ' is-active' : ''}`} onClick={() => setThemeMenuOpen(value => !value)} title={language === 'ru' ? 'Тема офиса' : 'Office theme'} aria-haspopup="true" aria-expanded={themeMenuOpen} style={{ '--theme-accent': palette.accent } as React.CSSProperties}><Palette size={16} /></button>
          {themeMenuOpen && (
            <div className="pixel-theme-menu" role="menu">
              {(Object.keys(OFFICE_THEMES) as OfficeThemeKey[]).map(key => (
                <button key={key} type="button" role="menuitemradio" aria-checked={theme === key} className={theme === key ? 'is-active' : ''} onClick={() => { onTheme(key); setThemeMenuOpen(false); }}>
                  <span className="pixel-theme-dot" style={{ background: OFFICE_THEMES[key].accent }} />{OFFICE_THEMES[key].label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="pixel-canvas-status" aria-hidden="true"><span>ISO</span><i />{agents.length}</div>
    </div>
  );
}
