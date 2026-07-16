import { Armchair, BrickWall, Download, Eraser, MousePointer2, PaintBucket, Redo2, RotateCcw, Trash2, Undo2, Upload } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CanvasOfficeEngine,
  cloneOfficeLayout,
  createDefaultCanvasLayout,
  FURNITURE_CATALOG,
  getWallMask,
  normalizeCanvasLayout,
  OFFICE_LAYOUT_STORAGE_KEY,
  OFFICE_TILE_SIZE,
  type CanvasAgentData,
  type CanvasCharacter,
  type CanvasDirection,
  type CanvasOfficeLayout,
  type FurnitureKind,
} from './officeCanvasEngine';

type EditorTool = 'select' | 'floor' | 'wall' | 'furniture' | 'erase';

interface PixelOfficeCanvasProps {
  agents: CanvasAgentData[];
  selectedAgentId: string;
  onSelectAgent: (id: string, trigger: HTMLElement) => void;
  zoom: number;
  onZoom: (zoom: number) => void;
  language: 'en' | 'ru';
}

const FLOOR_ASSETS = Array.from({ length: 9 }, (_, index) => `/pixel-agents-assets/floors/floor_${index}.png`);
const CHARACTER_ASSETS = Array.from({ length: 6 }, (_, index) => `/pixel-agents-assets/characters/char_${index}.png`);
const WALL_ASSET = '/pixel-agents-assets/walls/wall_0.png';
const STATUS_COLORS = { working: '#2ecc71', waiting: '#f4c430', error: '#ff4d5e', paused: '#b06ef7', offline: '#7d8aa5' } as const;
const FURNITURE_KINDS = Object.keys(FURNITURE_CATALOG) as FurnitureKind[];

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

function tintWallSheet(image: HTMLImageElement) {
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(image, 0, 0);
  context.globalCompositeOperation = 'multiply';
  context.fillStyle = '#465264';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.globalCompositeOperation = 'source-over';
  return canvas;
}

function characterFrame(character: CanvasCharacter) {
  if (character.state === 'rest') return 3;
  if (character.state === 'type') return 3 + (character.frame % 2);
  if (character.state === 'read') return 5 + (character.frame % 2);
  if (character.state === 'walk') return [0, 1, 2, 1][character.frame % 4];
  return 0;
}

function directionRow(direction: CanvasDirection) {
  if (direction === 'up') return 1;
  if (direction === 'left' || direction === 'right') return 2;
  return 0;
}

function statusBubble(character: CanvasCharacter, language: 'en' | 'ru') {
  if (character.agent.statusKind === 'waiting') return { text: '…', label: language === 'ru' ? 'Ожидает' : 'Waiting' };
  if (character.agent.statusKind === 'error') return { text: '!', label: language === 'ru' ? 'Ошибка' : 'Error' };
  if (character.agent.statusKind === 'paused') return { text: 'Ⅱ', label: language === 'ru' ? 'Пауза' : 'Paused' };
  if (character.agent.statusKind === 'offline') return { text: 'Z', label: language === 'ru' ? 'Неактивен' : 'Offline' };
  return null;
}

export function PixelOfficeCanvas({ agents, selectedAgentId, onSelectAgent, zoom, onZoom, language }: PixelOfficeCanvasProps) {
  const initialLayout = useMemo(loadStoredLayout, []);
  const engineRef = useRef(new CanvasOfficeEngine(initialLayout));
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const imagesRef = useRef(new Map<string, HTMLImageElement>());
  const tintedWallsRef = useRef<HTMLCanvasElement | null>(null);
  const cameraRef = useRef({ x: 0, y: 0 });
  const viewportRef = useRef({ offsetX: 0, offsetY: 0, scale: 1 });
  const dragRef = useRef<{ x: number; y: number; cameraX: number; cameraY: number; moved: boolean } | null>(null);
  const hoveredRef = useRef<string>('');
  const undoRef = useRef<CanvasOfficeLayout[]>([]);
  const redoRef = useRef<CanvasOfficeLayout[]>([]);
  const importRef = useRef<HTMLInputElement | null>(null);
  const [layout, setLayoutState] = useState(initialLayout);
  const [editorOpen, setEditorOpen] = useState(false);
  const [tool, setTool] = useState<EditorTool>('select');
  const [floor, setFloor] = useState(1);
  const [furniture, setFurniture] = useState<FurnitureKind>('DESK_FRONT');
  const [selectedFurniture, setSelectedFurniture] = useState('');
  const [historyTick, setHistoryTick] = useState(0);

  useEffect(() => { engineRef.current.setAgents(agents); }, [agents]);

  const commitLayout = useCallback((next: CanvasOfficeLayout, keepRedo = false) => {
    undoRef.current.push(cloneOfficeLayout(engineRef.current.layout));
    if (undoRef.current.length > 50) undoRef.current.shift();
    if (!keepRedo) redoRef.current = [];
    engineRef.current.setLayout(next);
    setLayoutState(cloneOfficeLayout(next));
    localStorage.setItem(OFFICE_LAYOUT_STORAGE_KEY, JSON.stringify(next));
    setHistoryTick(value => value + 1);
  }, []);

  const undo = useCallback(() => {
    const previous = undoRef.current.pop();
    if (!previous) return;
    redoRef.current.push(cloneOfficeLayout(engineRef.current.layout));
    engineRef.current.setLayout(previous);
    setLayoutState(cloneOfficeLayout(previous));
    localStorage.setItem(OFFICE_LAYOUT_STORAGE_KEY, JSON.stringify(previous));
    setHistoryTick(value => value + 1);
  }, []);

  const redo = useCallback(() => {
    const next = redoRef.current.pop();
    if (!next) return;
    undoRef.current.push(cloneOfficeLayout(engineRef.current.layout));
    engineRef.current.setLayout(next);
    setLayoutState(cloneOfficeLayout(next));
    localStorage.setItem(OFFICE_LAYOUT_STORAGE_KEY, JSON.stringify(next));
    setHistoryTick(value => value + 1);
  }, []);

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
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.fillStyle = '#080c12';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const worldWidth = engine.layout.cols * OFFICE_TILE_SIZE;
      const worldHeight = engine.layout.rows * OFFICE_TILE_SIZE;
      const fit = Math.max(.5, Math.min((canvas.width - 28) / worldWidth, (canvas.height - 28) / worldHeight));
      const scale = fit * zoom;
      const offsetX = Math.round((canvas.width - worldWidth * scale) / 2 + cameraRef.current.x);
      const offsetY = Math.round((canvas.height - worldHeight * scale) / 2 + cameraRef.current.y);
      viewportRef.current = { offsetX, offsetY, scale };

      engine.layout.tiles.forEach((tile, index) => {
        const col = index % engine.layout.cols;
        const row = Math.floor(index / engine.layout.cols);
        const x = offsetX + col * OFFICE_TILE_SIZE * scale;
        const y = offsetY + row * OFFICE_TILE_SIZE * scale;
        if (tile === 0) {
          ctx.fillStyle = '#1a2333';
          ctx.fillRect(x, y, OFFICE_TILE_SIZE * scale, OFFICE_TILE_SIZE * scale);
          ctx.fillStyle = row === 0 ? '#28324a' : '#202a3d';
          ctx.fillRect(x, y, OFFICE_TILE_SIZE * scale, Math.max(2, 3 * scale));
        } else {
          const floorImage = imageFor(imagesRef.current, FLOOR_ASSETS[(tile - 1) % FLOOR_ASSETS.length]);
          if (floorImage.complete) {
            ctx.drawImage(floorImage, x, y, OFFICE_TILE_SIZE * scale, OFFICE_TILE_SIZE * scale);
            ctx.fillStyle = tile === 4 ? 'rgba(36,22,45,.38)' : tile === 7 ? 'rgba(16,41,48,.42)' : tile === 2 ? 'rgba(31,38,54,.38)' : 'rgba(24,31,44,.42)';
            ctx.fillRect(x, y, OFFICE_TILE_SIZE * scale, OFFICE_TILE_SIZE * scale);
          }
          else { ctx.fillStyle = tile === 4 ? '#3a3342' : tile === 7 ? '#263d46' : '#303948'; ctx.fillRect(x, y, OFFICE_TILE_SIZE * scale, OFFICE_TILE_SIZE * scale); }
        }
      });

      const drawables: Array<{ z: number; draw: () => void }> = [];
      const wallImage = imageFor(imagesRef.current, WALL_ASSET);
      if (!tintedWallsRef.current && wallImage.complete && wallImage.naturalWidth) tintedWallsRef.current = tintWallSheet(wallImage);
      engine.layout.tiles.forEach((tile, index) => {
        if (tile !== 0) return;
        const col = index % engine.layout.cols;
        const row = Math.floor(index / engine.layout.cols);
        const mask = getWallMask(engine.layout, col, row);
        const x = offsetX + col * OFFICE_TILE_SIZE * scale;
        const y = offsetY + (row * OFFICE_TILE_SIZE - OFFICE_TILE_SIZE) * scale;
        drawables.push({ z: (row + 1) * OFFICE_TILE_SIZE, draw: () => {
          const source = tintedWallsRef.current;
          if (source) ctx.drawImage(source, (mask % 4) * 16, Math.floor(mask / 4) * 32, 16, 32, x, y, 16 * scale, 32 * scale);
        } });
      });
      engine.layout.furniture.forEach(item => {
        const spec = FURNITURE_CATALOG[item.kind];
        let src: string = spec.src;
        if ('electronics' in spec && spec.electronics && 'animated' in spec && spec.animated) {
          const active = [...engine.characters.values()].some(character => character.agent.statusKind === 'working' && Math.abs(character.col - item.col) <= 2 && Math.abs(character.row - item.row) <= 3);
          if (active) src = spec.animated[Math.floor(time / 360) % spec.animated.length];
        }
        const image = imageFor(imagesRef.current, src);
        const x = offsetX + item.col * OFFICE_TILE_SIZE * scale;
        const y = offsetY + ((item.row + spec.footprintH) * OFFICE_TILE_SIZE - spec.height) * scale;
        drawables.push({ z: (item.row + spec.footprintH) * OFFICE_TILE_SIZE, draw: () => { if (image.complete) ctx.drawImage(image, x, y, spec.width * scale, spec.height * scale); } });
      });

      engine.characters.forEach(character => {
        drawables.push({ z: character.y + 8, draw: () => {
          const image = imageFor(imagesRef.current, CHARACTER_ASSETS[character.palette]);
          if (!image.complete) return;
          const drawX = Math.round(offsetX + (character.x - 8) * scale);
          const sittingOffset = character.state === 'type' || character.state === 'read' || character.state === 'rest' ? 5 : 0;
          const drawY = Math.round(offsetY + (character.y - 24 + sittingOffset) * scale);
          const sx = characterFrame(character) * 16;
          const sy = directionRow(character.direction) * 32;
          const selected = selectedAgentId === character.agent.id;
          const hovered = hoveredRef.current === character.agent.id;
          if (selected || hovered) {
            ctx.beginPath();
            ctx.ellipse(drawX + 8 * scale, drawY + 29 * scale, (selected ? 9 : 7) * scale, (selected ? 4 : 3) * scale, 0, 0, Math.PI * 2);
            ctx.fillStyle = selected ? 'rgba(137,118,255,.28)' : 'rgba(230,235,245,.15)';
            ctx.fill();
            ctx.strokeStyle = selected ? '#9b88ff' : 'rgba(230,235,245,.58)';
            ctx.lineWidth = Math.max(1, scale);
            ctx.stroke();
          }
          ctx.save();
          if (character.spawnTimer > 0) ctx.globalAlpha = Math.max(.15, 1 - character.spawnTimer / .7);
          if (character.direction === 'left') {
            ctx.translate(drawX + 16 * scale, 0);
            ctx.scale(-1, 1);
            ctx.drawImage(image, sx, sy, 16, 32, 0, drawY, 16 * scale, 32 * scale);
          } else ctx.drawImage(image, sx, sy, 16, 32, drawX, drawY, 16 * scale, 32 * scale);
          ctx.restore();

          if (selected || hovered) {
            ctx.font = `700 ${Math.max(9, 5 * scale)}px Inter, sans-serif`;
            const label = character.agent.name;
            const width = Math.min(180 * scale, ctx.measureText(label).width + 12 * scale);
            const labelX = Math.round(offsetX + character.x * scale - width / 2);
            const labelY = drawY - 10 * scale;
            ctx.fillStyle = selected ? 'rgba(28,24,58,.96)' : 'rgba(8,12,18,.92)'; ctx.fillRect(labelX, labelY, width, 10 * scale);
            if (selected) { ctx.fillStyle = '#9b88ff'; ctx.fillRect(labelX, labelY, width, Math.max(1, scale)); }
            ctx.fillStyle = '#e6ebf5'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(label, labelX + width / 2, labelY + 5 * scale, width - 6 * scale);
          }

          const bubble = statusBubble(character, language);
          if (bubble) {
            const bubbleX = Math.round(offsetX + (character.x + 5) * scale);
            const bubbleY = Math.round(offsetY + (character.y - 30) * scale);
            ctx.fillStyle = '#f3f5f8'; ctx.fillRect(bubbleX, bubbleY, 10 * scale, 9 * scale);
            ctx.fillStyle = STATUS_COLORS[character.agent.statusKind]; ctx.fillRect(bubbleX + 2 * scale, bubbleY + 2 * scale, 6 * scale, 5 * scale);
            ctx.fillStyle = '#0b0f17'; ctx.font = `800 ${Math.max(8, 5 * scale)}px monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(bubble.text, bubbleX + 5 * scale, bubbleY + 4.5 * scale);
          }
          ctx.fillStyle = STATUS_COLORS[character.agent.statusKind];
          ctx.fillRect(Math.round(offsetX + (character.x - 2) * scale), Math.round(offsetY + (character.y + 7) * scale), 4 * scale, Math.max(1, scale));
        } });
      });
      drawables.sort((a, b) => a.z - b.z).forEach(item => item.draw());

      if (editorOpen) {
        ctx.strokeStyle = 'rgba(79,110,247,.22)'; ctx.lineWidth = 1;
        for (let col = 0; col <= engine.layout.cols; col += 1) { const x = offsetX + col * OFFICE_TILE_SIZE * scale + .5; ctx.beginPath(); ctx.moveTo(x, offsetY); ctx.lineTo(x, offsetY + worldHeight * scale); ctx.stroke(); }
        for (let row = 0; row <= engine.layout.rows; row += 1) { const y = offsetY + row * OFFICE_TILE_SIZE * scale + .5; ctx.beginPath(); ctx.moveTo(offsetX, y); ctx.lineTo(offsetX + worldWidth * scale, y); ctx.stroke(); }
      }
      frameId = requestAnimationFrame(render);
    };
    frameId = requestAnimationFrame(render);
    return () => { cancelAnimationFrame(frameId); observer.disconnect(); };
  }, [editorOpen, historyTick, language, selectedAgentId, zoom]);

  const screenToTile = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const x = (clientX - rect.left) * dpr;
    const y = (clientY - rect.top) * dpr;
    const { offsetX, offsetY, scale } = viewportRef.current;
    const col = Math.floor((x - offsetX) / (OFFICE_TILE_SIZE * scale));
    const row = Math.floor((y - offsetY) / (OFFICE_TILE_SIZE * scale));
    if (col < 0 || row < 0 || col >= engineRef.current.layout.cols || row >= engineRef.current.layout.rows) return null;
    return { col, row, worldX: (x - offsetX) / scale, worldY: (y - offsetY) / scale };
  }, []);

  const hitCharacter = useCallback((worldX: number, worldY: number) => [...engineRef.current.characters.values()].sort((a, b) => b.y - a.y).find(character => Math.abs(character.x - worldX) <= 10 && worldY >= character.y - 26 && worldY <= character.y + 10), []);

  const applyEditorAt = useCallback((col: number, row: number) => {
    const current = cloneOfficeLayout(engineRef.current.layout);
    const index = row * current.cols + col;
    if (tool === 'floor') current.tiles[index] = floor;
    if (tool === 'wall') current.tiles[index] = 0;
    if (tool === 'erase') {
      const item = [...current.furniture].reverse().find(candidate => {
        const spec = FURNITURE_CATALOG[candidate.kind];
        return col >= candidate.col && row >= candidate.row && col < candidate.col + spec.footprintW && row < candidate.row + spec.footprintH;
      });
      if (item) current.furniture = current.furniture.filter(candidate => candidate.id !== item.id);
      else current.tiles[index] = 1;
    }
    if (tool === 'furniture') {
      const spec = FURNITURE_CATALOG[furniture];
      if (col + spec.footprintW > current.cols || row + spec.footprintH > current.rows) return;
      current.furniture.push({ id: `f-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, kind: furniture, col, row });
    }
    if (tool === 'select') {
      const item = [...current.furniture].reverse().find(candidate => {
        const spec = FURNITURE_CATALOG[candidate.kind];
        return col >= candidate.col && row >= candidate.row && col < candidate.col + spec.footprintW && row < candidate.row + spec.footprintH;
      });
      setSelectedFurniture(item?.id || '');
      return;
    }
    commitLayout(current);
  }, [commitLayout, floor, furniture, tool]);

  const deleteSelected = useCallback(() => {
    if (!selectedFurniture) return;
    const next = cloneOfficeLayout(engineRef.current.layout);
    next.furniture = next.furniture.filter(item => item.id !== selectedFurniture);
    setSelectedFurniture('');
    commitLayout(next);
  }, [commitLayout, selectedFurniture]);

  const exportLayout = useCallback(() => {
    const blob = new Blob([JSON.stringify(engineRef.current.layout, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'hermes-office-layout.json'; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }, []);

  const editorTools: Array<{ id: EditorTool; title: string; icon: React.ReactNode }> = [
    { id: 'select', title: language === 'ru' ? 'Выбрать объект' : 'Select object', icon: <MousePointer2 size={15} /> },
    { id: 'floor', title: language === 'ru' ? 'Покрасить пол' : 'Paint floor', icon: <PaintBucket size={15} /> },
    { id: 'wall', title: language === 'ru' ? 'Построить стену' : 'Build wall', icon: <BrickWall size={15} /> },
    { id: 'furniture', title: language === 'ru' ? 'Расставить мебель' : 'Place furniture', icon: <Armchair size={15} /> },
    { id: 'erase', title: language === 'ru' ? 'Стереть' : 'Erase', icon: <Eraser size={15} /> },
  ];

  return (
    <div ref={shellRef} className={`pixel-canvas-shell${editorOpen ? ' is-editing' : ''}`}>
      <canvas
        ref={canvasRef}
        className="pixel-office-canvas"
        role="img"
        aria-label={language === 'ru' ? 'Интерактивный пиксельный офис агентов' : 'Interactive pixel agent office'}
        tabIndex={0}
        onWheel={event => { event.preventDefault(); onZoom(Math.max(.75, Math.min(1.5, zoom + (event.deltaY < 0 ? .1 : -.1)))); }}
        onPointerDown={event => {
          const tile = screenToTile(event.clientX, event.clientY);
          if (!tile) return;
          if (editorOpen && event.button === 0) { applyEditorAt(tile.col, tile.row); return; }
          if (event.button === 2 && selectedAgentId) { engineRef.current.moveAgentTo(selectedAgentId, tile.col, tile.row); return; }
          const character = hitCharacter(tile.worldX, tile.worldY);
          if (character) { onSelectAgent(character.agent.id, event.currentTarget); return; }
          dragRef.current = { x: event.clientX, y: event.clientY, cameraX: cameraRef.current.x, cameraY: cameraRef.current.y, moved: false };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          const tile = screenToTile(event.clientX, event.clientY);
          hoveredRef.current = tile ? hitCharacter(tile.worldX, tile.worldY)?.agent.id || '' : '';
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

      <button type="button" className={`pixel-layout-toggle${editorOpen ? ' is-active' : ''}`} onClick={() => setEditorOpen(value => !value)} title={language === 'ru' ? 'Редактор офиса' : 'Office editor'} aria-pressed={editorOpen}><Armchair size={16} /></button>
      {editorOpen && <div className="pixel-editor-toolbar" role="toolbar" aria-label={language === 'ru' ? 'Редактор офиса' : 'Office editor'}>
        <div className="pixel-editor-tools">{editorTools.map(item => <button key={item.id} type="button" className={tool === item.id ? 'is-active' : ''} onClick={() => setTool(item.id)} title={item.title} aria-label={item.title} aria-pressed={tool === item.id}>{item.icon}</button>)}</div>
        {tool === 'floor' && <div className="pixel-floor-swatches">{FLOOR_ASSETS.map((src, index) => <button key={src} type="button" className={floor === index + 1 ? 'is-active' : ''} onClick={() => setFloor(index + 1)} title={`Floor ${index + 1}`} aria-label={`Floor ${index + 1}`}><img src={src} alt="" /></button>)}</div>}
        {tool === 'furniture' && <div className="pixel-furniture-palette">{FURNITURE_KINDS.map(kind => <button key={kind} type="button" className={furniture === kind ? 'is-active' : ''} onClick={() => setFurniture(kind)} title={FURNITURE_CATALOG[kind].label} aria-label={FURNITURE_CATALOG[kind].label}><img src={FURNITURE_CATALOG[kind].src} alt="" /></button>)}</div>}
        <div className="pixel-editor-history">
          <button type="button" onClick={undo} disabled={!undoRef.current.length} title="Undo" aria-label="Undo"><Undo2 size={15} /></button>
          <button type="button" onClick={redo} disabled={!redoRef.current.length} title="Redo" aria-label="Redo"><Redo2 size={15} /></button>
          <button type="button" onClick={deleteSelected} disabled={!selectedFurniture} title="Delete selected" aria-label="Delete selected"><Trash2 size={15} /></button>
          <button type="button" onClick={() => commitLayout(createDefaultCanvasLayout())} title="Reset layout" aria-label="Reset layout"><RotateCcw size={15} /></button>
          <button type="button" onClick={exportLayout} title="Export layout" aria-label="Export layout"><Download size={15} /></button>
          <button type="button" onClick={() => importRef.current?.click()} title="Import layout" aria-label="Import layout"><Upload size={15} /></button>
        </div>
      </div>}
      <input ref={importRef} className="pixel-layout-import" type="file" accept="application/json,.json" onChange={event => {
        const file = event.target.files?.[0];
        if (!file) return;
        void file.text().then(text => commitLayout(normalizeCanvasLayout(JSON.parse(text))));
        event.target.value = '';
      }} />
      <div className="pixel-canvas-status" aria-hidden="true"><span>{layout.cols}×{layout.rows}</span><i />{agents.length}</div>
    </div>
  );
}
