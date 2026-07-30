/**
 * The GL energy floor (POLISH P3) — the legacy background system
 * (frontend/src/components/layout/AnimatedBackground.tsx) ported whole
 * and re-keyed to the brand: instanced matte hex tiles breathing over a
 * simplex-noise light field, bloom, and the pointer ripple. Owner
 * decision 2 (15_polish.md §2): the full three.js port on tier A/B.
 *
 * It lives in renderers/world/ because ONLY this tree may import three.js
 * (the eslint boundary + the bundle gate are one guarantee, D7 §3.3) —
 * the atmosphere reaches it through a dynamic import, so a tier-C device
 * still never downloads three.js.
 *
 * The re-key (decision 1): every colour is the warm-light family. The
 * legacy copper stays as the light's warmth; the legacy ELECTRIC_BLUE is
 * retired — its role (a second drifting pulse) is played by a brighter
 * warm white. No gold: the floor is light, never signal (art bible §13).
 *
 * The fallback ladder (15_polish.md §4): a second context loss, or 90
 * frames below 30fps inside a 5-second window, calls onFallback — the
 * mount swaps to the Canvas-2D floor in place, silently. Never a black
 * rectangle (D7 §4).
 */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

import { luminanceAt } from "../../atmosphere/scene";

const LIGHT_WARM = new THREE.Vector3(0.38, 0.35, 0.3);
const LIGHT_BRIGHT = new THREE.Vector3(0.48, 0.45, 0.38);
const TILE_COLOR = new THREE.Color("#0b0a08");
const BACKGROUND_COLOR = new THREE.Color("#060505");

// The legacy grid density: the field must outrun the light plane and the
// fog horizon, or the bare shader plane glows past the far edge of the
// tiles (found by screenshot — a bright scalloped band across the top).
const HEX_RADIUS = 0.2;
const HEX_HEIGHT = 0.2;
const GAP = 0.03;
const GRID_ROWS = 60;
const GRID_COLS = 105;

const FPS_FLOOR_MS = 33;
const BREACH_FRAMES = 90;
const BREACH_WINDOW_MS = 5000;

const vertexShader = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/* The legacy "lava" shader unchanged in structure; both colours are now
 * the one warm family and uGlow carries day–night (art bible §4). */
const fragmentShader = `
uniform float iTime;
uniform float uGlow;
uniform vec3 colorA;
uniform vec3 colorB;

varying vec2 vUv;

vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }

float snoise(vec2 v){
  const vec4 C = vec4(0.211324865405187, 0.366025403784439,
           -0.577350269189626, 0.024390243902439);
  vec2 i  = floor(v + dot(v, C.yy) );
  vec2 x0 = v -   i + dot(i, C.xx);
  vec2 i1;
  i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))
  + i.x + vec3(0.0, i1.x, 1.0 ));
  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
  m = m*m ;
  m = m*m ;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
  vec3 g;
  g.x  = a0.x  * x0.x  + h.x  * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

void main() {
    vec2 uv = vUv * 4.0;
    float time = iTime * 0.05;
    float noise1 = snoise(uv + vec2(time, time * 0.5));
    float noise2 = snoise(uv * 1.5 - vec2(time * 0.8, time));
    float pattern = noise1 * 0.5 + noise2 * 0.5;
    float intensity = smoothstep(0.1, 0.6, pattern);
    vec3 finalColor = mix(vec3(0.0), colorA * 1.2, intensity);
    float pulse = smoothstep(0.4, 0.6, snoise(uv - vec2(time * 1.2)));
    if(pulse > 0.0) {
        finalColor = mix(finalColor, colorB * 1.3, pulse * 0.5);
    }
    gl_FragColor = vec4(finalColor * uGlow, 1.0);
}
`;

const createHexagonShape = (radius: number): THREE.Shape => {
  const shape = new THREE.Shape();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6;
    const x = radius * Math.cos(angle);
    const y = radius * Math.sin(angle);
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  shape.closePath();
  return shape;
};

const hexToWorld = (col: number, row: number, radius: number): [number, number] => {
  const width = radius * 2;
  const height = Math.sqrt(3) * radius;
  const horizSpacing = width * 0.75;
  const vertSpacing = height;
  const x = col * (horizSpacing + GAP * 0.5);
  const z = row * (vertSpacing + GAP) + (col % 2 === 1 ? (vertSpacing + GAP) / 2 : 0);
  return [x, z];
};

export default function AtmosphereFloor({
  onFallback,
}: {
  onFallback: () => void;
}): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const fallbackRef = useRef(onFallback);
  fallbackRef.current = onFallback;

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;

    // Sized to the container (the lower viewport band), not the window.
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;

    const scene = new THREE.Scene();
    scene.background = BACKGROUND_COLOR;
    // The horizon: the far half of the frame dissolves into the vignette
    // rather than showing the field's edge.
    scene.fog = new THREE.Fog(0x000000, 8, 26);

    // Slightly higher horizon than the legacy scene — the floor band
    // reaches ~40% up the frame, like the wireframes' floorwrap.
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 100);
    camera.position.set(0, 8, 10);
    camera.lookAt(0, -5, -9);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch {
      fallbackRef.current();
      return;
    }
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    container.appendChild(renderer.domElement);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    // Bloom kept LOW: the estate's light is calm; the legacy "lava"
    // intensity read as harsh against the still line (screenshot round).
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(width, height),
      0.25,
      0.35,
      0.2,
    );
    composer.addPass(bloom);

    // The light field under the tiles. Direct references to the two
    // mutable uniforms — strict indexing has no view into three's map.
    const timeUniform = { value: 0 };
    const glowUniform = { value: 1 };
    const planeMaterial = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        iTime: timeUniform,
        uGlow: glowUniform,
        colorA: { value: LIGHT_WARM },
        colorB: { value: LIGHT_BRIGHT },
      },
    });
    // Kept just inside the tile field's extent (105 cols ≈ 31.5 units)
    // so the light only ever shows through the gaps, never past the edge —
    // and pulled slightly toward the camera so the whole visible band is lit.
    const energyFloor = new THREE.Mesh(
      new THREE.PlaneGeometry(34, 26),
      planeMaterial,
    );
    energyFloor.rotation.x = -Math.PI / 2;
    energyFloor.position.set(0, -0.1, -1);
    scene.add(energyFloor);

    // The matte tiles.
    const extrudeGeometry = new THREE.ExtrudeGeometry(
      createHexagonShape(HEX_RADIUS),
      {
        depth: HEX_HEIGHT,
        bevelEnabled: true,
        bevelThickness: 0.02,
        bevelSize: 0.02,
        bevelSegments: 1,
      },
    );
    extrudeGeometry.rotateX(Math.PI / 2);
    const tileMaterial = new THREE.MeshStandardMaterial({
      color: TILE_COLOR,
      roughness: 0.8,
      metalness: 0.2,
    });
    const instanceCount = GRID_ROWS * GRID_COLS;
    const hexMesh = new THREE.InstancedMesh(
      extrudeGeometry,
      tileMaterial,
      instanceCount,
    );
    scene.add(hexMesh);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.3);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);
    // The legacy rim light was blue; the brand's night has warm lamplight.
    const rimLight = new THREE.PointLight(0xfff6e6, 0.25);
    rimLight.position.set(-10, 5, -5);
    scene.add(rimLight);

    const dummy = new THREE.Object3D();
    const centre = hexToWorld(GRID_COLS / 2, GRID_ROWS / 2, HEX_RADIUS);
    const positions: { x: number; z: number }[] = [];
    let index = 0;
    for (let row = 0; row < GRID_ROWS; row++) {
      for (let col = 0; col < GRID_COLS; col++) {
        const [x, z] = hexToWorld(col, row, HEX_RADIUS);
        const finalX = x - centre[0];
        const finalZ = z - centre[1];
        dummy.position.set(finalX, 0, finalZ);
        dummy.updateMatrix();
        hexMesh.setMatrixAt(index, dummy.matrix);
        positions.push({ x: finalX, z: finalZ });
        index++;
      }
    }
    hexMesh.instanceMatrix.needsUpdate = true;

    // Day–night as luminance, re-read on a minute clock (art bible §4).
    const applyLuminance = (): void => {
      const lum = luminanceAt(new Date());
      glowUniform.value = lum.glow;
      dirLight.intensity = 0.3 * lum.face;
    };
    applyLuminance();
    const luminanceTimer = setInterval(applyLuminance, 60_000);

    const clock = new THREE.Clock();
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2(-10, -10);
    const onMouseMove = (event: MouseEvent): void => {
      mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", onMouseMove);

    // The fallback ladder's two triggers.
    let contextLosses = 0;
    const onContextLost = (event: Event): void => {
      event.preventDefault();
      contextLosses += 1;
      if (contextLosses >= 2) fallbackRef.current();
    };
    renderer.domElement.addEventListener("webglcontextlost", onContextLost);

    let slowFrames = 0;
    let windowStart = performance.now();
    let lastFrame = windowStart;

    let frameHandle: number | null = null;
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const pointerTarget = new THREE.Vector3();

    const animate = (): void => {
      frameHandle = requestAnimationFrame(animate);
      const nowMs = performance.now();
      if (nowMs - lastFrame > FPS_FLOOR_MS) slowFrames += 1;
      lastFrame = nowMs;
      if (nowMs - windowStart > BREACH_WINDOW_MS) {
        if (slowFrames >= BREACH_FRAMES) {
          fallbackRef.current();
          return;
        }
        slowFrames = 0;
        windowStart = nowMs;
      }

      const time = clock.getElapsedTime();
      timeUniform.value = time;

      raycaster.setFromCamera(mouse, camera);
      const hit = raycaster.ray.intersectPlane(groundPlane, pointerTarget);
      let i = 0;
      for (let row = 0; row < GRID_ROWS; row++) {
        for (let col = 0; col < GRID_COLS; col++) {
          const pos = positions[i];
          if (pos === undefined) {
            i++;
            continue;
          }
          const wave = Math.sin(pos.z * 0.1 + time * 0.15) * 0.03;
          let lift = 0;
          if (hit !== null) {
            const d = Math.hypot(pos.x - pointerTarget.x, pos.z - pointerTarget.z);
            if (d < 4) lift = (1 - d / 4) * 0.3;
          }
          dummy.position.set(pos.x, wave + lift, pos.z);
          dummy.updateMatrix();
          hexMesh.setMatrixAt(i, dummy.matrix);
          i++;
        }
      }
      hexMesh.instanceMatrix.needsUpdate = true;
      composer.render();
    };
    animate();

    const onResize = (): void => {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      if (frameHandle !== null) cancelAnimationFrame(frameHandle);
      clearInterval(luminanceTimer);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
      extrudeGeometry.dispose();
      tileMaterial.dispose();
      planeMaterial.dispose();
      energyFloor.geometry.dispose();
      composer.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      data-part="atmosphere-floor-gl"
      style={{ position: "absolute", inset: 0 }}
    />
  );
}
