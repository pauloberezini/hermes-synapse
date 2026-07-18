import { FURNITURE_CATALOG, type CanvasDirection, type FurnitureKind } from './officeCanvasEngine';

// ─── Isometric projection ──────────────────────────────────────────────────────
// The office grid (col/row) is reused verbatim from the top-down engine; only the
// projection to screen space changes. tileToIso maps a tile to the TOP vertex of
// its isometric diamond, so neighbouring tiles tessellate cleanly.

export const ISO_TILE_W = 64;
export const ISO_TILE_H = 32;

export interface IsoPoint { x: number; y: number }

export function tileToIso(tx: number, ty: number): IsoPoint {
  return { x: (tx - ty) * (ISO_TILE_W / 2), y: (tx + ty) * (ISO_TILE_H / 2) };
}

/** Inverse of tileToIso — screen-space iso coords back to fractional tile coords. */
export function isoToTile(x: number, y: number): { tx: number; ty: number } {
  const a = x / (ISO_TILE_W / 2);
  const b = y / (ISO_TILE_H / 2);
  return { tx: (a + b) / 2, ty: (b - a) / 2 };
}

export function isoWorldBounds(cols: number, rows: number) {
  const corners = [tileToIso(0, 0), tileToIso(cols, 0), tileToIso(0, rows), tileToIso(cols, rows)];
  const xs = corners.map(c => c.x);
  const ys = corners.map(c => c.y);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

// ─── Placeholder furniture volumes ─────────────────────────────────────────────
// Heights (unscaled iso px) and face colours for the programmatic stand-in art,
// used until a real isometric asset pack is dropped in via the manifest.

export interface IsoVolume { height: number; top: string; light: string; dark: string }

export const FURNITURE_ISO: Record<FurnitureKind, IsoVolume> = {
  DESK_FRONT: { height: 13, top: '#8a6a3c', light: '#6f5330', dark: '#4f3b22' },
  PC_FRONT_OFF: { height: 19, top: '#3a4a6b', light: '#2b3550', dark: '#1c2338' },
  CUSHIONED_CHAIR_BACK: { height: 12, top: '#4a5c78', light: '#3a4a63', dark: '#2a3550' },
  DOUBLE_BOOKSHELF: { height: 34, top: '#6f5636', light: '#5b4630', dark: '#3f3020' },
  SOFA_FRONT: { height: 13, top: '#3a726f', light: '#2f5d63', dark: '#204248' },
  COFFEE_TABLE: { height: 9, top: '#8a6a3c', light: '#6f5330', dark: '#4f3b22' },
  WHITEBOARD: { height: 30, top: '#e6ebf2', light: '#c3cad6', dark: '#9aa2b2' },
  PLANT: { height: 22, top: '#3a9a5c', light: '#2f7d4a', dark: '#1f5a34' },
  LARGE_PLANT: { height: 34, top: '#3a9a5c', light: '#2f7d4a', dark: '#1f5a34' },
  CLOCK: { height: 20, top: '#aab0bd', light: '#8a8f9c', dark: '#5f6470' },
  CUSHIONED_BENCH: { height: 9, top: '#4a5c78', light: '#3a4a63', dark: '#2a3550' },
  SMALL_PAINTING: { height: 18, top: '#b0895a', light: '#9a7b4a', dark: '#6f5836' },
};

export function furnitureDepth(kind: FurnitureKind, col: number, row: number): number {
  const spec = FURNITURE_CATALOG[kind];
  return (col + spec.footprintW - 1) + (row + spec.footprintH - 1);
}

// ─── Asset-pack manifest (real isometric art) ──────────────────────────────────
// When present at /iso-office-assets/manifest.json the renderer swaps the
// programmatic placeholder for the pack's sprites. Absent → placeholder mode.

export interface IsoSpriteSpec {
  src: string;
  /** Pixel offset from the tile's top vertex to the sprite's top-left when drawn. */
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
}

export interface IsoAssetManifest {
  tileWidth: number;
  tileHeight: number;
  floors?: Record<string, IsoSpriteSpec>;
  walls?: { far: IsoSpriteSpec; divider?: IsoSpriteSpec };
  furniture?: Partial<Record<FurnitureKind, IsoSpriteSpec>>;
  characters?: {
    sheet: string;
    frameWidth: number;
    frameHeight: number;
    /** Sprite-sheet row per facing direction. */
    directions: Record<CanvasDirection, number>;
    /** Frames per walk cycle. */
    frames: number;
    anchorY: number;
  };
}

export async function loadIsoManifest(url = '/iso-office-assets/manifest.json'): Promise<IsoAssetManifest | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    const data = (await response.json()) as IsoAssetManifest;
    if (!data || typeof data.tileWidth !== 'number' || typeof data.tileHeight !== 'number') return null;
    return data;
  } catch {
    return null;
  }
}
