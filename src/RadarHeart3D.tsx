import React, { useEffect, useMemo, useRef } from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { RadarHeartData, RadarHeartScene, ResolvedSlide } from "./types";
import { createRaymarchHero } from "./RadarRaymarch";

/** A/B switch: true restores the polygon-primitive hero (kept only for comparison). */
const LEGACY_PRIMITIVE_HERO = false;

/**
 * Year-3026 Photonic Sanctum 3D Stage (`radar_heart_3d`).
 *
 * Architecture:
 * - Layer 1: Optional 4K/HD looping futuristic world (`OffthreadVideo` via `heart3d.bg_video`)
 *   replacing flat black space with living liquid-gold oceans, light cathedrals, aurora spectra,
 *   bioluminescent waves, and vortex portals — gently graded + breathing Ken Burns motion.
 * - Layer 2: Transparent WebGL2 Three.js stage (`alpha: true`, `clearAlpha = 0`, `scene.background = null`)
 *   with physical IBL (`PMREMGenerator` + `RoomEnvironment`), real high-res Pixabay PBR textures
 *   (`ruby_magma`, `liquid_gold`, `emerald_vein`, `sapphire_circuit`), custom GLSL Fresnel &
 *   volumetric halo shaders, and 10 unique sculptural artifacts driven deterministically by `frame`.
 * - Layer 3: Ultra-clean floating liquid-glass telemetry HUD that keeps ~80% of the canvas unobstructed.
 */

const TEX_PATHS = {
  ruby: "cinema/world3026/textures/ruby_magma.jpg",
  gold: "cinema/world3026/textures/liquid_gold.jpg",
  emerald: "cinema/world3026/textures/emerald_vein.jpg",
  sapphire: "cinema/world3026/textures/sapphire_circuit.jpg",
} as const;

type TexturePack = {
  ruby: THREE.Texture | null;
  gold: THREE.Texture | null;
  emerald: THREE.Texture | null;
  sapphire: THREE.Texture | null;
};

type StageHandle = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  pmrem: THREE.PMREMGenerator;
  envTex: THREE.Texture;
  update: (t: number, progress: number) => void;
  dispose: () => void;
};

// ---------------------------------------------------------------------------
// Custom GLSL shaders (Fresnel iridescent shield, flowing plasma arteries, volumetric halo)
// ---------------------------------------------------------------------------

function createFresnelShieldMaterial(
  colorAHex: number,
  colorBHex: number,
  opacity = 0.42
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
    uniforms: {
      uTime: { value: 0 },
      uPulse: { value: 0 },
      uColorA: { value: new THREE.Color(colorAHex) },
      uColorB: { value: new THREE.Color(colorBHex) },
      uOpacity: { value: opacity },
    },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      varying vec3 vPos;
      uniform float uTime;
      uniform float uPulse;
      void main() {
        vPos = position;
        float wave = sin(position.y * 5.0 - uTime * 3.8 + position.x * 3.2) * (0.025 + uPulse * 0.055);
        vec3 displaced = position + normal * wave;
        vec4 mvPos = modelViewMatrix * vec4(displaced, 1.0);
        vNormal = normalize(normalMatrix * normal);
        vViewDir = normalize(-mvPos.xyz);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      varying vec3 vPos;
      uniform float uTime;
      uniform float uPulse;
      uniform vec3 uColorA;
      uniform vec3 uColorB;
      uniform float uOpacity;
      void main() {
        float ndotv = abs(dot(normalize(vNormal), normalize(vViewDir)));
        float fresnel = pow(1.0 - clamp(ndotv, 0.0, 1.0), 2.15);
        float bands = 0.5 + 0.5 * sin(vPos.y * 10.0 + vPos.x * 6.0 - uTime * 4.5);
        float hex = 0.5 + 0.5 * cos(atan(vPos.z, vPos.x) * 14.0 + vPos.y * 8.0 + uTime * 2.4);
        vec3 col = mix(uColorA, uColorB, clamp(bands * 0.65 + hex * 0.35, 0.0, 1.0));
        float alpha = clamp((fresnel * 1.15 + bands * 0.14 + uPulse * 0.25) * uOpacity, 0.0, 0.92);
        gl_FragColor = vec4(col * (1.25 + fresnel * 1.4 + uPulse * 0.9), alpha);
      }
    `,
  });
}

function createArteryFlowMaterial(
  baseHex: number,
  pulseHex: number
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uBase: { value: new THREE.Color(baseHex) },
      uPulse: { value: new THREE.Color(pulseHex) },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec2 vUv;
      uniform float uTime;
      uniform vec3 uBase;
      uniform vec3 uPulse;
      void main() {
        float flow1 = smoothstep(0.0, 0.12, fract(vUv.x * 2.2 - uTime * 0.85))
                    * (1.0 - smoothstep(0.12, 0.32, fract(vUv.x * 2.2 - uTime * 0.85)));
        float flow2 = smoothstep(0.0, 0.08, fract(vUv.x * 4.5 - uTime * 1.4 + 0.4))
                    * (1.0 - smoothstep(0.08, 0.20, fract(vUv.x * 4.5 - uTime * 1.4 + 0.4)));
        float core = 0.48 + 0.52 * sin(vUv.y * 3.14159);
        vec3 col = mix(uBase, uPulse, clamp(flow1 * 1.1 + flow2 * 0.7, 0.0, 1.0));
        float alpha = clamp((0.35 + flow1 * 0.65 + flow2 * 0.4) * core, 0.0, 1.0);
        gl_FragColor = vec4(col * (1.1 + flow1 * 1.5), alpha);
      }
    `,
  });
}

function createVolumetricHalo(
  radius: number,
  colorHex: number,
  intensity = 0.55
): THREE.Mesh {
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.BackSide,
    uniforms: {
      uColor: { value: new THREE.Color(colorHex) },
      uIntensity: { value: intensity },
    },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
        vNormal = normalize(normalMatrix * normal);
        vViewDir = normalize(-mvPos.xyz);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      uniform vec3 uColor;
      uniform float uIntensity;
      void main() {
        float rim = pow(clamp(dot(-vNormal, vViewDir), 0.0, 1.0), 2.4);
        gl_FragColor = vec4(uColor * (1.4 * uIntensity), rim * uIntensity);
      }
    `,
  });
  return new THREE.Mesh(new THREE.SphereGeometry(radius, 36, 28), mat);
}

// ---------------------------------------------------------------------------
// Sculptural Geometry Builders (Haute-Horology 3026 Artifacts)
// ---------------------------------------------------------------------------

/** Living anatomical-technological multi-chamber heart with golden coronary vessels. */
function buildLivingHeartGroup(
  tex: TexturePack,
  scale = 1.0
): {
  group: THREE.Group;
  coreMat: THREE.MeshPhysicalMaterial;
  haloMat: THREE.ShaderMaterial;
  veins: THREE.ShaderMaterial[];
} {
  const group = new THREE.Group();
  group.scale.setScalar(scale);

  // Sculpted asymmetric dual-ventricle silhouette (organic, anatomical, NOT a flat cartoon icon)
  const coreMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0xc8123a),
    map: tex.ruby,
    bumpMap: tex.ruby,
    bumpScale: 0.06,
    emissive: new THREE.Color(0x9e0a2c),
    emissiveMap: tex.ruby,
    emissiveIntensity: 0.88,
    roughness: 0.14,
    metalness: 0.28,
    clearcoat: 1.0,
    clearcoatRoughness: 0.06,
    iridescence: 0.85,
    iridescenceIOR: 1.45,
    envMapIntensity: 2.3,
  });

  // Main left ventricle chamber (organic deformed icosahedron)
  const lvGeo = new THREE.IcosahedronGeometry(1.12, 4);
  const pos = lvGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    let x = pos.getX(i);
    let y = pos.getY(i);
    let z = pos.getZ(i);
    // Taper apex downward-left, bulge upper muscular base
    const yn = y / 1.12;
    const taper = yn < 0 ? 1.0 + yn * 0.42 : 1.0 + (1.0 - yn) * 0.12;
    const rib = 1.0 + 0.045 * Math.sin(Math.atan2(z, x) * 6.0 + y * 3.5);
    x = x * taper * 0.92 * rib + (yn < 0 ? yn * 0.22 : 0);
    y = y * 1.24;
    z = z * taper * 0.84 * rib;
    pos.setXYZ(i, x, y, z);
  }
  lvGeo.computeVertexNormals();
  const leftVentricle = new THREE.Mesh(lvGeo, coreMat);
  leftVentricle.position.set(-0.18, -0.08, 0.06);
  leftVentricle.rotation.z = 0.14;
  group.add(leftVentricle);

  // Right ventricle & atrium sculptural lobe
  const rvGeo = new THREE.SphereGeometry(0.86, 40, 32);
  rvGeo.scale(0.88, 1.14, 0.82);
  const rightVentricle = new THREE.Mesh(rvGeo, coreMat);
  rightVentricle.position.set(0.46, 0.22, -0.05);
  rightVentricle.rotation.z = -0.22;
  group.add(rightVentricle);

  // Sculpted crystalline 24K liquid-gold Aortic Arch & Pulmonary Trunk
  const goldMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0xffd466),
    bumpMap: tex.gold,
    bumpScale: 0.035,
    emissive: new THREE.Color(0x6e3d06),
    emissiveIntensity: 0.55,
    metalness: 0.96,
    roughness: 0.13,
    clearcoat: 1.0,
    envMapIntensity: 2.8,
  });

  const aortaCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.08, 0.95, 0.04),
    new THREE.Vector3(-0.22, 1.65, 0.1),
    new THREE.Vector3(0.28, 1.98, -0.06),
    new THREE.Vector3(0.74, 1.48, -0.26),
    new THREE.Vector3(0.56, 0.85, -0.35),
  ]);
  group.add(new THREE.Mesh(new THREE.TubeGeometry(aortaCurve, 56, 0.21, 20, false), goldMat));

  const trunkCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.35, 0.82, 0.22),
    new THREE.Vector3(0.08, 1.48, 0.34),
    new THREE.Vector3(-0.58, 1.68, 0.18),
  ]);
  group.add(new THREE.Mesh(new THREE.TubeGeometry(trunkCurve, 40, 0.15, 16, false), goldMat));

  // 3 branching golden aortic crown arteries
  const branchOffsets = [-0.22, 0.08, 0.36];
  branchOffsets.forEach((bx, idx) => {
    const bCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(bx, 1.82 + idx * 0.05, 0.02),
      new THREE.Vector3(bx * 1.15 - 0.06, 2.38, 0.08 - idx * 0.05),
    ]);
    group.add(new THREE.Mesh(new THREE.TubeGeometry(bCurve, 18, 0.072, 12, false), goldMat));
  });

  // Glowing photonic coronary arteries wrapping the heart surface
  const veins: THREE.ShaderMaterial[] = [];
  for (let k = 0; k < 6; k++) {
    const a0 = (k / 6) * Math.PI * 2;
    const pts: THREE.Vector3[] = [];
    for (let s = 0; s <= 12; s++) {
      const f = s / 12;
      const y = 1.1 - f * 2.45;
      const r = 0.96 * Math.sin(f * Math.PI * 0.88 + 0.18) + 0.18;
      const ang = a0 + f * 1.45 + Math.sin(f * 6.0 + k) * 0.22;
      pts.push(new THREE.Vector3(Math.cos(ang) * r, y, Math.sin(ang) * r * 0.88));
    }
    const vMat = createArteryFlowMaterial(0xff3366, 0xffe484);
    veins.push(vMat);
    group.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 44, 0.042, 10, false), vMat));
  }

  // Inner volumetric ruby-gold radiance halo
  const halo = createVolumetricHalo(2.35, 0xff2f64, 0.65);
  group.add(halo);

  return { group, coreMat, haloMat: halo.material as THREE.ShaderMaterial, veins };
}

/** Impossible Year-3026 Twisted Spherical Mobius Shield enveloping the Heart. */
function buildTwistedShield(
  tex: TexturePack,
  radius = 2.95
): {
  group: THREE.Group;
  knot: THREE.Mesh;
  innerKnot: THREE.Mesh;
  shellMat: THREE.ShaderMaterial;
  rings: THREE.Mesh[];
} {
  const group = new THREE.Group();

  // Outer twisted sacred-geometry 24K liquid-gold torus knot cage
  const goldCageMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0xffd66e),
    bumpMap: tex.gold,
    bumpScale: 0.03,
    emissive: new THREE.Color(0x663a08),
    emissiveIntensity: 0.52,
    metalness: 0.96,
    roughness: 0.12,
    clearcoat: 1.0,
    envMapIntensity: 2.8,
  });
  const knot = new THREE.Mesh(
    new THREE.TorusKnotGeometry(radius * 0.82, 0.072, 220, 22, 3, 7),
    goldCageMat
  );
  group.add(knot);

  // Counter-rotating cyan-opal inner plasma spiral
  const opalMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0x70f8ff),
    emissive: new THREE.Color(0x18a8d8),
    emissiveIntensity: 0.85,
    metalness: 0.35,
    roughness: 0.08,
    iridescence: 1.0,
    iridescenceIOR: 1.6,
    clearcoat: 1.0,
    transparent: true,
    opacity: 0.88,
  });
  const innerKnot = new THREE.Mesh(
    new THREE.TorusKnotGeometry(radius * 0.72, 0.044, 180, 16, 2, 5),
    opalMat
  );
  group.add(innerKnot);

  // Iridescent Fresnel plasma sphere membrane
  const shellMat = createFresnelShieldMaterial(0x38e8ff, 0xffc857, 0.52);
  const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(radius, 4), shellMat);
  group.add(shell);

  // 3 Gyroscopic astrolabe rings with crystalline studs
  const rings: THREE.Mesh[] = [];
  const ringColors = [0xffcf6a, 0x3ef2ff, 0xff5a8a];
  for (let i = 0; i < 3; i++) {
    const rMat = new THREE.MeshPhysicalMaterial({
      color: ringColors[i],
      emissive: ringColors[i],
      emissiveIntensity: 0.55,
      metalness: 0.9,
      roughness: 0.14,
      clearcoat: 1.0,
    });
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius + 0.25 + i * 0.28, 0.032, 16, 128),
      rMat
    );
    ring.rotation.set(i * 0.72, i * 1.05, 0.35);
    group.add(ring);
    rings.push(ring);
  }

  return { group, knot, innerKnot, shellMat, rings };
}

/** Haute-horology toothed golden gear wheel. */
function buildGoldenGear(
  outerR: number,
  innerR: number,
  teeth: number,
  thickness: number,
  mat: THREE.Material
): THREE.Mesh {
  const shape = new THREE.Shape();
  const step = (Math.PI * 2) / teeth;
  for (let i = 0; i < teeth; i++) {
    const a0 = i * step;
    const a1 = a0 + step * 0.22;
    const a2 = a0 + step * 0.45;
    const a3 = a0 + step * 0.68;
    const rTip = outerR + outerR * 0.11;
    const p0x = Math.cos(a0) * outerR;
    const p0y = Math.sin(a0) * outerR;
    if (i === 0) shape.moveTo(p0x, p0y);
    else shape.lineTo(p0x, p0y);
    shape.lineTo(Math.cos(a1) * rTip, Math.sin(a1) * rTip);
    shape.lineTo(Math.cos(a2) * rTip, Math.sin(a2) * rTip);
    shape.lineTo(Math.cos(a3) * outerR, Math.sin(a3) * outerR);
  }
  shape.closePath();

  const hole = new THREE.Path();
  hole.absarc(0, 0, innerR, 0, Math.PI * 2, true);
  shape.holes.push(hole);

  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: thickness,
    bevelEnabled: true,
    bevelSegments: 3,
    steps: 1,
    bevelSize: 0.035,
    bevelThickness: 0.035,
  });
  geo.center();
  return new THREE.Mesh(geo, mat);
}

/** Soft circular bokeh sprite texture so WebGL Points render as luminous photonic orbs (never hard squares). */
function createGlowSpriteTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 64;
  const ctx = c.getContext("2d");
  if (ctx) {
    const grad = ctx.createRadialGradient(32, 32, 1, 32, 32, 30);
    grad.addColorStop(0.0, "rgba(255,255,255,1.0)");
    grad.addColorStop(0.28, "rgba(255,248,225,0.85)");
    grad.addColorStop(0.65, "rgba(255,220,160,0.22)");
    grad.addColorStop(1.0, "rgba(0,0,0,0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 64, 64);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}

/** Sculpted luminous floating dust / photonic fireflies (NOT black-space stars). */
function buildPhotonicMotes(count: number, radius: number, palette: number[]): THREE.Points {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < count; i++) {
    // Deterministic golden-angle distribution
    const u = ((i * 0.61803398875) % 1) * Math.PI * 2;
    const v = Math.acos(1 - 2 * ((i + 0.5) / count));
    const r = radius * (0.45 + 0.55 * (((i * 2654435761) % 1000) / 1000));
    positions[i * 3] = r * Math.sin(v) * Math.cos(u);
    positions[i * 3 + 1] = r * Math.cos(v) * 0.72;
    positions[i * 3 + 2] = r * Math.sin(v) * Math.sin(u);
    c.setHex(palette[i % palette.length]);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const mat = new THREE.PointsMaterial({
    size: 0.28,
    map: createGlowSpriteTexture(),
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Points(geo, mat);
}

// ---------------------------------------------------------------------------
// 10 Unique Year-3026 Scene Builders
// ---------------------------------------------------------------------------

function buildSceneStage(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
  sceneKind: RadarHeartScene,
  tex: TexturePack
): StageHandle {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    premultipliedAlpha: true,
    powerPreference: "high-performance",
  });
  renderer.setSize(width, height, false);
  renderer.setPixelRatio(1);
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.24;

  const scene = new THREE.Scene();
  scene.background = null; // CRITICAL: Transparent over live 4K Pixabay world!

  // Real physical environment map for chrome, liquid gold, crystal & opal reflections
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envTex;

  const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 140);
  camera.position.set(0, 0.5, 11.4);
  camera.lookAt(0, 0, 0);

  // Studio-cinema 3-point + rim + ambient lighting
  scene.add(new THREE.AmbientLight(0xd8e8ff, 0.85));
  const keyLight = new THREE.DirectionalLight(0xfff4d6, 2.8);
  keyLight.position.set(7, 9, 10);
  scene.add(keyLight);
  const rimCyan = new THREE.PointLight(0x3af0ff, 34, 42, 1.5);
  rimCyan.position.set(-7.5, 3.5, 5.5);
  scene.add(rimCyan);
  const rimGold = new THREE.PointLight(0xffb84d, 34, 42, 1.5);
  rimGold.position.set(7.5, -2.5, 6.0);
  scene.add(rimGold);

  const root = new THREE.Group();
  scene.add(root);

  // Shared noble materials (24K sculpted gold with hammered relief, opalescent crystal, emerald, ruby, sapphire)
  const goldMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0xffd368),
    bumpMap: tex.gold,
    bumpScale: 0.035,
    emissive: new THREE.Color(0x6c3e08),
    emissiveIntensity: 0.52,
    metalness: 0.96,
    roughness: 0.13,
    clearcoat: 1.0,
    envMapIntensity: 2.8,
  });

  const opalGlassMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0x7eeeff),
    emissive: new THREE.Color(0x1678b8),
    emissiveIntensity: 0.58,
    metalness: 0.28,
    roughness: 0.06,
    clearcoat: 1.0,
    iridescence: 1.0,
    iridescenceIOR: 1.6,
    transparent: true,
    opacity: 0.84,
    envMapIntensity: 2.6,
  });

  const emeraldCrystalMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0x1ce69c),
    map: tex.emerald,
    bumpMap: tex.emerald,
    bumpScale: 0.04,
    emissive: new THREE.Color(0x0a6c45),
    emissiveIntensity: 0.75,
    metalness: 0.35,
    roughness: 0.1,
    clearcoat: 1.0,
    iridescence: 0.9,
    envMapIntensity: 2.4,
  });

  const rubyCrystalMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0xff2a5f),
    map: tex.ruby,
    emissive: new THREE.Color(0x8a092a),
    emissiveIntensity: 0.82,
    metalness: 0.42,
    roughness: 0.12,
    clearcoat: 1.0,
    iridescence: 0.7,
    envMapIntensity: 2.4,
  });

  const sapphireTechMat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(0x32c8ff),
    map: tex.sapphire,
    emissive: new THREE.Color(0x0d5898),
    emissiveIntensity: 0.72,
    metalness: 0.65,
    roughness: 0.14,
    clearcoat: 1.0,
    iridescence: 0.85,
    envMapIntensity: 2.4,
  });

  let update: (t: number, progress: number) => void = () => {};

  // =========================================================================
  // SCENE 1 (SDF RAYMARCH HERO): true raymarched ruby heart + chrome shell + gold rings + arteries
  // =========================================================================
  if (sceneKind === "core_birth" && !LEGACY_PRIMITIVE_HERO) {
    const hero = createRaymarchHero(width, height);
    scene.add(hero.mesh);
    const motes = buildPhotonicMotes(160, 11.5, [0xffd86b, 0xff467e, 0x4ef2ff]);
    root.add(motes);
    update = (t, p) => {
      const beatCycle = (t * 1.25) % 1;
      const lub = Math.exp(-Math.pow((beatCycle - 0.12) / 0.055, 2));
      const dub = 0.65 * Math.exp(-Math.pow((beatCycle - 0.29) / 0.065, 2));
      hero.uniforms.uTime.value = t;
      hero.uniforms.uProgress.value = p;
      hero.uniforms.uBeat.value = lub + dub;
      motes.rotation.y = t * 0.09;
    };
  }

  // =========================================================================
  // SCENE 1 (LEGACY PRIMITIVE HERO): kept for A/B comparison, disabled by LEGACY_PRIMITIVE_HERO
  // =========================================================================
  if (sceneKind === "core_birth" && LEGACY_PRIMITIVE_HERO) {
    const heart = buildLivingHeartGroup(tex, 1.08);
    root.add(heart.group);
    const shield = buildTwistedShield(tex, 3.05);
    root.add(shield.group);
    const motes = buildPhotonicMotes(260, 11.5, [0xffd86b, 0xff467e, 0x4ef2ff]);
    root.add(motes);

    // 7 glowing photonic arteries radiating out toward future artifacts
    const arteryMats: THREE.ShaderMaterial[] = [];
    const arteryColors = [0x38e8ff, 0x62f5ff, 0x1ee69a, 0xff3b6b, 0xffa63d, 0xffd66b, 0xc378ff];
    for (let i = 0; i < 7; i++) {
      const ang = (i / 7) * Math.PI * 2 + 0.25;
      const elev = Math.sin(i * 1.9) * 1.25;
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(Math.cos(ang) * 1.35, elev * 0.2, Math.sin(ang) * 1.35),
        new THREE.Vector3(Math.cos(ang + 0.22) * 3.8, elev * 0.75, Math.sin(ang + 0.22) * 3.8),
        new THREE.Vector3(Math.cos(ang + 0.42) * 7.8, elev * 1.1, Math.sin(ang + 0.42) * 7.8),
      ]);
      const aMat = createArteryFlowMaterial(arteryColors[i], 0xfff5d4);
      arteryMats.push(aMat);
      root.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.068, 12, false), aMat));

      // Floating jewel seed at artery endpoint
      const gem = new THREE.Mesh(new THREE.OctahedronGeometry(0.28, 0), goldMat);
      gem.position.copy(curve.getPoint(1));
      root.add(gem);
    }

    update = (t, p) => {
      // Realistic lub-dub double heartbeat
      const beatCycle = (t * 1.25) % 1;
      const lub = Math.exp(-Math.pow((beatCycle - 0.12) / 0.055, 2));
      const dub = 0.65 * Math.exp(-Math.pow((beatCycle - 0.29) / 0.065, 2));
      const pulse = lub + dub;

      heart.group.scale.setScalar(1.08 + pulse * 0.14);
      heart.group.rotation.y = t * 0.48;
      heart.coreMat.emissiveIntensity = 0.75 + pulse * 1.05;
      heart.veins.forEach((m) => (m.uniforms.uTime.value = t * 1.4));

      shield.knot.rotation.set(t * 0.34, t * 0.52, t * 0.18);
      shield.innerKnot.rotation.set(-t * 0.46, -t * 0.32, t * 0.24);
      shield.shellMat.uniforms.uTime.value = t;
      shield.shellMat.uniforms.uPulse.value = pulse;
      shield.rings.forEach((r, idx) => {
        r.rotation.x = idx * 0.72 + t * (0.28 + idx * 0.14);
        r.rotation.y = idx * 1.05 - t * (0.22 + idx * 0.1);
      });
      arteryMats.forEach((m) => (m.uniforms.uTime.value = t));
      motes.rotation.y = t * 0.09;

      // Sweeping hero dolly-orbit
      const camAng = p * 0.65 - 0.25;
      const dist = 12.0 - Math.sin(p * Math.PI) * 1.75;
      camera.position.set(Math.sin(camAng) * dist, 0.75 + Math.sin(t * 0.5) * 0.45, Math.cos(camAng) * dist);
      camera.lookAt(0, 0.1, 0);
    };
  }

  // =========================================================================
  // SCENE 2: emblem_ingest — 6-Petal Crystal Lotus Turbine & 4 Rust WS Rings
  // =========================================================================
  else if (sceneKind === "emblem_ingest") {
    const lotusGroup = new THREE.Group();
    root.add(lotusGroup);

    // Central faceted sapphire-gold 512-tick quantum core
    const core = new THREE.Mesh(new THREE.OctahedronGeometry(1.18, 1), sapphireTechMat);
    lotusGroup.add(core);
    const coreHaloRing = new THREE.Mesh(new THREE.TorusGeometry(1.42, 0.06, 16, 64), goldMat);
    lotusGroup.add(coreHaloRing);
    lotusGroup.add(createVolumetricHalo(2.3, 0x38e8ff, 0.65));

    // 6 sculptural curved crystal-tech petals (6 venues) unfolding like an alien flower
    const petals: THREE.Group[] = [];
    const petalColors = [0x26e5a8, 0xffcb47, 0xff9a3c, 0x38c8ff, 0xc864ff, 0x72ff6b];
    for (let i = 0; i < 6; i++) {
      const pivot = new THREE.Group();
      pivot.rotation.z = (i / 6) * Math.PI * 2;

      const pMat = new THREE.MeshPhysicalMaterial({
        color: petalColors[i],
        map: tex.sapphire,
        emissive: petalColors[i],
        emissiveIntensity: 0.48,
        metalness: 0.65,
        roughness: 0.12,
        clearcoat: 1.0,
        iridescence: 1.0,
        envMapIntensity: 2.5,
      });

      // Petal blade sculpted from tapered Lathe/Cone
      const bladeGeo = new THREE.ConeGeometry(0.72, 3.15, 6);
      bladeGeo.scale(1.0, 1.0, 0.24);
      const blade = new THREE.Mesh(bladeGeo, pMat);
      blade.position.y = 2.45;
      pivot.add(blade);

      // Golden filigree spine on each petal
      const spine = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.09, 2.9, 10), goldMat);
      spine.position.y = 2.3;
      pivot.add(spine);

      // Glowing photonic intake stream from outer edge into the 512-tick core
      const sCurve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, 4.35, 0.35),
        new THREE.Vector3(0.32, 2.5, 0.55),
        new THREE.Vector3(0, 0.95, 0),
      ]);
      const streamMat = createArteryFlowMaterial(petalColors[i], 0xffffff);
      const stream = new THREE.Mesh(new THREE.TubeGeometry(sCurve, 36, 0.055, 8, false), streamMat);
      stream.userData.flowMat = streamMat;
      pivot.add(stream);

      lotusGroup.add(pivot);
      petals.push(pivot);
    }

    // 4 mercury-cyan Rust WebSocket gyroscopic rings
    const wsRings: THREE.Mesh[] = [];
    for (let j = 0; j < 4; j++) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(2.35 + j * 0.58, 0.048, 16, 120),
        j % 2 === 0 ? sapphireTechMat : goldMat
      );
      ring.rotation.set(0.45 * j, 0.65 * j, 0);
      root.add(ring);
      wsRings.push(ring);
    }

    const motes = buildPhotonicMotes(240, 10.5, [0x38e8ff, 0xffd46b, 0xc864ff]);
    root.add(motes);

    update = (t, p) => {
      const bloomOpen = Math.min(1, p * 2.1);
      const ease = 1 - Math.pow(1 - bloomOpen, 3);
      lotusGroup.rotation.z = t * 0.34;
      lotusGroup.rotation.y = Math.sin(t * 0.45) * 0.35;
      core.rotation.set(t * 0.8, t * 0.6, 0);
      core.scale.setScalar(1.0 + Math.sin(t * 5.0) * 0.06);

      petals.forEach((pv, i) => {
        // Petals unfold outward smoothly in 3D space
        const tilt = 0.25 + ease * 0.72 + Math.sin(t * 2.2 + i) * 0.06;
        pv.children[0].rotation.x = tilt;
        pv.children[1].rotation.x = tilt;
        const stream = pv.children[2];
        if (stream?.userData?.flowMat) {
          stream.userData.flowMat.uniforms.uTime.value = t * 1.45 + i * 0.2;
        }
      });

      wsRings.forEach((r, j) => {
        r.rotation.x = j * 0.5 + t * (0.48 + j * 0.16) * (j % 2 === 0 ? 1 : -1);
        r.rotation.y = j * 0.8 + t * (0.36 + j * 0.12);
      });

      motes.rotation.z = -t * 0.22;
      camera.position.set(Math.sin(p * 0.7) * 3.0, 0.85, 11.4 - ease * 1.1);
      camera.lookAt(0, 0, 0);
    };
  }

  // =========================================================================
  // SCENE 3: emblem_mtf_score — 3 Crystal Astrolabe Lenses -> 10 Emerald Jewels
  // =========================================================================
  else if (sceneKind === "emblem_mtf_score") {
    // 3 nested golden-crystal optical lenses aligned horizontally (15m -> 1h -> 4h)
    const lenses: THREE.Group[] = [];
    const lensX = [-3.6, -1.2, 1.2];
    const lensR = [1.85, 1.55, 1.28];
    const lensColors = [0x38e8ff, 0x62a8ff, 0xffd268];

    for (let i = 0; i < 3; i++) {
      const lg = new THREE.Group();
      lg.position.set(lensX[i], 0, 0);

      const gearRim = buildGoldenGear(lensR[i], lensR[i] - 0.22, 24 - i * 4, 0.14, goldMat);
      gearRim.rotation.y = Math.PI / 2;
      lg.add(gearRim);

      const glassMat = createFresnelShieldMaterial(lensColors[i], 0xffffff, 0.58);
      const lensDisc = new THREE.Mesh(new THREE.CylinderGeometry(lensR[i] - 0.24, lensR[i] - 0.24, 0.08, 48), glassMat);
      lensDisc.rotation.z = Math.PI / 2;
      lensDisc.userData.shaderMat = glassMat;
      lg.add(lensDisc);

      root.add(lg);
      lenses.push(lg);
    }

    // Photonic beam piercing all 3 lenses into the emerald Top-10 crown
    const beamMat = createArteryFlowMaterial(0x38e8ff, 0x24ff9e);
    const beamCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-6.2, 0, 0),
      new THREE.Vector3(-1.2, 0, 0),
      new THREE.Vector3(3.6, 0, 0),
    ]);
    root.add(new THREE.Mesh(new THREE.TubeGeometry(beamCurve, 64, 0.11, 16, false), beamMat));

    // 10 faceted Emerald Top-10 crown jewels emerging from the right focal point
    const jewelsGroup = new THREE.Group();
    jewelsGroup.position.set(3.6, 0, 0);
    root.add(jewelsGroup);
    const jewels: THREE.Mesh[] = [];
    for (let k = 0; k < 10; k++) {
      const jewel = new THREE.Mesh(new THREE.OctahedronGeometry(0.42 - k * 0.015, 0), emeraldCrystalMat);
      const ang = (k / 10) * Math.PI * 2;
      jewel.position.set(Math.cos(ang) * 0.2, Math.sin(ang) * 1.9, Math.cos(ang) * 1.9);
      jewelsGroup.add(jewel);
      jewels.push(jewel);
    }
    jewelsGroup.add(createVolumetricHalo(2.2, 0x1ee69a, 0.55));
    const motes = buildPhotonicMotes(220, 10.5, [0x38e8ff, 0x24ff9e, 0xffd268]);
    root.add(motes);

    update = (t, p) => {
      const unfold = Math.min(1, p * 1.9);
      const ease = 1 - Math.pow(1 - unfold, 3);
      beamMat.uniforms.uTime.value = t * 1.6;

      lenses.forEach((lg, i) => {
        lg.children[0].rotation.x = t * (0.55 + i * 0.22) * (i % 2 === 0 ? 1 : -1);
        const sMat = lg.children[1].userData.shaderMat as THREE.ShaderMaterial;
        if (sMat) sMat.uniforms.uTime.value = t + i;
        lg.position.y = Math.sin(t * 1.4 + i) * 0.12;
      });

      jewelsGroup.rotation.x = t * 0.52;
      jewels.forEach((jw, k) => {
        const ang = (k / 10) * Math.PI * 2 + t * 0.4;
        const rad = 0.65 + ease * 1.55;
        jw.position.set(Math.sin(t * 1.5 + k) * 0.35, Math.sin(ang) * rad, Math.cos(ang) * rad);
        jw.rotation.set(t * 1.1 + k, t * 0.9, 0);
        jw.scale.setScalar(0.35 + ease * 0.72);
      });

      motes.rotation.y = t * 0.1;
      camera.position.set(Math.sin(p * 0.8 - 0.3) * 3.8, 1.05, 11.4);
      camera.lookAt(0.4, 0, 0);
    };
  }

  // =========================================================================
  // SCENE 4: emblem_runners — Emerald Crystal Monoliths + Liquid-Glass Trailing Shield
  // =========================================================================
  else if (sceneKind === "emblem_runners") {
    // Sculpted reflective golden-obsidian sanctuary podium rings (open sky above — NO TP ceiling!)
    const baseRing = new THREE.Mesh(new THREE.TorusGeometry(4.4, 0.06, 16, 128), goldMat);
    baseRing.rotation.x = Math.PI / 2;
    baseRing.position.y = -2.4;
    root.add(baseRing);

    const innerBase = new THREE.Mesh(new THREE.CylinderGeometry(4.3, 4.5, 0.12, 48), opalGlassMat);
    innerBase.position.y = -2.46;
    root.add(innerBase);

    // 12 faceted emerald crystal monolith candles ascending toward an open horizon
    const candles: { body: THREE.Mesh; wick: THREE.Mesh; baseH: number; targetY: number }[] = [];
    const heights = [0.75, 1.0, 0.85, 1.35, 1.75, 2.25, 2.05, 2.75, 3.3, 3.85, 4.45, 5.1];
    for (let i = 0; i < 12; i++) {
      const x = -3.85 + i * 0.7;
      const h = heights[i];
      const bodyGeo = new THREE.CylinderGeometry(0.22, 0.26, h, 6);
      const body = new THREE.Mesh(bodyGeo, emeraldCrystalMat);
      body.position.set(x, -2.35 + h / 2, Math.sin(i * 0.55) * 0.55);
      root.add(body);

      const wick = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, h + 0.65, 8), goldMat);
      wick.position.copy(body.position);
      root.add(wick);

      candles.push({ body, wick, baseH: h, targetY: -2.35 + h / 2 });
    }

    // Floating iridescent hexagonal liquid-glass Trailing Shield (-5% Peak) rising underneath
    const shieldGroup = new THREE.Group();
    const hexShieldMat = createFresnelShieldMaterial(0x1ee69a, 0xffd66b, 0.32);
    const hexPlate = new THREE.Mesh(new THREE.CylinderGeometry(4.15, 4.15, 0.08, 6), hexShieldMat);
    shieldGroup.add(hexPlate);
    const hexRim = new THREE.Mesh(new THREE.TorusGeometry(4.18, 0.072, 12, 6), goldMat);
    hexRim.rotation.x = Math.PI / 2;
    shieldGroup.add(hexRim);
    root.add(shieldGroup);

    // Ascending breakout laser trajectory
    const trajPts = heights.map((h, i) => new THREE.Vector3(-3.85 + i * 0.7, -2.1 + h, Math.sin(i * 0.55) * 0.55 + 0.45));
    const trajMat = createArteryFlowMaterial(0x24ff9e, 0xfff2a8);
    root.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(trajPts), 80, 0.075, 12, false), trajMat));

    const motes = buildPhotonicMotes(260, 11.5, [0x24ff9e, 0xffd66b, 0x38e8ff]);
    root.add(motes);

    update = (t, p) => {
      trajMat.uniforms.uTime.value = t * 1.5;
      hexShieldMat.uniforms.uTime.value = t;
      candles.forEach((c, i) => {
        // Start tall enough from second 1 so emerald monoliths shine above the trailing shield immediately
        const appear = Math.max(0.42, Math.min(1, 0.42 + p * 1.35 - i * 0.04));
        const ease = 1 - Math.pow(1 - appear, 2);
        c.body.scale.y = ease;
        c.body.position.y = -2.35 + (c.baseH * ease) / 2;
        c.body.rotation.y = t * 0.55 + i * 0.4;
        c.wick.scale.y = ease;
        c.wick.position.y = c.body.position.y;
      });
      // Trailing shield glides upward smoothly protecting the runner without covering peaks
      const trailY = -2.1 + Math.min(1, p * 1.05) * 2.15;
      shieldGroup.position.y = trailY;
      shieldGroup.rotation.y = t * 0.35;

      motes.position.y = (t * 0.55) % 4 - 2;
      camera.position.set(Math.sin(p * 0.65 - 0.3) * 3.4, 1.15 + p * 0.85, 11.2);
      camera.lookAt(0.2, 0.35, 0);
    };
  }

  // =========================================================================
  // SCENE 5: emblem_stop_cut — Ruby Horizon Blade (-3% Mark) + Golden Seal (Ban 3h)
  // =========================================================================
  else if (sceneKind === "emblem_stop_cut") {
    // Razor-thin glowing crimson-gold plasma horizon blade (-3.0% Mark)
    const bladeMat = createFresnelShieldMaterial(0xff1e52, 0xffc45c, 0.78);
    const bladeDisc = new THREE.Mesh(new THREE.CylinderGeometry(4.8, 4.8, 0.05, 64), bladeMat);
    root.add(bladeDisc);
    const bladeRim = new THREE.Mesh(new THREE.TorusGeometry(4.82, 0.055, 16, 128), rubyCrystalMat);
    bladeRim.rotation.x = Math.PI / 2;
    root.add(bladeRim);

    // Falling ruby crystal monoliths cleanly sheared at the blade plane
    const fallingCrystals: { top: THREE.Mesh; shards: THREE.Mesh[]; x: number }[] = [];
    for (let i = 0; i < 7; i++) {
      const x = -2.7 + i * 0.9;
      const top = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.28, 2.2, 6), rubyCrystalMat);
      top.position.set(x, 1.35, Math.sin(i * 1.1) * 0.5);
      root.add(top);

      const shards: THREE.Mesh[] = [];
      for (let s = 0; s < 5; s++) {
        const sh = new THREE.Mesh(new THREE.OctahedronGeometry(0.18 + (s % 2) * 0.08, 0), rubyCrystalMat);
        sh.position.set(x, -0.35, 0);
        root.add(sh);
        shards.push(sh);
      }
      fallingCrystals.push({ top, shards, x });
    }

    // Ornate Golden Holographic Seal-Lock (Re-entry Ban 3h) assembling in front
    const sealGroup = new THREE.Group();
    sealGroup.position.set(0, -0.45, 2.35);
    const outerSeal = buildGoldenGear(1.65, 1.36, 20, 0.14, goldMat);
    const innerSeal = buildGoldenGear(1.18, 0.88, 12, 0.14, goldMat);
    const lockCrystal = new THREE.Mesh(new THREE.OctahedronGeometry(0.58, 0), rubyCrystalMat);
    sealGroup.add(outerSeal, innerSeal, lockCrystal);
    sealGroup.add(createVolumetricHalo(1.9, 0xffb84d, 0.58));
    root.add(sealGroup);

    const motes = buildPhotonicMotes(220, 10.5, [0xff2a5f, 0xffcf6a, 0xffffff]);
    root.add(motes);

    update = (t, p) => {
      bladeMat.uniforms.uTime.value = t * 1.8;
      bladeRim.rotation.z = t * 0.45;
      const cutPhase = Math.min(1, p * 1.6);

      fallingCrystals.forEach((fc, i) => {
        fc.top.rotation.y = t * 0.6 + i;
        fc.top.position.y = 1.4 - cutPhase * 0.4 + Math.sin(t * 2 + i) * 0.08;
        fc.shards.forEach((sh, s) => {
          const drift = Math.max(0, p * 1.4 - 0.12);
          const ang = (s / 5) * Math.PI * 2 + i;
          sh.position.set(
            fc.x + Math.cos(ang) * drift * 1.65,
            -0.25 - drift * (1.2 + s * 0.42),
            Math.sin(ang) * drift * 1.5
          );
          sh.rotation.set(t * 2.2 + s, t * 1.8 + i, s);
          sh.scale.setScalar(Math.max(0.05, 1.0 - drift * 0.55));
        });
      });

      const sealReveal = Math.max(0, Math.min(1, (p - 0.22) * 2.2));
      const ease = 1 - Math.pow(1 - sealReveal, 3);
      sealGroup.scale.setScalar(0.01 + ease * 1.0);
      outerSeal.rotation.z = t * 0.65;
      innerSeal.rotation.z = -t * 0.95;
      lockCrystal.rotation.y = t * 1.4;

      camera.position.set(Math.sin(p * 0.75 - 0.35) * 3.2, 1.1, 11.2);
      camera.lookAt(0, -0.1, 0);
    };
  }

  // =========================================================================
  // SCENE 6: emblem_traps — Iridescent Bastion Dome vs 6 Sculpted Anomalies
  // (includes fiery FUTURES_BLOCK transforming into a calm blue Watch-Lens!)
  // =========================================================================
  else if (sceneKind === "emblem_traps") {
    const domeMat = createFresnelShieldMaterial(0x38e8ff, 0xffb84d, 0.62);
    const dome = new THREE.Mesh(new THREE.IcosahedronGeometry(2.65, 3), domeMat);
    root.add(dome);
    const domeCage = new THREE.Mesh(new THREE.IcosahedronGeometry(2.72, 2), new THREE.MeshBasicMaterial({
      color: 0x70f8ff,
      wireframe: true,
      transparent: true,
      opacity: 0.28,
    }));
    root.add(domeCage);
    const innerCore = new THREE.Mesh(new THREE.OctahedronGeometry(0.95, 1), goldMat);
    root.add(innerCore);
    root.add(createVolumetricHalo(3.1, 0x38e8ff, 0.52));

    // 6 distinct sculptural market-trap anomalies orbiting & rebounding off the bastion
    const traps: { mesh: THREE.Object3D; baseAngle: number; isFutures: boolean; mat?: THREE.MeshPhysicalMaterial }[] = [];

    // 1. Anti-Chase fiery spear
    const spear = new THREE.Mesh(new THREE.ConeGeometry(0.38, 1.85, 6), rubyCrystalMat);
    spear.rotation.z = Math.PI / 2;
    root.add(spear);
    traps.push({ mesh: spear, baseAngle: 0, isFutures: false });

    // 2. FUTURES_BLOCK linked torus -> transforms into calm sapphire watch-lens!
    const futMat = new THREE.MeshPhysicalMaterial({
      color: new THREE.Color(0xff4228),
      emissive: new THREE.Color(0xaa1800),
      emissiveIntensity: 0.9,
      metalness: 0.72,
      roughness: 0.14,
      clearcoat: 1.0,
    });
    const futGroup = new THREE.Group();
    const futTorusA = new THREE.Mesh(new THREE.TorusGeometry(0.56, 0.14, 16, 48), futMat);
    const futTorusB = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.08, 12, 36), futMat);
    futTorusB.rotation.x = Math.PI / 2;
    futGroup.add(futTorusA, futTorusB);
    root.add(futGroup);
    traps.push({ mesh: futGroup, baseAngle: Math.PI / 3, isFutures: true, mat: futMat });

    // 3. Ghost listing hollow rings
    const ghost = new THREE.Mesh(new THREE.TorusKnotGeometry(0.42, 0.08, 64, 12, 2, 3), opalGlassMat);
    root.add(ghost);
    traps.push({ mesh: ghost, baseAngle: (2 * Math.PI) / 3, isFutures: false });

    // 4. Degraded snapshot cracked dodecahedron
    const degraded = new THREE.Mesh(new THREE.DodecahedronGeometry(0.55, 0), rubyCrystalMat);
    root.add(degraded);
    traps.push({ mesh: degraded, baseAngle: Math.PI, isFutures: false });

    // 5. Losing streak golden hourglass
    const hourglass = new THREE.Group();
    const hgTop = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.65, 16), goldMat);
    hgTop.position.y = 0.34;
    hgTop.rotation.x = Math.PI;
    const hgBot = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.65, 16), goldMat);
    hgBot.position.y = -0.34;
    hourglass.add(hgTop, hgBot);
    root.add(hourglass);
    traps.push({ mesh: hourglass, baseAngle: (4 * Math.PI) / 3, isFutures: false });

    // 6. Emergency Kill-Switch ruby octahedron crystal
    const killGem = new THREE.Mesh(new THREE.OctahedronGeometry(0.58, 0), rubyCrystalMat);
    root.add(killGem);
    traps.push({ mesh: killGem, baseAngle: (5 * Math.PI) / 3, isFutures: false });

    const motes = buildPhotonicMotes(240, 11, [0x38e8ff, 0xff467e, 0xffd66b]);
    root.add(motes);

    update = (t, p) => {
      const impactWave = 0.5 + 0.5 * Math.sin(t * 4.2);
      domeMat.uniforms.uTime.value = t * 1.4;
      domeMat.uniforms.uPulse.value = impactWave;
      dome.rotation.y = t * 0.25;
      domeCage.rotation.set(t * 0.18, -t * 0.22, 0);
      innerCore.rotation.set(t * 0.9, t * 0.7, 0);

      traps.forEach((tr, idx) => {
        const ang = tr.baseAngle + t * 0.36;
        // Approach shield, bounce cleanly outside radius 3.3..5.4
        const bounce = Math.abs(Math.sin(t * 1.35 + idx * 1.05));
        const r = 3.25 + bounce * 2.15;
        tr.mesh.position.set(Math.cos(ang) * r, Math.sin(t * 1.2 + idx) * 1.1, Math.sin(ang) * r);
        tr.mesh.rotation.set(t * 1.1 + idx, t * 0.9, 0);
        if (tr.isFutures && tr.mat) {
          // Smoothly cool from fiery orange-red to calm sapphire watch-only lens
          const cool = Math.min(1, Math.max(0, (p - 0.32) * 2.2));
          tr.mat.color.setHex(0xff4228).lerp(new THREE.Color(0x38d8ff), cool);
          tr.mat.emissive.setHex(0xaa1800).lerp(new THREE.Color(0x0c6aa8), cool);
        }
      });

      camera.position.set(Math.sin(p * 0.75) * 3.5, 1.35, 11.4);
      camera.lookAt(0, 0, 0);
    };
  }

  // =========================================================================
  // SCENE 7: emblem_integer — Haute-Horology Golden Astrolabe (i64/i128) + 3 Equal Chalices
  // =========================================================================
  else if (sceneKind === "emblem_integer") {
    const astrolabe = new THREE.Group();
    astrolabe.position.set(0, 1.15, 0);
    root.add(astrolabe);

    const g1 = buildGoldenGear(2.15, 1.55, 28, 0.22, goldMat);
    const g2 = buildGoldenGear(1.42, 0.92, 18, 0.22, goldMat);
    g2.position.set(0, 0, 0.26);
    const g3 = buildGoldenGear(0.82, 0.38, 12, 0.26, sapphireTechMat);
    g3.position.set(0, 0, -0.26);
    const axisRing = new THREE.Mesh(new THREE.TorusGeometry(2.55, 0.055, 16, 128), goldMat);
    axisRing.rotation.x = Math.PI / 3;
    astrolabe.add(g1, g2, g3, axisRing);
    astrolabe.add(createVolumetricHalo(2.4, 0xffd268, 0.52));

    // 3 Crystal Chalices (Equal Sleeves: spot_alts, memes, listings) filled evenly by 3 streams
    const chaliceX = [-3.35, 0, 3.35];
    const streamColors = [0x1ee69a, 0x38d8ff, 0xffcf6a];
    const fills: THREE.Mesh[] = [];
    const streamMats: THREE.ShaderMaterial[] = [];

    for (let i = 0; i < 3; i++) {
      const cx = chaliceX[i];
      // Outer sculpted crystal chalice shell
      const cup = new THREE.Mesh(
        new THREE.CylinderGeometry(0.92, 0.62, 1.95, 24, 1, true),
        opalGlassMat
      );
      cup.position.set(cx, -1.95, 0.4);
      root.add(cup);

      const cupRim = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.05, 12, 48), goldMat);
      cupRim.rotation.x = Math.PI / 2;
      cupRim.position.set(cx, -0.98, 0.4);
      root.add(cupRim);

      const cupBase = new THREE.Mesh(new THREE.CylinderGeometry(0.68, 0.78, 0.16, 24), goldMat);
      cupBase.position.set(cx, -2.95, 0.4);
      root.add(cupBase);

      // Luminous liquid-light fill inside each chalice (rising identically!)
      const fMat = new THREE.MeshPhysicalMaterial({
        color: streamColors[i],
        emissive: streamColors[i],
        emissiveIntensity: 0.85,
        roughness: 0.08,
        metalness: 0.2,
        clearcoat: 1.0,
        transparent: true,
        opacity: 0.88,
      });
      const fill = new THREE.Mesh(new THREE.CylinderGeometry(0.82, 0.56, 1.65, 24), fMat);
      fill.position.set(cx, -2.85, 0.4);
      root.add(fill);
      fills.push(fill);

      // Flowing photonic stream from the Golden Astrolabe into each chalice
      const sCurve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(cx * 0.18, 0.55, 0.1),
        new THREE.Vector3(cx * 0.68, -0.15, 0.35),
        new THREE.Vector3(cx, -1.15, 0.4),
      ]);
      const sMat = createArteryFlowMaterial(streamColors[i], 0xfff8dc);
      streamMats.push(sMat);
      root.add(new THREE.Mesh(new THREE.TubeGeometry(sCurve, 44, 0.072, 10, false), sMat));
    }

    const motes = buildPhotonicMotes(240, 11, [0xffd268, 0x1ee69a, 0x38d8ff]);
    root.add(motes);

    update = (t, p) => {
      g1.rotation.z = t * 0.48;
      g2.rotation.z = -t * 0.82;
      g3.rotation.z = t * 1.25;
      axisRing.rotation.y = t * 0.55;
      astrolabe.rotation.y = Math.sin(t * 0.4) * 0.28;

      const fillLvl = Math.min(1, 0.15 + p * 0.88);
      fills.forEach((f) => {
        f.scale.y = fillLvl;
        f.position.y = -2.85 + (1.65 * fillLvl) / 2;
      });
      streamMats.forEach((m) => (m.uniforms.uTime.value = t * 1.45));

      camera.position.set(Math.sin(p * 0.7 - 0.35) * 3.0, 0.45, 11.6);
      camera.lookAt(0, -0.4, 0);
    };
  }

  // =========================================================================
  // SCENE 8: emblem_recovery — Opalescent Neural Phoenix & 3 Floating Holo-Mirrors
  // =========================================================================
  else if (sceneKind === "emblem_recovery") {
    const phoenix = new THREE.Group();
    root.add(phoenix);

    const core = new THREE.Mesh(new THREE.OctahedronGeometry(1.12, 1), sapphireTechMat);
    phoenix.add(core);
    const coreRing = new THREE.Mesh(new THREE.TorusGeometry(1.48, 0.055, 16, 64), goldMat);
    coreRing.rotation.x = Math.PI / 3;
    phoenix.add(coreRing);
    phoenix.add(createVolumetricHalo(2.45, 0x9b6dff, 0.68));

    // 18 glowing neural wing-filaments (self-healing pulses!)
    const wingMats: THREE.ShaderMaterial[] = [];
    for (let i = 0; i < 18; i++) {
      const side = i < 9 ? -1 : 1;
      const idx = i % 9;
      const spreadY = (idx - 4) * 0.42;
      const reach = 3.2 + (4 - Math.abs(idx - 4)) * 0.68;
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(side * 0.65, spreadY * 0.25, 0),
        new THREE.Vector3(side * reach * 0.55, spreadY * 0.85 + 0.55, Math.sin(idx) * 0.75),
        new THREE.Vector3(side * reach, spreadY * 1.15 + 0.9, Math.cos(idx) * 0.85),
      ]);
      const wMat = createArteryFlowMaterial(0x7c5cff, 0x4ef2ff);
      wingMats.push(wMat);
      phoenix.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 36, 0.052, 8, false), wMat));
    }

    // 3 precision-framed floating glass holo-mirrors (Dashboard, PWA, Telegram)
    const mirrors: THREE.Group[] = [];
    const mirrorColors = [0x38e8ff, 0x24ff9e, 0xffcf6a];
    for (let m = 0; m < 3; m++) {
      const mg = new THREE.Group();
      const glassMat = createFresnelShieldMaterial(mirrorColors[m], 0xffffff, 0.58);
      const screen = new THREE.Mesh(new THREE.BoxGeometry(2.1, 1.32, 0.06), glassMat);
      // Exact rectangular golden bezel around the glass mirror (4 precision rails)
      const topBar = new THREE.Mesh(new THREE.BoxGeometry(2.18, 0.055, 0.09), goldMat);
      topBar.position.y = 0.68;
      const botBar = new THREE.Mesh(new THREE.BoxGeometry(2.18, 0.055, 0.09), goldMat);
      botBar.position.y = -0.68;
      const leftBar = new THREE.Mesh(new THREE.BoxGeometry(0.055, 1.38, 0.09), goldMat);
      leftBar.position.x = -1.07;
      const rightBar = new THREE.Mesh(new THREE.BoxGeometry(0.055, 1.38, 0.09), goldMat);
      rightBar.position.x = 1.07;
      mg.add(screen, topBar, botBar, leftBar, rightBar);
      mg.userData.shaderMat = glassMat;
      root.add(mg);
      mirrors.push(mg);
    }

    const motes = buildPhotonicMotes(260, 11, [0x4ef2ff, 0x9b6dff, 0xffd268]);
    root.add(motes);

    update = (t, p) => {
      phoenix.rotation.y = Math.sin(t * 0.45) * 0.35;
      core.rotation.set(t * 0.7, t * 0.9, 0);
      // Self-heal brightening wave after brief dip
      const healWave = p < 0.28 ? 0.45 + 0.55 * Math.cos(p * 11) : 1.0;
      wingMats.forEach((m, idx) => {
        m.uniforms.uTime.value = t * (1.1 + (idx % 3) * 0.25);
        m.uniforms.uPulse.value.setHex(healWave > 0.7 ? 0xffe484 : 0xff3b6b);
      });

      mirrors.forEach((mg, m) => {
        const ang = (m / 3) * Math.PI * 2 + t * 0.32;
        mg.position.set(Math.cos(ang) * 4.55, Math.sin(t * 1.1 + m * 2) * 0.65 - 0.35, Math.sin(ang) * 3.4);
        mg.lookAt(0, 0, 12);
        const sMat = mg.userData.shaderMat as THREE.ShaderMaterial;
        if (sMat) sMat.uniforms.uTime.value = t + m;
      });

      camera.position.set(Math.sin(p * 0.7) * 2.8, 0.95, 11.8);
      camera.lookAt(0, 0, 0);
    };
  }

  // =========================================================================
  // SCENE 9: constellation_radar — Full Sanctum Fly-Out: Heart + 7 Arteries + 7 Sculpted Artifacts
  // =========================================================================
  else if (sceneKind === "constellation_radar") {
    const heart = buildLivingHeartGroup(tex, 0.86);
    root.add(heart.group);
    const shield = buildTwistedShield(tex, 2.35);
    root.add(shield.group);

    const nodeColors = [0x38e8ff, 0x62a8ff, 0x1ee69a, 0xff3b6b, 0xffa63d, 0xffd268, 0xb278ff];
    const arteryMats: THREE.ShaderMaterial[] = [];
    const nodes: THREE.Mesh[] = [];
    const nodeGeos = [
      new THREE.ConeGeometry(0.48, 1.05, 6),
      new THREE.TorusGeometry(0.48, 0.14, 16, 48),
      new THREE.OctahedronGeometry(0.58, 0),
      new THREE.TorusKnotGeometry(0.36, 0.11, 72, 14, 2, 5),
      new THREE.IcosahedronGeometry(0.52, 1),
      new THREE.DodecahedronGeometry(0.54, 0),
      new THREE.TorusKnotGeometry(0.4, 0.1, 64, 12, 2, 3),
    ];

    for (let i = 0; i < 7; i++) {
      const ang = (i / 7) * Math.PI * 2;
      const rad = 5.45;
      const ny = Math.sin(i * 1.7) * 1.35 + 0.35;
      const target = new THREE.Vector3(Math.cos(ang) * rad, ny, Math.sin(ang) * rad * 0.72);

      const nMat = new THREE.MeshPhysicalMaterial({
        color: nodeColors[i],
        emissive: nodeColors[i],
        emissiveIntensity: 0.65,
        metalness: 0.78,
        roughness: 0.14,
        clearcoat: 1.0,
        iridescence: 0.9,
        envMapIntensity: 2.5,
      });
      const node = new THREE.Mesh(nodeGeos[i], nMat);
      node.position.copy(target);
      root.add(node);
      nodes.push(node);

      // Orbiting golden halo ring around each satellite artifact
      const satRing = new THREE.Mesh(new THREE.TorusGeometry(0.76, 0.028, 10, 48), goldMat);
      satRing.position.copy(target);
      satRing.rotation.set(i * 0.6, i * 0.8, 0);
      root.add(satRing);

      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(Math.cos(ang) * 1.0, ny * 0.15, Math.sin(ang) * 1.0),
        new THREE.Vector3(Math.cos(ang + 0.25) * 3.1, ny * 0.65 + 0.4, Math.sin(ang + 0.25) * 2.4),
        target,
      ]);
      const aMat = createArteryFlowMaterial(nodeColors[i], 0xfff5d4);
      arteryMats.push(aMat);
      root.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 56, 0.062, 10, false), aMat));
    }

    const motes = buildPhotonicMotes(300, 13.5, [0xffd268, 0x38e8ff, 0xff467e, 0x1ee69a]);
    root.add(motes);

    update = (t, p) => {
      const beatCycle = (t * 1.2) % 1;
      const pulse = Math.exp(-Math.pow((beatCycle - 0.14) / 0.06, 2)) + 0.6 * Math.exp(-Math.pow((beatCycle - 0.31) / 0.07, 2));
      heart.group.scale.setScalar(0.86 + pulse * 0.11);
      heart.group.rotation.y = t * 0.45;
      heart.veins.forEach((m) => (m.uniforms.uTime.value = t * 1.3));
      shield.knot.rotation.set(t * 0.32, t * 0.48, t * 0.15);
      shield.innerKnot.rotation.set(-t * 0.4, -t * 0.28, t * 0.2);
      shield.shellMat.uniforms.uTime.value = t;
      shield.shellMat.uniforms.uPulse.value = pulse;
      arteryMats.forEach((m) => (m.uniforms.uTime.value = t * 1.25));
      nodes.forEach((n, i) => {
        n.rotation.set(t * 0.8 + i, t * 1.0, 0);
      });
      root.rotation.y = t * 0.16;

      // Grand ascending pull-back so all 7 artifacts + Heart shine above the repo glass card
      const dist = 10.6 + p * 3.2;
      camera.position.set(Math.sin(p * 0.6 - 0.2) * 3.2, 1.35 + p * 0.9, dist);
      camera.lookAt(0, -0.35, 0);
    };
  }

  // =========================================================================
  // SCENE 10: presenter_core — DUP PRESENTER 3026 Photonic Cinema Reactor
  // =========================================================================
  else if (sceneKind === "presenter_core") {
    const reactor = new THREE.Group();
    reactor.position.y = 0.55;
    root.add(reactor);

    // Golden Optical Cinema Lens TorusKnot Core
    const lensKnot = new THREE.Mesh(
      new THREE.TorusKnotGeometry(1.75, 0.26, 220, 28, 2, 5),
      goldMat
    );
    reactor.add(lensKnot);

    // Iridescent inner diamond projection core
    const prismCore = new THREE.Mesh(new THREE.OctahedronGeometry(0.95, 1), opalGlassMat);
    reactor.add(prismCore);
    reactor.add(createVolumetricHalo(2.9, 0xffcf6a, 0.65));

    // Futuristic Mobius Cinema Film-Ribbon orbiting the reactor
    const ribbonMat = createFresnelShieldMaterial(0x38e8ff, 0xff5a8a, 0.72);
    const filmRibbon = new THREE.Mesh(new THREE.TorusGeometry(3.25, 0.24, 18, 128), ribbonMat);
    filmRibbon.scale.set(1.15, 0.85, 0.35);
    reactor.add(filmRibbon);

    const outerGoldHalo = buildGoldenGear(3.85, 3.55, 36, 0.09, goldMat);
    reactor.add(outerGoldHalo);

    // 48 Crystal Audio Equalizer Resonators orbiting in a glowing ring
    const eqBars: THREE.Mesh[] = [];
    const eqColors = [0xffcf6a, 0x38e8ff, 0xff467e, 0x1ee69a];
    for (let i = 0; i < 48; i++) {
      const ang = (i / 48) * Math.PI * 2;
      const barMat = new THREE.MeshPhysicalMaterial({
        color: eqColors[i % eqColors.length],
        emissive: eqColors[i % eqColors.length],
        emissiveIntensity: 0.78,
        metalness: 0.6,
        roughness: 0.12,
        clearcoat: 1.0,
      });
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.75, 0.11), barMat);
      bar.position.set(Math.cos(ang) * 4.45, Math.sin(ang) * 4.45, 0);
      bar.rotation.z = ang - Math.PI / 2;
      reactor.add(bar);
      eqBars.push(bar);
    }

    const motes = buildPhotonicMotes(280, 12.5, [0xffcf6a, 0x38e8ff, 0xff467e, 0x24ff9e]);
    root.add(motes);

    update = (t, p) => {
      lensKnot.rotation.set(t * 0.42, t * 0.62, t * 0.18);
      prismCore.rotation.set(-t * 0.9, t * 1.1, 0);
      ribbonMat.uniforms.uTime.value = t * 1.6;
      filmRibbon.rotation.set(0.55 + Math.sin(t * 0.6) * 0.25, t * 0.48, 0.3);
      outerGoldHalo.rotation.z = -t * 0.28;
      outerGoldHalo.rotation.x = Math.sin(t * 0.4) * 0.22;

      eqBars.forEach((bar, i) => {
        const wave = 0.45 + 1.35 * Math.pow(0.5 + 0.5 * Math.sin(t * 5.2 + i * 0.52), 2);
        bar.scale.y = wave;
      });
      motes.rotation.z = t * 0.12;

      camera.position.set(Math.sin(p * 0.7 - 0.35) * 3.0, 0.45, 11.8 - p * 0.8);
      camera.lookAt(0, -0.1, 0);
    };
  }

  return {
    renderer,
    scene,
    camera,
    pmrem,
    envTex,
    update,
    dispose: () => {
      scene.traverse((obj) => {
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
        const mat = (obj as THREE.Mesh).material;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else if (mat) mat.dispose();
      });
      envTex.dispose();
      pmrem.dispose();
      renderer.dispose();
    },
  };
}

// ---------------------------------------------------------------------------
// React Component (4K World Video + Transparent WebGL2 3026 Artifact + Liquid-Glass HUD)
// ---------------------------------------------------------------------------

export const RadarHeart3DSlide: React.FC<{
  slide: ResolvedSlide;
  dur?: number;
  theme?: unknown;
  isPortrait?: boolean;
}> = ({ slide, dur }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const data: RadarHeartData = slide.heart3d ?? { scene: "core_birth" };

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stageRef = useRef<StageHandle | null>(null);

  const durationFrames = Math.max(1, dur ?? Math.round((slide.duration_sec || 16) * fps));
  const progress = Math.min(1, Math.max(0, frame / durationFrames));
  const timeSec = frame / fps;

  // Initialize Three.js transparent WebGL2 stage + Pixabay PBR textures via delayRender
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handle = delayRender(`radar-heart-3026-${slide.id}`);
    let cancelled = false;

    const loader = new THREE.TextureLoader();
    const loadTex = (relPath: string): Promise<THREE.Texture | null> =>
      new Promise((resolve) => {
        loader.load(
          staticFile(relPath),
          (t) => {
            t.wrapS = THREE.RepeatWrapping;
            t.wrapT = THREE.RepeatWrapping;
            t.colorSpace = THREE.SRGBColorSpace;
            resolve(t);
          },
          undefined,
          () => resolve(null)
        );
      });

    Promise.all([
      loadTex(TEX_PATHS.ruby),
      loadTex(TEX_PATHS.gold),
      loadTex(TEX_PATHS.emerald),
      loadTex(TEX_PATHS.sapphire),
    ]).then(([ruby, gold, emerald, sapphire]) => {
      if (cancelled) {
        [ruby, gold, emerald, sapphire].forEach((t) => t?.dispose());
        continueRender(handle);
        return;
      }
      const stage = buildSceneStage(canvas, width, height, data.scene, {
        ruby,
        gold,
        emerald,
        sapphire,
      });
      stageRef.current = stage;
      stage.update(timeSec, progress);
      stage.renderer.render(stage.scene, stage.camera);
      continueRender(handle);
    });

    return () => {
      cancelled = true;
      if (stageRef.current) {
        stageRef.current.dispose();
        stageRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.scene, width, height, slide.id]);

  // Deterministic per-frame 3D render
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.update(timeSec, progress);
    stage.renderer.render(stage.scene, stage.camera);
  }, [timeSec, progress]);

  // Subtle Ken Burns breathing on the 4K futuristic world background
  const bgScale = interpolate(progress, [0, 1], [1.04, 1.12], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const hudIn = interpolate(frame, [6, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const hudShift = interpolate(frame, [6, 26], [18, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const bgOpacity = data.bg_opacity ?? 0.78;
  const accentHex = useMemo(() => {
    switch (data.scene) {
      case "core_birth":
        return "#ffd268";
      case "emblem_ingest":
        return "#38e8ff";
      case "emblem_mtf_score":
        return "#62c8ff";
      case "emblem_runners":
        return "#24ff9e";
      case "emblem_stop_cut":
        return "#ff3b6b";
      case "emblem_traps":
        return "#ffae42";
      case "emblem_integer":
        return "#ffd66b";
      case "emblem_recovery":
        return "#b278ff";
      case "constellation_radar":
        return "#38e8ff";
      case "presenter_core":
        return "#ffd66b";
    }
  }, [data.scene]);

  const isFinaleCard = data.scene === "constellation_radar" || data.scene === "presenter_core";

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 50% 45%, #162040 0%, #0a1026 55%, #050816 100%)",
        overflow: "hidden",
        fontFamily:
          "'Inter', 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* LAYER 1: Live 4K/HD Futuristic World (NO flat black outer space) */}
      {data.bg_video ? (
        <AbsoluteFill
          style={{
            transform: `scale(${bgScale})`,
            opacity: bgOpacity,
            filter: "saturate(1.22) contrast(1.08) brightness(0.92)",
          }}
        >
          <OffthreadVideo
            src={staticFile(data.bg_video)}
            muted
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        </AbsoluteFill>
      ) : null}

      {/* Atmospheric photonic tint & cinematic focus vignette (keeps 3D crystal-clear) */}
      <AbsoluteFill
        style={{
          background: data.bg_tint
            ? `radial-gradient(circle at 50% 48%, rgba(8,14,32,0.14) 0%, ${data.bg_tint} 65%, rgba(4,8,20,0.72) 100%)`
            : "radial-gradient(circle at 50% 48%, rgba(8,14,32,0.12) 0%, rgba(6,10,26,0.48) 70%, rgba(4,7,18,0.78) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* LAYER 2: Transparent WebGL2 Three.js 3026 Sculptural Artifact */}
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
        }}
      />

      {/* LAYER 3: Minimal Liquid-Glass Future HUD (zero overlap with bottom karaoke captions) */}
      <AbsoluteFill
        style={{
          padding: isFinaleCard ? "34px 52px 124px 52px" : "34px 52px 118px 52px",
          justifyContent: "space-between",
          pointerEvents: "none",
          opacity: hudIn,
          transform: `translateY(${hudShift}px)`,
        }}
      >
        {/* Top Visor Row (Badge + Headline + Telemetry Chips cleanly grouped at top) */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 24,
          }}
        >
          <div style={{ maxWidth: 960 }}>
            {data.emblem_label ? (
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "6px 15px",
                  borderRadius: 999,
                  background: "rgba(6, 12, 28, 0.58)",
                  border: `1px solid ${accentHex}88`,
                  backdropFilter: "blur(12px)",
                  color: accentHex,
                  fontSize: 15,
                  fontWeight: 700,
                  letterSpacing: 1.7,
                  textTransform: "uppercase",
                  boxShadow: `0 0 24px ${accentHex}33`,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: accentHex,
                    boxShadow: `0 0 12px ${accentHex}`,
                  }}
                />
                {data.emblem_label}
              </div>
            ) : null}

            {data.headline ? (
              <div
                style={{
                  marginTop: 10,
                  color: "#f8fbff",
                  fontSize: isFinaleCard ? 42 : 38,
                  fontWeight: 800,
                  lineHeight: 1.12,
                  letterSpacing: -0.6,
                  textShadow:
                    "0 4px 26px rgba(0, 0, 0, 0.88), 0 0 36px rgba(56, 232, 255, 0.22)",
                }}
              >
                {data.headline}
              </div>
            ) : null}

            {data.chips && data.chips.length > 0 ? (
              <div
                style={{
                  marginTop: 12,
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                }}
              >
                {data.chips.map((chip, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "6px 13px",
                      borderRadius: 10,
                      background: "rgba(6, 12, 28, 0.62)",
                      border: `1px solid ${accentHex}55`,
                      backdropFilter: "blur(12px)",
                      color: "#eef6ff",
                      fontSize: 14,
                      fontWeight: 600,
                      letterSpacing: 0.25,
                      boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                    }}
                  >
                    {chip}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {/* Right telemetry capsule */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              gap: 8,
              flexShrink: 0,
            }}
          >
            <div
              style={{
                padding: "7px 15px",
                borderRadius: 999,
                background: "rgba(6, 12, 28, 0.58)",
                border: "1px solid rgba(255, 255, 255, 0.18)",
                backdropFilter: "blur(10px)",
                color: "rgba(240, 248, 255, 0.92)",
                fontSize: 14,
                fontWeight: 700,
                letterSpacing: 1.4,
              }}
            >
              {slide.num} · {slide.tag}
            </div>
            {data.world_title ? (
              <div
                style={{
                  color: "rgba(255, 230, 170, 0.88)",
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: 1.1,
                  textTransform: "uppercase",
                  textShadow: "0 2px 12px rgba(0,0,0,0.95)",
                }}
              >
                {data.world_title}
              </div>
            ) : null}
          </div>
        </div>

        {/* Bottom Visor Row (Only Finale Repo Crystal Plate + Honest Disclaimer, cleanly above captions) */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
          }}
        >
          {data.repo_url ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 6,
                padding: "14px 32px",
                borderRadius: 20,
                background:
                  "linear-gradient(135deg, rgba(8, 16, 38, 0.84) 0%, rgba(18, 24, 52, 0.78) 100%)",
                border: `1.5px solid ${accentHex}bb`,
                backdropFilter: "blur(16px)",
                boxShadow: `0 12px 48px rgba(0,0,0,0.6), 0 0 38px ${accentHex}38`,
                textAlign: "center",
              }}
            >
              {data.repo_caption ? (
                <div
                  style={{
                    color: accentHex,
                    fontSize: 15,
                    fontWeight: 800,
                    letterSpacing: 1.5,
                    textTransform: "uppercase",
                  }}
                >
                  {data.repo_caption}
                </div>
              ) : null}
              <div
                style={{
                  color: "#ffffff",
                  fontSize: 28,
                  fontWeight: 800,
                  letterSpacing: 0.4,
                  fontFamily: "'JetBrains Mono', 'Cascadia Code', monospace",
                  textShadow: `0 0 22px ${accentHex}66`,
                }}
              >
                {data.repo_url}
              </div>
            </div>
          ) : null}

          {data.disclaimer ? (
            <div
              style={{
                padding: "4px 14px",
                borderRadius: 999,
                background: "rgba(4, 8, 20, 0.62)",
                color: "rgba(225, 238, 255, 0.82)",
                fontSize: 12.5,
                fontWeight: 500,
                letterSpacing: 0.3,
                textAlign: "center",
              }}
            >
              {data.disclaimer}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
