import * as THREE from "three";

/**
 * Full-screen SDF raymarched hero (Year-3026 Sanctum core).
 *
 * Why: polygon primitives cannot produce soft smooth-union organic forms, volumetric
 * halo accumulation, or believable chrome/subsurface reflections in one pass. A
 * fragment-shader raymarcher gives those for free and is fully deterministic per frame
 * (driven only by `uTime`, `uProgress`, `uBeat`), so Remotion frame rendering stays exact.
 *
 * The quad ignores the camera (clip-space triangle) and is drawn first (renderOrder -10)
 * so the transparent WebGL canvas composites over the 4K world video beneath.
 */

const VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const FRAG = `
varying vec2 vUv;
uniform float uTime;
uniform float uProgress;
uniform float uBeat;
uniform float uAspect;

mat2 rot(float a) {
  float c = cos(a);
  float s = sin(a);
  return mat2(c, -s, s, c);
}

float smin(float a, float b, float k) {
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}

float sdTorusXZ(vec3 p, float R, float r) {
  vec2 q = vec2(length(p.xz) - R, p.y);
  return length(q) - r;
}

float sdSeg(vec3 p, vec3 a, vec3 b, float r) {
  vec3 pa = p - a;
  vec3 ba = b - a;
  float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h) - r;
}

// Anatomical two-ventricle heart with apex, beating with uBeat
float sdHeart(vec3 p) {
  float s = 1.25 + uBeat * 0.07;
  p /= s;
  vec3 pl = p - vec3(-0.22, 0.05, 0.0);
  vec3 pr = p - vec3(0.24, 0.18, -0.05);
  float lv = length(pl * vec3(1.0, 0.92, 1.05)) - 0.78;
  float rv = length(pr * vec3(1.12, 1.0, 1.0)) - 0.62;
  float body = smin(lv, rv, 0.32);
  float apex = length(p - vec3(-0.12, -0.72, 0.02)) - 0.32;
  return smin(body, apex, 0.32) * s;
}

// Gyroid chrome lattice confined to a spherical shell: thin see-through sheets, heart visible through the holes
float sdShell(vec3 p) {
  p.xz = rot(uTime * 0.18 + p.y * 0.6) * p.xz;
  vec3 g = p * 2.1;
  float gyroid = sin(g.x) * cos(g.y) + sin(g.y) * cos(g.z) + sin(g.z) * cos(g.x);
  float sheet = abs(gyroid) - 0.28;
  float sphere = abs(length(p) - 2.6) - 0.02;
  return max(sheet * 0.45, sphere);
}

vec2 map(vec3 p) {
  vec2 res = vec2(sdHeart(p), 0.0);

  float sh = sdShell(p);
  if (sh < res.x) res = vec2(sh, 1.0);

  // Two gold gyroscope rings
  float r1 = sdTorusXZ(p, 2.9, 0.022);
  vec3 q = p;
  q.xy = rot(0.9) * q.xy;
  q.yz = rot(0.5) * q.yz;
  float r2 = sdTorusXZ(q, 2.75, 0.018);
  float rings = min(r1, r2);
  if (rings < res.x) res = vec2(rings, 2.0);

  // Seven plasma arteries radiating outward from the heart
  float art = 1e5;
  for (int i = 0; i < 7; i++) {
    float fi = float(i);
    float ang = fi * 0.8975979 + 0.25;
    vec3 a = vec3(cos(ang) * 0.5, sin(fi * 1.9) * 0.25, sin(ang) * 0.5);
    vec3 b = vec3(cos(ang) * 2.6, sin(fi * 1.9) * 0.9, sin(ang) * 2.6);
    art = min(art, sdSeg(p, a, b, 0.028));
  }
  if (art < res.x) res = vec2(art, 3.0);

  return res;
}

vec3 calcNormal(vec3 p) {
  vec2 e = vec2(0.0015, 0.0);
  return normalize(vec3(
    map(p + e.xyy).x - map(p - e.xyy).x,
    map(p + e.yxy).x - map(p - e.yxy).x,
    map(p + e.yyx).x - map(p - e.yyx).x
  ));
}

vec3 env(vec3 r) {
  vec3 sky = mix(vec3(0.02, 0.03, 0.06), vec3(0.55, 0.35, 0.12), smoothstep(-0.3, 0.8, r.y));
  vec3 key = vec3(1.0, 0.85, 0.6) * pow(max(dot(r, normalize(vec3(-0.5, 0.7, 0.6))), 0.0), 18.0) * 2.0;
  vec3 rim = vec3(0.25, 0.85, 1.0) * pow(max(dot(r, normalize(vec3(0.9, 0.1, -0.3))), 0.0), 10.0) * 1.4;
  return sky + key + rim;
}

vec3 shade(vec3 p, vec3 rd, vec3 n, float id) {
  vec3 v = -rd;
  float ndv = clamp(dot(n, v), 0.0, 1.0);
  float fres = pow(1.0 - ndv, 4.0);
  vec3 E = env(reflect(rd, n));
  vec3 col;
  if (id < 0.5) {
    // Ruby heart: subsurface glow + internal magma pulse
    float sss = pow(clamp(dot(-n, rd) * 0.5 + 0.5, 0.0, 1.0), 2.0);
    float magma = 0.5 + 0.5 * sin(p.y * 7.0 - uTime * 4.0 + sin(p.x * 5.0) * 1.3);
    vec3 base = vec3(0.42, 0.005, 0.05);
    col = base * (0.18 + 0.8 * max(dot(n, normalize(vec3(0.4, 0.8, 0.5))), 0.0));
    col += vec3(1.0, 0.18, 0.08) * sss * (0.2 + uBeat * 1.1) * magma * 0.9;
    col += vec3(1.0, 0.7, 0.3) * fres * 0.35 * E;
  } else if (id < 1.5) {
    // Gold-chrome gyroid lattice with thin-film iridescence
    vec3 film = 0.5 + 0.5 * cos(vec3(0.0, 2.1, 4.2) + fres * 5.0 + uTime * 0.4);
    vec3 chrome = E * vec3(1.0, 0.86, 0.6);
    col = chrome * (0.55 + fres * 1.4) + film * fres * 0.8 + vec3(0.12, 0.08, 0.02);
  } else if (id < 2.5) {
    // Gold rings
    col = vec3(1.0, 0.74, 0.32) * (0.15 + 0.9 * E * 0.7) + E * fres * 0.5;
  } else {
    // Emissive arteries
    col = vec3(0.35, 1.0, 0.9) * 2.4;
  }
  return col;
}

void main() {
  vec2 uv = vUv * 2.0 - 1.0;
  uv.x *= uAspect;

  float a = -0.35 + uProgress * 0.7;
  vec3 ro = vec3(0.0, 0.5, 8.0);
  ro.xz = rot(a) * ro.xz;
  vec3 ww = normalize(vec3(0.0) - ro);
  vec3 uu = normalize(cross(ww, vec3(0.0, 1.0, 0.0)));
  vec3 vv = cross(uu, ww);
  vec3 rd = normalize(uv.x * uu + uv.y * vv + 2.0 * ww);

  float t = 0.0;
  float glow = 0.0;
  float hitT = -1.0;
  float hitId = -1.0;
  for (int i = 0; i < 120; i++) {
    vec3 p = ro + rd * t;
    vec2 h = map(p);
    glow += 0.003 / (0.03 + abs(h.x));
    if (h.x < 0.0015) {
      hitT = t;
      hitId = h.y;
      break;
    }
    t += h.x * 0.9;
    if (t > 22.0) break;
  }

  vec3 col = vec3(0.0);
  float alpha = 0.0;
  if (hitT > 0.0) {
    vec3 p = ro + rd * hitT;
    vec3 n = calcNormal(p);
    col = shade(p, rd, n, hitId);
    alpha = 1.0;
  }

  vec3 haloCol = mix(vec3(1.0, 0.2, 0.4), vec3(0.2, 0.8, 1.0), 0.5 + 0.5 * sin(uTime * 0.3));
  col += haloCol * glow * 0.02;
  alpha = max(alpha, clamp(glow * 0.035, 0.0, 1.0));

  // Filmic tone map (no hard clipping of highlights)
  col = col / (1.0 + col);
  col = pow(col, vec3(0.85));
  gl_FragColor = vec4(col, alpha);
}
`;

export interface RaymarchHero {
  mesh: THREE.Mesh;
  uniforms: {
    uTime: { value: number };
    uProgress: { value: number };
    uBeat: { value: number };
    uAspect: { value: number };
  };
}

export function createRaymarchHero(width: number, height: number): RaymarchHero {
  const uniforms = {
    uTime: { value: 0 },
    uProgress: { value: 0 },
    uBeat: { value: 0 },
    uAspect: { value: width / height },
  };
  const material = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -10;
  return { mesh, uniforms };
}
