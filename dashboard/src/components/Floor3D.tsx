import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { DeskState } from "../data/types";
import {
  CORE_TICKERS,
  FLOOR_DUCKS,
  FLOOR_ROLES,
  MASCOT_POSITION,
  SLEEVE_COLORS,
  type FloorDuckSpec,
  type FloorRole,
  type FloorScene,
  type FloorStatus,
} from "../data/floor";
import { fmtUsd } from "../data/format";

const BG = "#0c1322";
const LINE = "#24314a";
const YELLOW = "#f2c230";
const GREY = "#c3ccdc";
const ORANGE = "#ff7a1a";
const BLUE = "#5b8def";
const VIOLET = "#a78bfa";
const GREEN = "#34c98a";
const RED = "#f26b6b";

/** Lifts a name tag above a tall prop without moving the duck. */
const TAG_LIFT: Record<string, number> = {
  manager: 0.55,
  auditor: 0.15,
};

interface BoxOptions {
  cast?: boolean;
  receive?: boolean;
  opacity?: number;
  emissive?: string;
  rotation?: [number, number, number];
}

function addBox(
  parent: THREE.Object3D,
  w: number,
  h: number,
  d: number,
  x: number,
  y: number,
  z: number,
  color: string,
  options: BoxOptions = {},
): THREE.Mesh {
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.78,
    metalness: 0.02,
    flatShading: true,
    transparent: (options.opacity ?? 1) < 1,
    opacity: options.opacity ?? 1,
    depthWrite: (options.opacity ?? 1) >= 1,
    emissive: options.emissive ?? "#000000",
    emissiveIntensity: options.emissive ? 0.6 : 0,
  });
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  mesh.position.set(x, y, z);
  if (options.rotation) mesh.rotation.set(...options.rotation);
  mesh.castShadow = options.cast ?? true;
  mesh.receiveShadow = options.receive ?? true;
  parent.add(mesh);
  return mesh;
}

function addCylinder(
  parent: THREE.Object3D,
  radiusTop: number,
  radiusBottom: number,
  height: number,
  x: number,
  y: number,
  z: number,
  color: string,
  options: BoxOptions = {},
  segments = 12,
): THREE.Mesh {
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.72,
    metalness: 0.03,
    flatShading: true,
    transparent: (options.opacity ?? 1) < 1,
    opacity: options.opacity ?? 1,
    depthWrite: (options.opacity ?? 1) >= 1,
    emissive: options.emissive ?? "#000000",
    emissiveIntensity: options.emissive ? 0.6 : 0,
  });
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments), material);
  mesh.position.set(x, y, z);
  if (options.rotation) mesh.rotation.set(...options.rotation);
  mesh.castShadow = options.cast ?? true;
  mesh.receiveShadow = options.receive ?? true;
  parent.add(mesh);
  return mesh;
}

function addSphere(
  parent: THREE.Object3D,
  radius: number,
  x: number,
  y: number,
  z: number,
  color: string,
  segments = 10,
): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, segments, Math.max(6, Math.round(segments * 0.7))),
    new THREE.MeshStandardMaterial({ color, roughness: 0.75, flatShading: true }),
  );
  mesh.position.set(x, y, z);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function addDesk(parent: THREE.Object3D, x: number, z: number, width = 2.15, color = "#5b3f2a"): void {
  addBox(parent, width, 0.16, 1.2, x, 0.95, z, color);
  const leg = 0.09;
  [-1, 1].forEach((sx) => {
    [-1, 1].forEach((sz) => {
      addBox(parent, leg, 0.88, leg, x + sx * (width / 2 - 0.12), 0.46, z + sz * 0.46, "#3b2c22");
    });
  });
  addBox(parent, 0.72, 0.44, 0.08, x, 1.34, z - 0.32, "#0c1322");
  addBox(parent, 0.62, 0.34, 0.035, x, 1.34, z - 0.27, "#17365c", { emissive: "#0b2748" });
  addBox(parent, 0.08, 0.28, 0.08, x, 1.16, z - 0.32, "#24314a");
  addBox(parent, 0.78, 0.06, 0.34, x, 1.03, z - 0.32, "#24314a");
}

function addChair(parent: THREE.Object3D, x: number, z: number, color = "#2a3852"): void {
  addCylinder(parent, 0.28, 0.24, 0.1, x, 0.55, z, color, {}, 10);
  addCylinder(parent, 0.04, 0.04, 0.45, x, 0.3, z, "#1a2438", {}, 8);
  addBox(parent, 0.46, 0.52, 0.08, x, 0.92, z - 0.24, color);
}

function addPlant(parent: THREE.Object3D, x: number, z: number): void {
  addCylinder(parent, 0.32, 0.24, 0.45, x, 0.23, z, "#6b4a2f", {}, 10);
  addCylinder(parent, 0.05, 0.06, 0.6, x, 0.72, z, "#3f5d33", {}, 8);
  addSphere(parent, 0.3, x, 1.05, z, "#3f7a4a", 7);
  addSphere(parent, 0.22, x - 0.22, 1.22, z + 0.05, "#4d8a56", 7);
  addSphere(parent, 0.2, x + 0.2, 1.28, z - 0.08, "#356c41", 7);
}

function addZone(
  parent: THREE.Object3D,
  x: number,
  z: number,
  w: number,
  d: number,
  color: string,
): void {
  addBox(parent, w, 0.02, d, x, 0.07, z, color, { opacity: 0.1, cast: false, receive: false });
  [
    [x, z - d / 2, w, 0.07],
    [x, z + d / 2, w, 0.07],
    [x - w / 2, z, 0.07, d],
    [x + w / 2, z, 0.07, d],
  ].forEach(([bx, bz, bw, bd]) => {
    addBox(parent, bw, 0.05, bd, bx, 0.095, bz, color, { opacity: 0.48, cast: false, receive: false });
  });
}

function addRoundTable(parent: THREE.Object3D, x: number, z: number, radius: number): void {
  addCylinder(parent, radius, radius, 0.14, x, 1.02, z, "#5b3f2a", {}, 20);
  addCylinder(parent, 0.16, 0.26, 0.88, x, 0.52, z, "#3b2c22", {}, 10);
}

interface DuckState {
  spec: FloorDuckSpec;
  group: THREE.Group;
  bob: THREE.Group;
  lean: number;
}

function createDuckBase(bodyColor: string): { group: THREE.Group; bob: THREE.Group } {
  const group = new THREE.Group();
  const bob = new THREE.Group();
  group.add(bob);

  addBox(bob, 0.24, 0.12, 0.42, -0.28, 0.09, 0.18, ORANGE);
  addBox(bob, 0.24, 0.12, 0.42, 0.28, 0.09, 0.18, ORANGE);
  addBox(bob, 1.04, 0.58, 0.9, 0, 0.48, 0, bodyColor);
  addBox(bob, 0.7, 0.22, 0.82, 0, 0.75, -0.02, bodyColor);
  addBox(bob, 0.22, 0.22, 0.3, 0, 0.63, -0.53, bodyColor, { rotation: [0.18, 0, 0] });
  addBox(bob, 0.18, 0.36, 0.5, 0.58, 0.66, 0.02, bodyColor, { rotation: [0, 0, -0.2] });
  addBox(bob, 0.56, 0.32, 0.06, 0, 0.48, 0.46, bodyColor === YELLOW ? "#ffe06a" : "#e2e8f2", {
    cast: false,
  });
  addBox(bob, 0.78, 0.7, 0.7, 0, 1.27, 0.04, bodyColor);
  addBox(bob, 0.42, 0.12, 0.06, 0.03, 1.47, 0.4, bodyColor === YELLOW ? "#ffe06a" : "#e8edf6", {
    cast: false,
  });
  addBox(bob, 0.32, 0.16, 0.34, 0, 1.22, 0.55, ORANGE);
  addBox(bob, 0.09, 0.12, 0.05, -0.2, 1.36, 0.41, BG, { cast: false });
  addBox(bob, 0.09, 0.12, 0.05, 0.2, 1.36, 0.41, BG, { cast: false });
  return { group, bob };
}

function addGlasses(bob: THREE.Group): void {
  addCylinder(bob, 0.14, 0.14, 0.05, -0.19, 1.36, 0.42, BG, { rotation: [Math.PI / 2, 0, 0] }, 12);
  addCylinder(bob, 0.14, 0.14, 0.05, 0.19, 1.36, 0.42, BG, { rotation: [Math.PI / 2, 0, 0] }, 12);
  addCylinder(bob, 0.1, 0.1, 0.015, -0.19, 1.36, 0.45, "#cfe3ff", { rotation: [Math.PI / 2, 0, 0] }, 12);
  addCylinder(bob, 0.1, 0.1, 0.015, 0.19, 1.36, 0.45, "#cfe3ff", { rotation: [Math.PI / 2, 0, 0] }, 12);
  addBox(bob, 0.13, 0.035, 0.035, 0, 1.36, 0.43, BG);
}

const ANALYST_CLIPBOARDS: Record<string, string> = {
  "analyst-1": BLUE,
  "analyst-2": VIOLET,
  "analyst-3": "#2dd4bf",
};

function addRoleProps(role: FloorRole, bob: THREE.Group, id: string): void {
  switch (role) {
    case "analyst": {
      const accent = ANALYST_CLIPBOARDS[id] ?? BLUE;
      addCylinder(bob, 0.4, 0.4, 0.13, 0, 1.67, 0.03, BLUE, {}, 12);
      addCylinder(bob, 0.46, 0.46, 0.04, 0, 1.6, 0.03, "#3f6fc4", {}, 12);
      addSphere(bob, 0.06, 0.08, 1.76, 0.03, BLUE, 6);
      addGlasses(bob);
      addBox(bob, 0.7, 0.54, 0.05, 0.4, 0.98, 0.58, accent, { rotation: [0, 0, -0.18] });
      addBox(bob, 0.58, 0.42, 0.014, 0.4, 0.98, 0.612, "#e8edf6", {
        cast: false,
        rotation: [0, 0, -0.18],
      });
      addBox(bob, 0.16, 0.06, 0.025, 0.4, 1.22, 0.618, "#24314a", {
        cast: false,
        rotation: [0, 0, -0.18],
      });
      addBox(bob, 0.42, 0.024, 0.012, 0.42, 1.08, 0.625, "#8b97ad", { cast: false, rotation: [0, 0, -0.18] });
      addBox(bob, 0.36, 0.024, 0.012, 0.42, 1.0, 0.625, "#8b97ad", { cast: false, rotation: [0, 0, -0.18] });
      addBox(bob, 0.28, 0.024, 0.012, 0.42, 0.92, 0.625, "#8b97ad", { cast: false, rotation: [0, 0, -0.18] });
      break;
    }
    case "bull": {
      addBox(bob, 1.32, 0.48, 0.84, 0, 1.06, 0.02, YELLOW);
      addBox(bob, 0.42, 0.34, 0.5, -0.7, 0.95, 0.04, YELLOW, { rotation: [0, 0, 0.18] });
      addBox(bob, 0.42, 0.34, 0.5, 0.7, 0.95, 0.04, YELLOW, { rotation: [0, 0, -0.18] });
      addCylinder(bob, 0.43, 0.45, 0.24, 0, 1.69, 0.03, "#2b9a6a", {}, 10);
      addCylinder(bob, 0.1, 0.13, 0.64, -0.44, 1.78, 0.03, "#e8edf6", {
        rotation: [0, 0, 1.15],
      }, 8);
      addCylinder(bob, 0.1, 0.13, 0.64, 0.44, 1.78, 0.03, "#e8edf6", {
        rotation: [0, 0, -1.15],
      }, 8);
      addCylinder(bob, 0.025, 0.025, 0.9, 0.62, 1.05, -0.1, "#24314a", {}, 6);
      addBox(bob, 0.4, 0.34, 0.035, 0.79, 1.38, -0.1, GREEN);
      addBox(bob, 0.065, 0.2, 0.02, 0.79, 1.39, -0.075, "#e8edf6", { cast: false });
      addBox(bob, 0.2, 0.06, 0.02, 0.79, 1.42, -0.075, "#e8edf6", { cast: false });
      break;
    }
    case "bear": {
      addSphere(bob, 0.5, 0, 0.88, 0.24, YELLOW, 12);
      addSphere(bob, 0.47, 0, 1.61, -0.01, "#3d2227", 10);
      addSphere(bob, 0.16, -0.37, 1.86, 0, "#7a2f2f", 7);
      addSphere(bob, 0.16, 0.37, 1.86, 0, "#7a2f2f", 7);
      addBox(bob, 0.88, 0.15, 0.15, 0, 0.85, 0.54, "#c3ccdc", { rotation: [0, 0, 0.38] });
      addBox(bob, 0.88, 0.15, 0.15, 0, 0.85, 0.55, "#c3ccdc", { rotation: [0, 0, -0.38] });
      addCylinder(bob, 0.025, 0.025, 0.9, -0.58, 1.06, -0.12, "#24314a", {}, 6);
      addBox(bob, 0.34, 0.3, 0.035, -0.58, 1.37, -0.12, RED);
      addBox(bob, 0.06, 0.2, 0.02, -0.58, 1.35, -0.09, "#e8edf6", { cast: false });
      addBox(bob, 0.17, 0.06, 0.02, -0.58, 1.28, -0.09, "#e8edf6", { cast: false });
      break;
    }
    case "manager": {
      addCylinder(bob, 0.32, 0.32, 0.92, 0, 2.16, 0.02, "#171512", {}, 12);
      addCylinder(bob, 0.52, 0.52, 0.07, 0, 1.64, 0.02, "#171512", {}, 12);
      addCylinder(bob, 0.33, 0.33, 0.11, 0, 1.75, 0.02, VIOLET, {}, 12);
      addCylinder(bob, 0.04, 0.045, 0.46, 0.68, 0.91, 0.42, "#7a5a32", {
        rotation: [0, 0, -0.45],
      }, 8);
      addBox(bob, 0.2, 0.18, 0.3, 0.8, 1.1, 0.46, "#7a5a32", { rotation: [0, 0, -0.45] });
      addBox(bob, 0.4, 0.3, 0.04, -0.58, 0.98, 0.53, "#e8edf6", { rotation: [0, 0, 0.14] });
      addBox(bob, 0.42, 0.32, 0.025, -0.58, 0.98, 0.5, VIOLET, { rotation: [0, 0, 0.14], cast: false });
      break;
    }
    case "quick": {
      addBox(bob, 0.11, 0.28, 0.06, 0.5, 1.57, 0.12, "#ffe27a", { rotation: [0, 0, 0.55] });
      addBox(bob, 0.11, 0.28, 0.06, 0.38, 1.39, 0.12, "#ffe27a", { rotation: [0, 0, 0.55] });
      addBox(bob, 0.11, 0.26, 0.06, 0.52, 1.25, 0.12, "#ffe27a", { rotation: [0, 0, 0.55] });
      addBox(bob, 0.1, 0.16, 0.05, 0.38, 1.67, 0.12, "#ffe27a", { rotation: [0, 0, 0.55] });
      addCylinder(bob, 0.2, 0.2, 0.08, 0.5, 1.56, 0.3, "#171512", { rotation: [Math.PI / 2, 0, 0] }, 14);
      addCylinder(bob, 0.155, 0.155, 0.02, 0.5, 1.56, 0.35, "#f4f7fb", {
        rotation: [Math.PI / 2, 0, 0],
        emissive: "#dfe6f0",
      }, 14);
      addBox(bob, 0.025, 0.12, 0.012, 0.5, 1.6, 0.365, BG, { cast: false });
      addBox(bob, 0.08, 0.025, 0.012, 0.53, 1.56, 0.365, BG, { cast: false });
      addCylinder(bob, 0.03, 0.03, 0.07, 0.5, 1.71, 0.3, "#171512", {}, 8);
      break;
    }
    case "coordinator": {
      addBox(bob, 0.66, 0.06, 0.12, 0, 1.65, 0.03, "#171512");
      addCylinder(bob, 0.1, 0.1, 0.08, -0.4, 1.39, 0.03, "#171512", {
        rotation: [0, 0, Math.PI / 2],
      }, 10);
      addCylinder(bob, 0.1, 0.1, 0.08, 0.4, 1.39, 0.03, "#171512", {
        rotation: [0, 0, Math.PI / 2],
      }, 10);
      addBox(bob, 0.045, 0.3, 0.045, 0.37, 1.23, 0.28, "#171512", { rotation: [0.3, 0, 0] });
      addSphere(bob, 0.05, 0.33, 1.12, 0.4, "#171512", 6);
      addBox(bob, 0.39, 0.48, 0.04, -0.47, 0.92, 0.5, "#7a5a32", { rotation: [0, 0, 0.12] });
      addBox(bob, 0.32, 0.39, 0.012, -0.47, 0.92, 0.525, "#e8edf6", {
        rotation: [0, 0, 0.12],
        cast: false,
      });
      break;
    }
    case "auditor": {
      addBox(bob, 0.16, 0.12, 0.05, -0.14, 1.02, 0.47, VIOLET, { rotation: [0, 0, 0.45] });
      addBox(bob, 0.16, 0.12, 0.05, 0.14, 1.02, 0.47, VIOLET, { rotation: [0, 0, -0.45] });
      addBox(bob, 0.08, 0.08, 0.06, 0, 1.02, 0.48, "#7c5fd6");
      addBox(bob, 0.18, 0.04, 0.03, -0.19, 1.43, 0.41, BG, { cast: false });
      addBox(bob, 0.18, 0.04, 0.03, 0.19, 1.43, 0.41, BG, { cast: false });
      addCylinder(bob, 0.03, 0.035, 0.4, 0.53, 0.84, 0.42, "#171512", {
        rotation: [0.4, 0, -0.5],
      }, 8);
      addCylinder(bob, 0.14, 0.14, 0.04, 0.64, 1.07, 0.42, BG, { rotation: [Math.PI / 2, 0, 0] }, 12);
      addCylinder(bob, 0.1, 0.1, 0.02, 0.64, 1.07, 0.45, "#bfe3ff", {
        rotation: [Math.PI / 2, 0, 0],
        opacity: 0.5,
      }, 12);
      break;
    }
    case "scheduler": {
      addCylinder(bob, 0.31, 0.31, 0.1, 0, 1.78, 0.06, "#171512", {
        rotation: [Math.PI / 2, 0, 0],
      }, 14);
      addCylinder(bob, 0.26, 0.26, 0.04, 0, 1.78, 0.12, "#e8edf6", {
        rotation: [Math.PI / 2, 0, 0],
      }, 14);
      addSphere(bob, 0.08, -0.26, 1.98, 0.02, ORANGE, 7);
      addSphere(bob, 0.08, 0.26, 1.98, 0.02, ORANGE, 7);
      addBox(bob, 0.035, 0.16, 0.02, 0, 1.83, 0.145, BG, { cast: false });
      addBox(bob, 0.12, 0.035, 0.02, 0.05, 1.78, 0.145, BG, { cast: false });
      break;
    }
    case "screener": {
      addBox(bob, 0.7, 0.16, 0.18, 0, 1.55, 0.06, "#24314a");
      addCylinder(bob, 0.15, 0.15, 0.3, -0.18, 1.38, 0.55, BG, {
        rotation: [Math.PI / 2, 0, 0],
      }, 12);
      addCylinder(bob, 0.15, 0.15, 0.3, 0.18, 1.38, 0.55, BG, {
        rotation: [Math.PI / 2, 0, 0],
      }, 12);
      addCylinder(bob, 0.1, 0.1, 0.02, -0.18, 1.38, 0.71, BLUE, {
        rotation: [Math.PI / 2, 0, 0],
        emissive: "#204a80",
      }, 12);
      addCylinder(bob, 0.1, 0.1, 0.02, 0.18, 1.38, 0.71, BLUE, {
        rotation: [Math.PI / 2, 0, 0],
        emissive: "#204a80",
      }, 12);
      addBox(bob, 0.12, 0.06, 0.12, 0, 1.38, 0.56, "#24314a");
      addBox(bob, 0.12, 0.36, 0.12, -0.35, 1.1, 0.36, "#c3ccdc", { rotation: [0.7, 0, 0.3] });
      addBox(bob, 0.12, 0.36, 0.12, 0.35, 1.1, 0.36, "#c3ccdc", { rotation: [0.7, 0, -0.3] });
      break;
    }
    case "trader": {
      addBox(bob, 0.66, 0.07, 0.1, 0, 1.64, 0.02, "#171512");
      addCylinder(bob, 0.12, 0.12, 0.1, -0.36, 1.42, 0.02, "#171512", {
        rotation: [0, 0, Math.PI / 2],
      }, 10);
      addCylinder(bob, 0.12, 0.12, 0.1, 0.36, 1.42, 0.02, "#171512", {
        rotation: [0, 0, Math.PI / 2],
      }, 10);
      addBox(bob, 0.04, 0.04, 0.32, 0.33, 1.28, 0.19, "#171512", { rotation: [0.5, 0, 0] });
      addSphere(bob, 0.055, 0.33, 1.17, 0.4, "#171512", 6);
      addBox(bob, 0.045, 0.085, 0.46, -0.4, 1.44, -0.02, YELLOW, { rotation: [0.1, -0.2, -0.3] });
      addBox(bob, 0.35, 0.25, 0.035, 0.43, 0.94, 0.55, ORANGE, { rotation: [0, 0, -0.12] });
      break;
    }
    case "risk": {
      addBox(bob, 0.66, 0.12, 0.2, 0, 1.47, 0.39, "#c92a2a", { rotation: [-0.16, 0, 0] });
      addBox(bob, 0.38, 0.24, 0.035, -0.42, 0.95, 0.54, "#e8edf6");
      addBox(bob, 0.3, 0.03, 0.012, -0.42, 0.98, 0.562, "#c92a2a", { cast: false });
      addCylinder(bob, 0.045, 0.055, 0.34, 0.47, 0.9, 0.5, "#7a5a32", {
        rotation: [0.35, 0, -0.5],
      }, 8);
      addBox(bob, 0.28, 0.14, 0.24, 0.58, 1.02, 0.6, "#c92a2a", { rotation: [0, 0.3, 0] });
      break;
    }
    case "rebalancer": {
      addBox(bob, 0.66, 0.11, 0.2, 0, 1.48, 0.39, BLUE, { rotation: [-0.18, 0, 0] });
      addBox(bob, 0.52, 0.42, 0.05, 0.42, 0.96, 0.58, "#e8edf6", { rotation: [0, 0, -0.14] });
      addBox(bob, 0.38, 0.07, 0.014, 0.42, 1.07, 0.609, "#8fb2ff", { cast: false, rotation: [0, 0, -0.14] });
      addBox(bob, 0.3, 0.07, 0.014, 0.42, 0.97, 0.609, BLUE, { cast: false, rotation: [0, 0, -0.14] });
      addBox(bob, 0.22, 0.07, 0.014, 0.42, 0.87, 0.609, "#3f6fc4", { cast: false, rotation: [0, 0, -0.14] });
      break;
    }
    case "executor": {
      addBox(bob, 0.58, 0.14, 0.55, 0, 1.68, 0.03, ORANGE);
      addBox(bob, 0.56, 0.06, 0.25, 0, 1.61, 0.35, ORANGE);
      addBox(bob, 0.55, 0.6, 0.3, 0, 0.75, -0.62, ORANGE);
      addBox(bob, 0.3, 0.22, 0.035, 0.45, 0.95, 0.56, ORANGE, { rotation: [0, 0, -0.12] });
      break;
    }
    case "watcher": {
      addBox(bob, 0.56, 0.14, 0.56, 0, 1.68, 0.03, "#1b3a2c");
      addBox(bob, 0.56, 0.05, 0.22, 0, 1.61, 0.38, "#1b3a2c");
      addCylinder(bob, 0.08, 0.08, 0.4, 0.49, 1.02, 0.38, GREEN, {
        rotation: [Math.PI / 2, 0, 0],
      }, 10);
      addCylinder(bob, 0.3, 0.03, 1.1, 0.49, 1.02, 1.05, "#d6ffe9", {
        rotation: [Math.PI / 2, 0, 0],
        opacity: 0.16,
        cast: false,
      }, 12);
      break;
    }
    default:
      break;
  }
}

function createDuck(spec: FloorDuckSpec): DuckState {
  const bodyColor = FLOOR_ROLES[spec.role].agent ? YELLOW : GREY;
  const { group, bob } = createDuckBase(bodyColor);
  addRoleProps(spec.role, bob, spec.id);
  group.scale.setScalar(spec.scale);
  group.position.set(spec.x, 0, spec.z);
  group.rotation.y = spec.rotation;
  group.userData = { kind: "role", role: spec.role };
  const lean = spec.role === "bull" ? 0.1 : spec.role === "quick" || spec.role === "executor" ? -0.09 : 0;
  return { spec, group, bob, lean };
}

function createMascot(): THREE.Group {
  const { group, bob } = createDuckBase(YELLOW);
  addCylinder(bob, 0.36, 0.36, 0.22, 0, 1.72, 0.02, "#171512", {}, 12);
  addBox(bob, 0.6, 0.06, 0.36, 0, 1.61, -0.28, "#171512", { rotation: [0.08, 0, 0] });
  addBox(bob, 0.32, 0.14, 0.06, -0.19, 1.36, 0.42, BG);
  addBox(bob, 0.32, 0.14, 0.06, 0.19, 1.36, 0.42, BG);
  addBox(bob, 0.14, 0.035, 0.035, 0, 1.36, 0.43, BG);
  addBox(bob, 0.07, 0.025, 0.012, 0.25, 1.4, 0.46, "#f4f7fb", { cast: false });
  addBox(bob, 0.38, 0.1, 0.36, 0, 1.24, 0.58, ORANGE);
  addBox(bob, 0.3, 0.07, 0.28, 0, 1.15, 0.55, ORANGE, { rotation: [0.18, 0, 0] });
  addBox(bob, 0.26, 0.035, 0.02, 0, 1.19, 0.62, "#b5470e", { cast: false });
  group.position.set(MASCOT_POSITION.x, 0, MASCOT_POSITION.z);
  group.rotation.y = -0.2;
  return group;
}

function buildOffice(office: THREE.Group, stampGroup: THREE.Group): void {
  addBox(office, 36, 0.4, 24, 0, -0.25, 0, "#3b2a1c", { cast: false });
  for (let i = 0; i < 18; i += 1) {
    const x = -17 + i * 1.9;
    const color = i % 3 === 0 ? "#745033" : i % 3 === 1 ? "#67462b" : "#5b3d26";
    addBox(office, 1.82, 0.06, 23.6, x, 0.03, 0, color, { cast: false });
  }
  addBox(office, 36, 3.5, 0.34, 0, 1.75, -11.85, "#182238", { cast: false });
  addBox(office, 0.34, 3.5, 24, -17.85, 1.75, 0, "#182238", { cast: false });
  addBox(office, 36.2, 0.18, 0.46, 0, 3.5, -11.85, LINE, { cast: false });
  addBox(office, 0.46, 0.18, 24.2, -17.85, 3.5, 0, LINE, { cast: false });
  addBox(office, 36, 0.12, 0.4, 0, 0.08, -11.85, "#2c3852", { cast: false });
  addBox(office, 0.4, 0.12, 24, -17.85, 0.08, 0, "#2c3852", { cast: false });

  // Zone mats follow the pipeline left to right and fill the front-right floor.
  addZone(office, -12.8, -4.0, 6.2, 10.2, "#3d6ea8");
  addZone(office, -7.2, -3.3, 5.2, 5.2, "#2dd4bf");
  addZone(office, 7.1, -1.2, 6.2, 6.4, "#e08a2e");
  addZone(office, 12.4, 1.8, 6.0, 5.6, "#c94a4a");
  addZone(office, 14.7, -7.9, 4.4, 3.6, "#e08a2e");
  addZone(office, 15.7, 6.4, 3.8, 4.2, "#a78bfa");

  // Wall clock and fixtures.
  addCylinder(office, 0.48, 0.48, 0.14, -14.2, 2.72, -11.6, "#171512", {
    rotation: [Math.PI / 2, 0, 0],
  }, 18);
  addCylinder(office, 0.39, 0.39, 0.04, -14.2, 2.72, -11.52, "#e8edf6", {
    rotation: [Math.PI / 2, 0, 0],
  }, 18);
  addBox(office, 0.045, 0.25, 0.02, -14.2, 2.81, -11.49, BG, { cast: false });
  addBox(office, 0.19, 0.045, 0.02, -14.12, 2.72, -11.49, BG, { cast: false });

  addBox(office, 5.7, 2.55, 0.12, -10.8, 2.18, -11.58, "#0d1628");
  addBox(office, 5.95, 2.8, 0.06, -10.8, 2.18, -11.64, LINE, { cast: false });
  addBox(office, 5.35, 2.2, 0.03, -10.8, 2.18, -11.5, "#101c31", { emissive: "#07101f" });

  addBox(office, 5.9, 2.55, 0.12, 0, 2.2, -11.58, "#0d1628");
  addBox(office, 6.15, 2.8, 0.06, 0, 2.2, -11.64, ORANGE, { cast: false, opacity: 0.8 });
  addBox(office, 5.55, 2.2, 0.03, 0, 2.2, -11.5, "#0d1b33", { emissive: "#07162d" });

  // Core board (blue) and the small satellite board beside it.
  addBox(office, 5.8, 2.7, 0.12, 8, 2.18, -11.58, "#0d1628");
  addBox(office, 6.05, 2.95, 0.06, 8, 2.18, -11.64, BLUE, { cast: false, opacity: 0.85 });
  addBox(office, 5.45, 2.35, 0.03, 8, 2.18, -11.5, "#0d1b33", { emissive: "#07162d" });
  addBox(office, 3.05, 2.3, 0.12, 12.4, 2.0, -11.58, "#0d1628");
  addBox(office, 3.3, 2.55, 0.06, 12.4, 2.0, -11.64, VIOLET, { cast: false, opacity: 0.8 });
  addBox(office, 2.8, 1.95, 0.03, 12.4, 2.0, -11.5, "#141028", { emissive: "#0d0a1f" });

  // Door to the paper broker.
  addBox(office, 2.55, 2.95, 0.22, 15.35, 1.48, -11.64, "#15243c");
  addBox(office, 2.15, 2.65, 0.16, 15.35, 1.35, -11.48, "#7a3f16");
  addBox(office, 2.15, 2.65, 0.05, 15.35, 1.35, -11.39, ORANGE, { opacity: 0.72, emissive: "#6b2f08" });
  addSphere(office, 0.08, 14.55, 1.3, -11.31, "#e8edf6", 8);
  addBox(office, 2.9, 0.16, 0.8, 15.35, 0.08, -11.2, "#2c3852");

  // Intake: schedule and screen the run by the wall clock and ticker board.
  addDesk(office, -14.3, -8.1, 2.3, "#5b3f2a");
  addDesk(office, -10.7, -8.0, 2.1, "#4d3828");
  addBox(office, 0.9, 1.15, 0.7, -15.2, 0.58, -1.7, "#223149");
  addBox(office, 0.72, 0.5, 0.06, -15.2, 1.4, -1.95, "#0d1628");
  addBox(office, 0.6, 0.38, 0.03, -15.2, 1.4, -1.9, "#17365c", { emissive: "#0b2748" });

  // Research pod: three analysts share one round table.
  addRoundTable(office, -7.2, -2.9, 1.3);
  addChair(office, -8.15, -1.85);
  addChair(office, -6.25, -1.85);
  addChair(office, -7.2, -4.2);
  addBox(office, 0.72, 0.045, 0.5, -7.8, 1.12, -2.85, "#e8edf6", { cast: false });
  addBox(office, 0.62, 0.045, 0.42, -6.65, 1.12, -3.2, "#dfe6f0", { cast: false });
  addBox(office, 0.5, 0.32, 0.05, -6.7, 1.3, -3.48, "#17233a", { rotation: [0, 0.35, 0] });
  addCylinder(office, 0.09, 0.08, 0.2, -7.6, 1.18, -3.3, "#8b97ad", {}, 8);

  // Glass-walled debate pit, open at the front for the analyst entrance.
  addBox(office, 5.7, 2.45, 0.08, 0, 1.23, -5.15, BLUE, { opacity: 0.13, cast: false });
  addBox(office, 0.08, 2.45, 2.2, -2.85, 1.23, -4.05, BLUE, { opacity: 0.13, cast: false });
  addBox(office, 0.08, 2.45, 2.2, 2.85, 1.23, -4.05, BLUE, { opacity: 0.13, cast: false });
  addBox(office, 5.9, 0.09, 0.12, 0, 2.47, -5.15, "#3a4a67");
  addBox(office, 0.12, 0.09, 2.3, -2.85, 2.47, -4.05, "#3a4a67");
  addBox(office, 0.12, 0.09, 2.3, 2.85, 2.47, -4.05, "#3a4a67");
  [-2.85, 0, 2.85].forEach((x) => addBox(office, 0.1, 2.5, 0.1, x, 1.25, -5.15, "#3a4a67"));
  [-2.85, 2.85].forEach((x) => addBox(office, 0.1, 2.5, 0.1, x, 1.25, -2.95, "#3a4a67"));
  addRoundTable(office, 0, -3.1, 1.3);
  addChair(office, -1.55, -1.7);
  addChair(office, 1.55, -1.7);
  addBox(office, 0.46, 0.04, 0.34, -0.4, 1.12, -3.15, "#e8edf6", { cast: false });
  addBox(office, 0.36, 0.04, 0.28, 0.35, 1.12, -3.3, "#dfe6f0", { cast: false });

  // Decision: quick kiosk and the trader desk.
  addBox(office, 1.9, 1.05, 1.0, 5.2, 0.53, -3.65, "#223149");
  addBox(office, 1.6, 1.3, 0.12, 5.2, 1.45, -4.1, "#0d1628");
  addBox(office, 1.38, 1.05, 0.035, 5.2, 1.45, -4.03, "#193b66", { emissive: "#0b2748" });
  addBox(office, 0.12, 0.32, 0.06, 5.2, 1.77, -3.89, YELLOW, { rotation: [0, 0, 0.55], cast: false });
  addBox(office, 0.1, 0.22, 0.06, 5.13, 1.63, -3.89, YELLOW, { rotation: [0, 0, 0.55], cast: false });
  addDesk(office, 7.9, -0.7, 2.35);
  addChair(office, 9.05, 0.35);

  // Controls: the risk booth and the core rebalancer.
  addBox(office, 3.6, 1.75, 0.12, 11.0, 0.88, 3.0, "#24314a");
  addBox(office, 0.12, 1.75, 2.6, 9.25, 0.88, 1.7, "#24314a");
  addBox(office, 0.12, 1.75, 2.6, 12.75, 0.88, 1.7, "#24314a");
  addBox(office, 3.6, 0.09, 0.18, 11.0, 1.78, 3.0, RED, { opacity: 0.65 });
  addBox(office, 3.0, 0.9, 0.05, 11.0, 1.62, 2.92, "#17233a", { emissive: "#07101f" });
  addDesk(office, 11.0, 1.8, 2.6, "#4d3828");
  stampGroup.position.set(11.7, 1.12, 1.42);
  addCylinder(stampGroup, 0.06, 0.07, 0.52, 0, 0.42, 0, "#7a5a32", {}, 8);
  addBox(stampGroup, 0.62, 0.28, 0.5, 0, 0.06, 0, "#c92a2a");
  addBox(stampGroup, 0.42, 0.06, 0.34, 0, 0.23, 0, "#f26b6b", { cast: false });
  office.add(stampGroup);
  addDesk(office, 14.0, 4.2, 2.25);
  [0, 1, 2, 3, 4].forEach((index) => {
    const height = 0.12 + index * 0.07;
    addBox(office, 0.22, height, 0.14, 13.25 + index * 0.32, 1.1 + height / 2, 3.95, BLUE, {
      emissive: "#1d3f74",
      cast: false,
    });
  });

  // Execution: executor desk beside the paper door, plus the slip rail.
  addDesk(office, 14.7, -7.6, 2.2);
  addBox(office, 0.16, 0.05, 2.1, 15.35, 0.11, -9.3, ORANGE, { opacity: 0.4, cast: false });

  // Back office: auditor and the filing cabinets in the front-right corner.
  addBox(office, 1.35, 2.15, 0.85, 16.3, 1.08, 5.9, "#2b3852");
  [0.55, 1.12, 1.69].forEach((y) => {
    addBox(office, 1.18, 0.42, 0.04, 16.3, y, 6.35, "#1a2438");
    addBox(office, 0.22, 0.04, 0.05, 16.3, y, 6.4, "#8b97ad", { cast: false });
  });
  addBox(office, 1.0, 1.45, 0.75, 15.15, 0.73, 5.4, "#2b3852");
  [0.42, 0.92].forEach((y) => {
    addBox(office, 0.86, 0.36, 0.04, 15.15, y, 5.79, "#1a2438");
    addBox(office, 0.18, 0.035, 0.05, 15.15, y, 5.84, "#8b97ad", { cast: false });
  });

  // Coordinator platform in the centre of the floor.
  addCylinder(office, 2.15, 2.15, 0.22, 0.8, 0.11, 4.9, "#1b2940", {}, 24);
  addCylinder(office, 2.1, 2.1, 0.04, 0.8, 0.24, 4.9, ORANGE, { opacity: 0.5 }, 24);
  addBox(office, 1.25, 0.72, 0.65, 0.8, 0.6, 4.1, "#223149");
  addBox(office, 0.82, 0.42, 0.03, 0.8, 0.75, 4.45, "#5b8def", { emissive: "#17365c" });

  // Lounge corner.
  addBox(office, 3.1, 0.38, 1.25, -14.2, 0.42, 6.7, "#2a3852");
  addBox(office, 3.1, 0.9, 0.24, -14.2, 0.89, 7.27, "#24314a");
  addBox(office, 0.24, 0.62, 1.25, -15.65, 0.72, 6.7, "#24314a");
  addBox(office, 0.24, 0.62, 1.25, -12.75, 0.72, 6.7, "#24314a");
  addBox(office, 0.55, 0.12, 0.55, -14.6, 0.65, 6.68, YELLOW, { cast: false });
  addBox(office, 0.55, 0.12, 0.55, -13.8, 0.65, 6.68, YELLOW, { cast: false });
  addCylinder(office, 0.75, 0.75, 0.12, -14.2, 0.58, 4.9, "#5b3f2a", {}, 16);
  addCylinder(office, 0.11, 0.13, 0.55, -14.2, 0.29, 4.9, "#3b2c22", {}, 8);
  addPlant(office, -16.1, 7.2);
  addPlant(office, 16.9, 9.6);
}

function findPickable(object: THREE.Object3D | null): Record<string, unknown> | null {
  let node = object;
  while (node) {
    if (node.userData && typeof node.userData.kind === "string") return node.userData as Record<string, unknown>;
    node = node.parent;
  }
  return null;
}

export function Floor3D({
  scene,
  state,
  statuses,
  duckEnabled,
  screenTickers,
  onOpenDecision,
  onSelectRole,
  onUnsupported,
}: {
  scene: FloorScene;
  state: DeskState;
  statuses: Record<FloorRole, FloorStatus>;
  duckEnabled: boolean;
  screenTickers: FloorScene["screenTickers"];
  onOpenDecision: (id: string) => void;
  onSelectRole: (role: FloorRole) => void;
  onUnsupported: () => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const tagRefs = useRef<Record<string, HTMLElement | null>>({});
  const speechRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const screenRef = useRef<HTMLDivElement | null>(null);
  const tickerBoardRef = useRef<HTMLDivElement | null>(null);
  const coreLabelRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const satelliteLabelRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const doorRef = useRef<HTMLDivElement | null>(null);
  const stampRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLButtonElement | null>(null);
  const controllerRef = useRef<{
    update: (nextScene: FloorScene, nextState: DeskState, nextDuck: boolean) => void;
    reset: () => void;
  } | null>(null);
  const onOpenRef = useRef(onOpenDecision);
  const onSelectRef = useRef(onSelectRole);
  const unsupportedRef = useRef(onUnsupported);
  onOpenRef.current = onOpenDecision;
  onSelectRef.current = onSelectRole;
  unsupportedRef.current = onUnsupported;

  const isCoreTicker = (ticker: string): boolean =>
    (CORE_TICKERS as readonly string[]).includes(ticker);
  const corePositions = state.positions.filter((position) => isCoreTicker(position.ticker));
  const satellitePositions = state.positions
    .filter((position) => !isCoreTicker(position.ticker))
    .slice(0, 4);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const stage = host;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    } catch {
      unsupportedRef.current();
      return;
    }

    const canvas = renderer.domElement;
    canvas.className = "floor-canvas";
    canvas.setAttribute("role", "img");
    canvas.setAttribute(
      "aria-label",
      "Isometric voxel office with the MooWoo duck crew. Use the ticker line and controls below for the current event.",
    );
    stage.appendChild(canvas);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.04;

    const threeScene = new THREE.Scene();
    const background = new THREE.Color(BG);
    threeScene.background = background;

    const viewTarget = new THREE.Vector3(0, 1.1, 0);
    const viewOffset = new THREE.Vector3(1, 0.86, 1).normalize().multiplyScalar(64);
    let zoom = 1;
    const BASE_HEIGHT = 24;
    const FIT_WIDTH = 38.5;
    const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 180);
    const syncCamera = () => {
      camera.position.copy(viewTarget).add(viewOffset);
      camera.lookAt(viewTarget);
    };

    const hemi = new THREE.HemisphereLight(0xcfd9e8, 0x3a2b1c, 1.15);
    threeScene.add(hemi);
    const light = new THREE.DirectionalLight(0xfff2dd, 2.15);
    light.position.set(11, 25, 13);
    light.castShadow = true;
    light.shadow.mapSize.set(2048, 2048);
    light.shadow.camera.left = -25;
    light.shadow.camera.right = 25;
    light.shadow.camera.top = 25;
    light.shadow.camera.bottom = -25;
    light.shadow.camera.near = 1;
    light.shadow.camera.far = 80;
    light.shadow.bias = -0.0004;
    light.shadow.normalBias = 0.02;
    threeScene.add(light);

    const office = new THREE.Group();
    threeScene.add(office);
    const stampGroup = new THREE.Group();
    buildOffice(office, stampGroup);

    const ducksGroup = new THREE.Group();
    threeScene.add(ducksGroup);
    const ducks = new Map<string, DuckState>();
    FLOOR_DUCKS.forEach((spec) => {
      const duck = createDuck(spec);
      ducks.set(spec.id, duck);
      ducksGroup.add(duck.group);
    });
    const mascot = createMascot();
    mascot.visible = duckEnabled;
    threeScene.add(mascot);

    const tilesGroup = new THREE.Group();
    threeScene.add(tilesGroup);

    const slipGroup = new THREE.Group();
    addBox(slipGroup, 0.55, 0.34, 0.05, 0, 0, 0, ORANGE);
    addBox(slipGroup, 0.37, 0.03, 0.014, 0, 0.06, 0.035, "#7a2d04", { cast: false });
    addBox(slipGroup, 0.31, 0.03, 0.014, 0, -0.01, 0.035, "#7a2d04", { cast: false });
    addBox(slipGroup, 0.95, 0.72, 0.55, 0, 0, 0, ORANGE, {
      opacity: 0.001,
      cast: false,
      receive: false,
    });
    slipGroup.visible = false;
    threeScene.add(slipGroup);

    const paper = addBox(threeScene, 0.48, 0.36, 0.04, 0, 1.05, 0, "#e8edf6");
    addBox(paper, 0.34, 0.02, 0.012, 0, 0.05, 0.03, "#8b97ad", { cast: false });
    paper.visible = false;

    const debateCard = new THREE.Group();
    addBox(debateCard, 0.64, 0.46, 0.05, 0, 0, 0, VIOLET, { emissive: "#3d2f70" });
    addBox(debateCard, 0.54, 0.36, 0.02, 0, 0, 0.035, "#e8edf6");
    debateCard.position.set(-1.1, 1.28, -3.15);
    debateCard.visible = false;
    threeScene.add(debateCard);

    const pickRoots = [ducksGroup, slipGroup, tilesGroup, debateCard];
    let currentScene = scene;
    let currentState = state;
    let sceneStart = performance.now();
    let animationUntil = sceneStart;
    let actor: DuckState | null = null;
    let actorFrom = new THREE.Vector3();
    let actorTo = new THREE.Vector3();
    let stampActive = false;
    let newTile: THREE.Object3D | null = null;
    let stopTile: THREE.Object3D | null = null;
    let dragActive = false;

    function applyTier(tier: string): void {
      const palette =
        tier === "kill"
          ? { bg: "#240d0d", sky: "#f2a0a0", ground: "#3a1717", sun: "#ff9a8f" }
          : tier === "exits_only"
            ? { bg: "#20100f", sky: "#f2b0a0", ground: "#3a1d17", sun: "#ffb08f" }
            : tier === "reduced"
              ? { bg: "#1a1411", sky: "#e8c98a", ground: "#3a2b1c", sun: "#ffca7a" }
              : { bg: BG, sky: "#cfd9e8", ground: "#3a2b1c", sun: "#fff2dd" };
      background.set(palette.bg);
      hemi.color.set(palette.sky);
      hemi.groundColor.set(palette.ground);
      light.color.set(palette.sun);
    }

    function resetDucks(): void {
      ducks.forEach((duck) => {
        duck.group.position.set(duck.spec.x, 0, duck.spec.z);
        duck.group.rotation.set(0, duck.spec.rotation, 0);
        duck.bob.position.set(0, 0, 0);
        duck.bob.rotation.set(duck.lean, 0, 0);
      });
      actor = null;
      actorFrom.set(0, 0, 0);
      actorTo.set(0, 0, 0);
    }

    function buildTiles(nextState: DeskState, nextScene: FloorScene): void {
      while (tilesGroup.children.length > 0) {
        const child = tilesGroup.children.pop();
        if (child) tilesGroup.remove(child);
      }
      newTile = null;
      stopTile = null;
      const isCore = (ticker: string): boolean =>
        (CORE_TICKERS as readonly string[]).includes(ticker);
      const core = nextState.positions.filter((position) => isCore(position.ticker)).slice(0, 5);
      const satellites = nextState.positions.filter((position) => !isCore(position.ticker)).slice(0, 4);

      const addTile = (
        ticker: string,
        baseColor: string,
        decisionId: string | null,
        x: number,
        baseY: number,
        width: number,
        height: number,
      ): void => {
        const activeChange = nextScene.tile?.ticker === ticker ? nextScene.tile : null;
        const tileColor =
          activeChange?.action === "add"
            ? ORANGE
            : activeChange?.action === "red" || activeChange?.action === "remove"
              ? RED
              : baseColor;
        const tile = addBox(
          tilesGroup,
          width,
          height,
          0.11,
          x,
          baseY,
          -11.37,
          tileColor,
          { emissive: tileColor, opacity: 1 },
        );
        addBox(
          tilesGroup,
          width * 0.74,
          0.035,
          0.015,
          x,
          baseY + height * 0.24,
          -11.29,
          "#e8edf6",
          { cast: false },
        );
        tile.userData = { kind: "decision", decisionId, baseY };
        if (activeChange) {
          if (activeChange.action === "add") newTile = tile;
          if (activeChange.action === "remove") stopTile = tile;
          if (activeChange.action === "red") {
            const material = tile.material as THREE.MeshStandardMaterial;
            material.emissive.set(RED);
            material.emissiveIntensity = 1.2;
          }
        }
      };

      core.forEach((position, index) => {
        addTile(
          position.ticker,
          BLUE,
          position.decisionId,
          8 + (index - (core.length - 1) / 2) * 1.04,
          2.52,
          0.92,
          0.58,
        );
      });

      satellites.forEach((position, index) => {
        addTile(
          position.ticker,
          SLEEVE_COLORS[position.sleeve],
          position.decisionId,
          12.4,
          2.55 - index * 0.55,
          0.94,
          0.4,
        );
      });
    }

    function update(nextScene: FloorScene, nextState: DeskState, nextDuck: boolean): void {
      currentScene = nextScene;
      currentState = nextState;
      sceneStart = performance.now();
      animationUntil = sceneStart + nextScene.durationMs + 450;
      resetDucks();
      applyTier(nextState.tier);
      mascot.visible = nextDuck;

      if (nextScene.actorId && nextScene.actorTarget) {
        actor = ducks.get(nextScene.actorId) ?? null;
        if (actor) {
          actorFrom.set(actor.group.position.x, 0, actor.group.position.z);
          actorTo.set(nextScene.actorTarget.x, 0, nextScene.actorTarget.z);
        }
      }

      if (nextScene.slip) {
        slipGroup.visible = true;
        slipGroup.position.set(nextScene.slip.from.x, 1.42, nextScene.slip.from.z);
      } else {
        slipGroup.visible = false;
      }
      slipGroup.userData = nextScene.decisionId ? { kind: "decision", decisionId: nextScene.decisionId } : {};

      paper.visible = nextScene.kind === "rating";
      debateCard.visible = nextScene.kind === "rating" && nextScene.decisionId != null;
      debateCard.userData = nextScene.decisionId ? { kind: "decision", decisionId: nextScene.decisionId } : {};
      stampActive = nextScene.kind === "risk_verdict";
      buildTiles(nextState, nextScene);
      schedule();
    }

    function updateMotion(now: number): void {
      const elapsed = now - sceneStart;
      const animating = now < animationUntil;
      const actorDuration = actor?.spec.id === "quick" ? 700 : 950;
      if (actor) {
        const t = Math.max(0, Math.min(1, elapsed / actorDuration));
        const eased = t * t * (3 - 2 * t);
        actor.group.position.set(
          actorFrom.x + (actorTo.x - actorFrom.x) * eased,
          0,
          actorFrom.z + (actorTo.z - actorFrom.z) * eased,
        );
        const dx = actorTo.x - actorFrom.x;
        const dz = actorTo.z - actorFrom.z;
        if (t > 0.02) actor.group.rotation.y = Math.atan2(dx, dz);
        if (t < 1) {
          actor.bob.position.y = Math.abs(Math.sin(elapsed * 0.021)) * 0.075;
          actor.bob.rotation.z = Math.sin(elapsed * 0.021) * 0.09;
        }
      }

      const watcher = ducks.get("watcher");
      if (watcher && watcher !== actor && animating && currentScene.kind !== "stop_hit" && currentScene.kind !== "halt") {
        const t = elapsed / 1900;
        const x = -14.0 + Math.sin(t * Math.PI * 2) * 0.9;
        const z = -2.6 + Math.cos(t * Math.PI * 2) * 2.2;
        watcher.group.position.set(x, 0, z);
        watcher.group.rotation.y = Math.atan2(
          Math.cos(t * Math.PI * 2) * 0.9,
          -Math.sin(t * Math.PI * 2) * 2.2,
        );
        watcher.bob.position.y = Math.abs(Math.sin(elapsed * 0.018)) * 0.055;
        watcher.bob.rotation.z = Math.sin(elapsed * 0.018) * 0.07;
      }

      if (mascot.visible) {
        const t = now * 0.00028;
        const mx = 5.75 + Math.sin(t * 1.3) * 3.4;
        const mz = 7.0 + Math.cos(t) * 2.3;
        mascot.position.set(mx, 0, mz);
        mascot.rotation.y = Math.atan2(Math.cos(t * 1.3) * 3.4, -Math.sin(t) * 2.3);
        mascot.children[0].position.y = Math.abs(Math.sin(now * 0.003)) * 0.05;
      }

      if (paper.visible && actor) {
        paper.position.set(actor.group.position.x + 0.25, 1.08, actor.group.position.z + 0.5);
        paper.rotation.y = actor.group.rotation.y + 0.15;
      }

      if (slipGroup.visible && currentScene.slip) {
        const t = Math.max(0, Math.min(1, (elapsed - 240) / 820));
        const eased = t * t * (3 - 2 * t);
        const from = currentScene.slip.from;
        const to = currentScene.slip.to;
        slipGroup.position.set(
          from.x + (to.x - from.x) * eased,
          1.4 + Math.sin(t * Math.PI) * 0.38,
          from.z + (to.z - from.z) * eased,
        );
        slipGroup.rotation.y = Math.atan2(to.x - from.x, to.z - from.z);
      }

      if (stampActive) {
        const t = Math.max(0, Math.min(1, (elapsed - 260) / 520));
        stampGroup.position.y = 1.12 + (1 - t) * 0.72;
      } else {
        stampGroup.position.y = 1.12;
      }

      if (newTile) {
        const t = Math.max(0, Math.min(1, elapsed / 620));
        newTile.scale.set(t, t, 1);
      }
      if (stopTile) {
        const t = Math.max(0, Math.min(1, elapsed / 1650));
        stopTile.scale.set(1 - t * 0.95, 1 - t * 0.95, 1);
        stopTile.position.y = ((stopTile.userData.baseY as number | undefined) ?? 2.73) - t * 0.4;
        if (t >= 1) stopTile.visible = false;
      }

      if (!animating && actor) {
        actor.bob.position.y = 0;
        actor.bob.rotation.z = 0;
      }
    }

    function project(x: number, y: number, z: number): { x: number; y: number; visible: boolean } {
      const point = new THREE.Vector3(x, y, z).project(camera);
      const rect = stage.getBoundingClientRect();
      return {
        x: (point.x * 0.5 + 0.5) * rect.width,
        y: (-point.y * 0.5 + 0.5) * rect.height,
        visible: point.z > -1 && point.z < 1,
      };
    }

    function place(
      element: HTMLElement | null,
      x: number,
      y: number,
      z: number,
      opacity = 1,
    ): void {
      if (!element) return;
      const point = project(x, y, z);
      element.style.left = `${point.x}px`;
      element.style.top = `${point.y}px`;
      element.style.opacity = point.visible ? String(opacity) : "0";
    }

    type ScreenBox = { left: number; right: number; top: number; bottom: number };
    function visibleBox(
      element: HTMLElement | null,
      mode: "tag" | "bottom" | "center",
      leader = 0,
    ): ScreenBox | null {
      if (!element || element.style.opacity === "0") return null;
      const left = Number.parseFloat(element.style.left);
      const top = Number.parseFloat(element.style.top);
      if (!Number.isFinite(left) || !Number.isFinite(top)) return null;
      const half = element.offsetWidth / 2;
      const height = element.offsetHeight;
      if (mode === "center") {
        return { left: left - half, right: left + half, top: top - height / 2, bottom: top + height / 2 };
      }
      const bottom = top - leader;
      return { left: left - half, right: left + half, top: bottom - height, bottom };
    }
    function intersects(a: ScreenBox, b: ScreenBox, pad: number): boolean {
      return (
        a.left < b.right + pad &&
        b.left - pad < a.right &&
        a.top < b.bottom + pad &&
        b.top - pad < a.bottom
      );
    }
    function placeClear(
      element: HTMLElement | null,
      x: number,
      y: number,
      z: number,
      offsets: Array<[number, number]>,
      obstacles: ScreenBox[],
      pad: number,
    ): boolean {
      if (!element) return false;
      const width = element.offsetWidth;
      const height = element.offsetHeight;
      const rect = stage.getBoundingClientRect();
      for (const [dx, dy] of offsets) {
        const point = project(x + dx, y + dy, z);
        if (!point.visible) continue;
        const box: ScreenBox = {
          left: point.x - width / 2,
          right: point.x + width / 2,
          top: point.y - height,
          bottom: point.y,
        };
        if (box.left < 6 || box.right > rect.width - 6 || box.top < 6 || box.bottom > rect.height - 6) {
          continue;
        }
        if (obstacles.some((obstacle) => intersects(box, obstacle, pad))) continue;
        element.style.left = `${point.x}px`;
        element.style.top = `${point.y}px`;
        element.style.opacity = "1";
        return true;
      }
      place(element, x, y, z);
      return false;
    }

    function placeDock(element: HTMLElement | null): void {
      if (!element) return;
      element.style.left = `${14 + element.offsetWidth / 2}px`;
      element.style.top = `${14 + element.offsetHeight}px`;
      element.style.opacity = "1";
    }

    const CARD_OFFSETS: Array<[number, number]> = [];
    const cardLifts = [0, 0.9, 1.8, 2.7, 3.6, 4.5, -0.9, -1.8, -2.7, -3.6, -4.5];
    const cardShifts = [0, 1.5, -1.5, 3, -3, 4.5, -4.5, 6, -6, 7.5, -7.5, 9, -9, 10.5, -10.5, 12, -12];
    for (const dy of cardLifts) {
      for (const dx of cardShifts) CARD_OFFSETS.push([dx, dy]);
    }
    CARD_OFFSETS.sort((a, b) => Math.abs(a[0]) * 1.2 + Math.abs(a[1]) - (Math.abs(b[0]) * 1.2 + Math.abs(b[1])));

    function speechOffsets(side: number): Array<[number, number]> {
      const offsets: Array<[number, number]> = [];
      for (const lift of [0, 1, 2, 3, 4]) {
        for (const spread of [0, 1]) offsets.push([side * spread, lift]);
        if (lift > 0) {
          for (const spread of [0, 1]) offsets.push([side * spread, -lift]);
        }
      }
      return offsets;
    }

    function activeDuckIds(): Set<string> {
      const active = new Set<string>();
      if (currentScene.actorId) active.add(currentScene.actorId);
      currentScene.speech.forEach((speech) => active.add(speech.role));
      if (currentScene.stamp) active.add("risk");
      if (currentScene.slip) active.add("executor");
      if (currentScene.card?.kind === "report") active.add("auditor");
      if (currentScene.card?.kind === "rating" && !currentScene.actorId) active.add("manager");
      return active;
    }

    function updateOverlays(): void {
      const active = activeDuckIds();
      FLOOR_DUCKS.forEach((spec) => {
        const duck = ducks.get(spec.id);
        if (!duck) return;
        const y = (spec.role === "scheduler" ? 2.42 : 2.32) * Math.max(spec.scale, 0.9);
        place(
          tagRefs.current[spec.id],
          duck.group.position.x,
          y + (TAG_LIFT[spec.id] ?? 0),
          duck.group.position.z,
          active.size > 0 && !active.has(spec.id) ? 0.5 : 1,
        );
      });
      place(
        tagRefs.current.mascot,
        mascot.position.x,
        2.34,
        mascot.position.z,
        active.size > 0 ? 0.5 : 1,
      );
      const tagBoxes = [
        ...FLOOR_DUCKS.map((spec) => visibleBox(tagRefs.current[spec.id], "tag", 12)),
        visibleBox(tagRefs.current.mascot, "tag", 12),
      ].filter((box): box is ScreenBox => box !== null);
      const speechBoxes: ScreenBox[] = [];
      currentScene.speech.forEach((speech) => {
        const duck = speech.role === "bull" ? ducks.get("bull") : ducks.get("bear");
        if (!duck) return;
        const side = speech.role === "bull" ? -2.1 : 2.1;
        placeClear(
          speechRefs.current[speech.role],
          duck.group.position.x + side,
          3.85,
          duck.group.position.z,
          speechOffsets(side),
          tagBoxes,
          3,
        );
        const box = visibleBox(speechRefs.current[speech.role], "bottom");
        if (box) speechBoxes.push(box);
      });
      place(screenRef.current, 0, 2.23, -11.38);
      place(tickerBoardRef.current, -10.8, 2.2, -11.38);
      const coreNow = currentState.positions
        .filter((position) => (CORE_TICKERS as readonly string[]).includes(position.ticker))
        .slice(0, 5);
      coreNow.forEach((position, index) => {
        place(
          coreLabelRefs.current[position.ticker],
          8 + (index - (coreNow.length - 1) / 2) * 1.04,
          2.52,
          -11.29,
        );
      });
      const satelliteNow = currentState.positions
        .filter((position) => !(CORE_TICKERS as readonly string[]).includes(position.ticker))
        .slice(0, 4);
      satelliteNow.forEach((position, index) => {
        place(satelliteLabelRefs.current[position.ticker], 12.4, 2.55 - index * 0.55, -11.29);
      });
      place(doorRef.current, 15.35, 2.9, -11.32);
      if (currentScene.stamp) place(stampRef.current, 11.7, 2.55, 1.42);
      const wallBoxes = [
        visibleBox(screenRef.current, "center"),
        visibleBox(tickerBoardRef.current, "center"),
        visibleBox(doorRef.current, "center"),
        ...coreNow.map((position) => visibleBox(coreLabelRefs.current[position.ticker], "center")),
        ...satelliteNow.map((position) => visibleBox(satelliteLabelRefs.current[position.ticker], "center")),
      ].filter((box): box is ScreenBox => box !== null);
      const cardObstacles = [...tagBoxes, ...speechBoxes, ...wallBoxes];
      if (currentScene.card?.kind === "rating") {
        const rater = currentScene.actorId === "quick" ? ducks.get("quick") : ducks.get("manager");
        if (rater) {
          const placed = placeClear(
            cardRef.current,
            rater.group.position.x,
            2.55,
            rater.group.position.z,
            CARD_OFFSETS,
            cardObstacles,
            5,
          );
          if (!placed) placeDock(cardRef.current);
        }
      } else if (currentScene.card?.kind === "report") {
        const auditor = ducks.get("auditor");
        if (auditor) {
          const placed = placeClear(
            cardRef.current,
            auditor.group.position.x,
            2.55,
            auditor.group.position.z,
            CARD_OFFSETS,
            cardObstacles,
            5,
          );
          if (!placed) placeDock(cardRef.current);
        }
      } else if (currentScene.card?.kind === "outcome") {
        place(cardRef.current, 8.2, 3.28, -9.4);
      }
    }

    let raf = 0;
    let scheduled = false;
    function frame(now: number): void {
      scheduled = false;
      if (document.hidden) return;
      updateMotion(now);
      renderer.render(threeScene, camera);
      updateOverlays();
      if (now < animationUntil || dragActive || mascot.visible) schedule();
    }
    function schedule(): void {
      if (scheduled || document.hidden) return;
      scheduled = true;
      raf = window.requestAnimationFrame(frame);
    }

    function setSize(): void {
      const rect = stage.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      const aspect = width / height;
      const viewHeight = Math.max(BASE_HEIGHT, FIT_WIDTH / aspect);
      const halfHeight = viewHeight / zoom / 2;
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      syncCamera();
      schedule();
    }

    const resizeObserver = new ResizeObserver(setSize);
    resizeObserver.observe(host);
    setSize();

    let dragMoved = 0;
    let lastX = 0;
    let lastY = 0;
    let pinchDistance = 0;
    let suppressClick = false;
    const pointers = new Map<number, { x: number; y: number }>();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const onPointerDown = (event: PointerEvent) => {
      canvas.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 1) {
        dragActive = true;
        dragMoved = 0;
        lastX = event.clientX;
        lastY = event.clientY;
        suppressClick = false;
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
        dragActive = true;
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchDistance > 0) {
          zoom = Math.max(0.72, Math.min(2.35, zoom * (distance / pinchDistance)));
          pinchDistance = distance;
          setSize();
        }
        return;
      }
      if (!dragActive) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      dragMoved += Math.abs(dx) + Math.abs(dy);
      if (dragMoved < 2) return;
      const rect = stage.getBoundingClientRect();
      const worldPerPixel = (camera.top - camera.bottom) / Math.max(1, rect.height);
      const forward = new THREE.Vector3();
      camera.getWorldDirection(forward);
      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
      const flat = new THREE.Vector3(forward.x, 0, forward.z).normalize();
      viewTarget.addScaledVector(right, -dx * worldPerPixel);
      viewTarget.addScaledVector(flat, dy * worldPerPixel);
      viewTarget.x = Math.max(-7, Math.min(7, viewTarget.x));
      viewTarget.z = Math.max(-6, Math.min(6, viewTarget.z));
      viewTarget.y = 1.1;
      syncCamera();
      schedule();
    };

    const onPointerUp = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinchDistance = 0;
      if (pointers.size === 0) {
        if (dragMoved > 5) suppressClick = true;
        dragActive = false;
        schedule();
      }
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoom = Math.max(0.72, Math.min(2.35, zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
      setSize();
    };

    const onClick = (event: MouseEvent) => {
      if (suppressClick) {
        suppressClick = false;
        return;
      }
      const rect = canvas.getBoundingClientRect();
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(pickRoots, true);
      for (const hit of hits) {
        const pick = findPickable(hit.object);
        if (!pick) continue;
        if (pick.kind === "role" && typeof pick.role === "string") {
          onSelectRef.current(pick.role as FloorRole);
          return;
        }
        if (pick.kind === "decision" && typeof pick.decisionId === "string") {
          onOpenRef.current(pick.decisionId);
          return;
        }
      }
    };

    const onVisibility = () => {
      if (document.hidden) {
        window.cancelAnimationFrame(raf);
        scheduled = false;
      } else {
        schedule();
      }
    };

    const getCanvas = () => canvas;
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("click", onClick);
    document.addEventListener("visibilitychange", onVisibility);

    const resetView = () => {
      zoom = 1;
      viewTarget.set(0, 1.1, 0);
      setSize();
    };

    controllerRef.current = {
      update(nextScene, nextState, nextDuck) {
        update(nextScene, nextState, nextDuck);
      },
      reset: resetView,
    };
    update(scene, state, duckEnabled);

    return () => {
      window.cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("click", onClick);
      resizeObserver.disconnect();
      controllerRef.current = null;
      threeScene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((item) => item.dispose());
          else material.dispose();
        }
      });
      renderer.dispose();
      if (getCanvas().parentElement === stage) stage.removeChild(getCanvas());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    controllerRef.current?.update(scene, state, duckEnabled);
  }, [scene, state, duckEnabled]);

  return (
    <div className="floor-stage" ref={hostRef}>
      <div className="floor-tag-layer">
        {FLOOR_DUCKS.map((spec) => (
          <button
            key={spec.id}
            type="button"
            ref={(element) => {
              tagRefs.current[spec.id] = element;
            }}
            className={`floor-tag status-${statuses[spec.role]}`}
            onClick={() => onSelectRole(spec.role)}
            aria-label={`${spec.label}, ${statuses[spec.role]}. Show handled events.`}
          >
            <span className={`floor-tag-dot ${statuses[spec.role]}`} aria-hidden="true" />
            {spec.label}
          </button>
        ))}
        {duckEnabled ? (
          <span
            className="floor-tag mascot"
            ref={(element) => {
              tagRefs.current.mascot = element;
            }}
          >
            <span className="floor-tag-dot idle" aria-hidden="true" />
            Mascot
          </span>
        ) : null}
      </div>

      {scene.speech.map((speech) => (
        <div
          key={speech.role}
          ref={(element) => {
            speechRefs.current[speech.role] = element;
          }}
          className={`floor-speech ${speech.role}`}
        >
          <strong>{speech.role === "bull" ? "Bull" : "Bear"}</strong>
          <span>{speech.text}</span>
        </div>
      ))}

      <div ref={screenRef} className="floor-wall-screen" aria-hidden="true">
        <span className="floor-screen-label">Equity</span>
        <strong>{state.equity == null ? "—" : fmtUsd(state.equity, 0)}</strong>
        <span className={`floor-screen-tier tier-${state.tier}`}>{state.tier.replaceAll("_", " ")}</span>
      </div>

      <div ref={tickerBoardRef} className="floor-ticker-board" aria-hidden="true">
        {screenTickers.length === 0 ? (
          <span className="floor-board-empty">awaiting screen</span>
        ) : (
          screenTickers.slice(0, 6).map((ticker, index) => (
            <span
              key={ticker.ticker}
              className={ticker.picked ? "floor-screen-ticker is-picked" : "floor-screen-ticker"}
              style={{ animationDelay: `${index * 90}ms` }}
            >
              {ticker.ticker}
              <i className={ticker.movePct >= 0 ? "up" : "down"}>
                {ticker.movePct >= 0 ? "+" : ""}
                {ticker.movePct.toFixed(1)}
              </i>
            </span>
          ))
        )}
      </div>

      {corePositions.map((position) => (
        <span
          key={position.ticker}
          ref={(element) => {
            coreLabelRefs.current[position.ticker] = element;
          }}
          className="floor-board-ticker is-core"
          aria-hidden="true"
        >
          <i />
          {position.ticker}
        </span>
      ))}

      {satellitePositions.map((position) => (
        <span
          key={position.ticker}
          ref={(element) => {
            satelliteLabelRefs.current[position.ticker] = element;
          }}
          className={`floor-board-ticker is-satellite satellite-${position.sleeve}`}
          aria-hidden="true"
        >
          <i />
          {position.ticker}
        </span>
      ))}

      <div ref={doorRef} className="floor-door-label" aria-hidden="true">
        Moomoo paper
      </div>

      {scene.stamp ? (
        <div ref={stampRef} className={`floor-stamp tone-${scene.stamp.tone}`} aria-hidden="true">
          <strong>{scene.stamp.label}</strong>
          <span>{scene.stamp.rule ?? "rules checked"}</span>
        </div>
      ) : null}

      {scene.card && scene.card.kind !== "drill" && scene.card.kind !== "tier" && scene.card.kind !== "halt" && scene.card.kind !== "rule" ? (
        <button
          type="button"
          ref={cardRef}
          className={`floor-world-card tone-${scene.card.tone}`}
          onClick={() => {
            if (scene.decisionId) onOpenDecision(scene.decisionId);
          }}
          disabled={!scene.decisionId}
          aria-label={`${scene.card.title}. ${scene.card.body}${scene.decisionId ? ". Open decision." : ""}`}
        >
          <strong>{scene.card.title}</strong>
          <span>{scene.card.body}</span>
        </button>
      ) : null}

      {scene.card && (scene.card.kind === "drill" || scene.card.kind === "tier" || scene.card.kind === "halt" || scene.card.kind === "rule") ? (
        <div className={`floor-banner tone-${scene.card.tone}`} role="status">
          <strong>{scene.card.title}</strong>
          <span>{scene.card.body}</span>
        </div>
      ) : null}

      <div className="floor-view-hint" aria-hidden="true">
        Drag to pan · wheel or pinch to zoom
      </div>
      <button type="button" className="floor-reset" onClick={() => controllerRef.current?.reset()}>
        Reset view
      </button>
    </div>
  );
}
