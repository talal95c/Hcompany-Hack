export const ZOOM_DURATION = 1150;
export const COLUMNS = 19;
export const ROWS = 3;
export const GRID_X = 12;
export const GRID_Y = 8;
export type Point = { x: number; y: number; u: number; v: number };
export type Rect = { x: number; y: number; size: number };

export function initialRect(width: number, height: number): Rect {
  const unit = Math.min(height, width * 1.5);
  const size = unit * 0.3;
  return {
    x: (width - size) / 2,
    y: height / 2 + unit * 0.01 - size / 2,
    size,
  };
}

export function smoothstep(start: number, end: number, value: number) {
  const t = Math.max(0, Math.min(1, (value - start) / (end - start)));
  return t * t * (3 - 2 * t);
}

export function zoomProgress(progress: number) {
  let t = progress;
  for (let i = 0; i < 6; i++) {
    const x = 1.35 * t * (1 - t) ** 2 + 0.45 * t * t * (1 - t) + t ** 3;
    const derivative = 1.35 * (1 - t) ** 2 - 1.8 * t * (1 - t) + 2.55 * t * t;
    t = Math.max(0, Math.min(1, t - (x - progress) / derivative));
  }
  return t * t * (3 - 2 * t);
}

export function screenMesh(column: number, row: number): Point[] {
  const yaw = -0.34 + (column - 9) * 0.01;
  const pitch = Math.atan2(0.065, 1.35) + 0.055 - (row - 1) * 0.015;
  const distance = Math.hypot(1.35, 0.065);
  const cameraY = -Math.cos(pitch) * distance;
  const cameraZ = 0.155 + Math.sin(pitch) * distance;
  const focal = Math.tan((17 * Math.PI) / 180);
  const points: Point[] = [];
  for (let y = 0; y <= GRID_Y; y++) {
    for (let x = 0; x <= GRID_X; x++) {
      const u = x / GRID_X,
        v = y / GRID_Y;
      const wx = (u * 2 - 1) * 0.119;
      const wz = 0.203 + (1 - v * 2) * 0.093;
      const wy =
        -0.15 +
        Math.tan(Math.PI / 18) * (wz - 0.035) -
        0.018 +
        0.245 -
        Math.sqrt(0.245 ** 2 - wx ** 2 - (wz - 0.203) ** 2) +
        0.002;
      const rx = Math.cos(yaw) * wx - Math.sin(yaw) * wy;
      const ry = Math.sin(yaw) * wx + Math.cos(yaw) * wy - cameraY;
      const rz = wz - 0.0025 - cameraZ;
      const depth = ry * Math.cos(pitch) - rz * Math.sin(pitch);
      const vertical = ry * Math.sin(pitch) + rz * Math.cos(pitch);
      points.push({
        x: (0.5 + (0.5 * rx) / (depth * focal) - 0.2) / 0.6,
        y: (0.5 - (0.5 * vertical) / (depth * focal) - 0.22) / 0.6,
        u,
        v,
      });
    }
  }
  return points;
}

export function bounds(points: Point[]) {
  const x = Math.min(...points.map((p) => p.x));
  const y = Math.min(...points.map((p) => p.y));
  return {
    x,
    y,
    width: Math.max(...points.map((p) => p.x)) - x,
    height: Math.max(...points.map((p) => p.y)) - y,
  };
}

export function zoomRect(points: Point[], width: number, height: number): Rect {
  const screen = bounds(points);
  const scale = Math.max(width / screen.width, height / screen.height) * 1.25;
  return {
    x: width / 2 - (screen.x + screen.width / 2) * scale,
    y: height / 2 - (screen.y + screen.height / 2) * scale,
    size: scale,
  };
}
