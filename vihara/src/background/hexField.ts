import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

/**
 * The hex-field background, extracted from the legacy app so it can be
 * re-keyed without being rewritten.
 *
 * Redesign decision D2: the owner's approved background is
 * `frontend/src/components/layout/AnimatedBackground.tsx`, ported *verbatim*
 * as `LegacyBackground.tsx` (byte-identical — `tests/background_verbatim.test.ts`
 * fails if that stops being true). This module is the same scene with the four
 * colours lifted into a parameter, so a brand-keyed variant can be shown beside
 * the original with the difference provably limited to palette.
 *
 * Everything below — the two shaders, the noise function, the grid dimensions,
 * the camera, the fog, the bloom parameters, the breathing wave, the mouse lift
 * — is character-identical to the legacy file. `tests/background_verbatim.test.ts`
 * asserts the shader sources and the geometry constants still match, so this
 * cannot silently drift into "a background that looks a bit like the one that
 * was approved".
 */

// ============================================================================
// SHADERS (The secret sauce for the "Lava" look)
// ============================================================================

const vertexShader = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = `
uniform float iTime;
uniform vec3 iResolution;
uniform vec3 colorA;
uniform vec3 colorB;

varying vec2 vUv;

// Simplex 2D noise
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
    // Scale UVs for pattern size
    vec2 uv = vUv * 4.0;
    
    // Create organic movement - SLOWED DOWN
    float time = iTime * 0.05; // Was 0.2
    float noise1 = snoise(uv + vec2(time, time * 0.5));
    float noise2 = snoise(uv * 1.5 - vec2(time * 0.8, time));
    
    // Combine noise layers
    float pattern = noise1 * 0.5 + noise2 * 0.5;
    
    // Sharpen the pattern to create "cracks" of light
    float intensity = smoothstep(0.1, 0.6, pattern);
    
    // mostly Dark (0.0) with bright peaks (1.0), but less intense
    vec3 finalColor = mix(vec3(0.0), colorA * 1.2, intensity); // Reduced multiplier
    
    // Add subtle blue pulses
    float bluePulse = smoothstep(0.4, 0.6, snoise(uv - vec2(time * 1.2)));
    if(bluePulse > 0.0) {
        finalColor = mix(finalColor, colorB * 1.3, bluePulse * 0.5); // Reduced multiplier
    }
    
    gl_FragColor = vec4(finalColor, 1.0);
}
`;

// ============================================================================
// GEOMETRY CONSTANTS — legacy values, unchanged
// ============================================================================
export const HEX_RADIUS = 0.2;
export const HEX_HEIGHT = 0.2;
export const GAP = 0.03; // Defined gap for light to shine through
export const GRID_ROWS = 60;
export const GRID_COLS = 105;

/** The four colours that make one variant differ from another. */
export interface HexFieldPalette {
  /** Primary crack-of-light colour (`colorA`). Legacy: vec3(0.4, 0.2, 0.1). */
  colorA: THREE.Vector3;
  /** Secondary pulse colour (`colorB`). Legacy: vec3(0.1, 0.2, 0.4). */
  colorB: THREE.Vector3;
  /** The hex tile surface. Legacy: #080808. */
  tile: THREE.Color;
  /** The scene clear colour — the haze above the horizon. Legacy: #382b02. */
  background: THREE.Color;
}

// ============================================================================
// UTILS
// ============================================================================
const createHexagonShape = (radius: number) => {
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

  // Add fixed gap
  const x = col * (horizSpacing + GAP * 0.5);
  const z = row * (vertSpacing + GAP) + (col % 2 === 1 ? (vertSpacing + GAP) / 2 : 0);

  return [x, z];
};

/**
 * Mounts the field into `container` and returns a teardown function.
 * The caller owns the container's sizing and stacking.
 */
export function createHexField(
  container: HTMLElement,
  palette: HexFieldPalette,
): () => void {
  const width = window.innerWidth;
  const height = window.innerHeight;

  // Scene
  const scene = new THREE.Scene();
  scene.background = palette.background;
  // Fog makes distant tiles fade into darkness (cinematic)
  scene.fog = new THREE.Fog(0x000000, 10, 40);

  // Camera - Very steep angle to push perspective to top
  const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 100);
  camera.position.set(0, 9, 7);
  camera.lookAt(0, -8, -6);

  // Renderer
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  // Post-processing
  const composer = new EffectComposer(renderer);
  const renderPass = new RenderPass(scene, camera);
  composer.addPass(renderPass);

  // Intense Bloom for the "Lava" effect
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(width, height),
    0.8, // strength
    0.4, // radius
    0.1, // threshold
  );
  composer.addPass(bloomPass);

  // --------------------------------------------------------------------
  // 1. ENERGY FLOOR (The glowing gaps)
  // --------------------------------------------------------------------
  const planeGeometry = new THREE.PlaneGeometry(80, 80);
  const planeMaterial = new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms: {
      iTime: { value: 0 },
      colorA: { value: palette.colorA },
      colorB: { value: palette.colorB },
    },
  });

  const energyFloor = new THREE.Mesh(planeGeometry, planeMaterial);
  energyFloor.rotation.x = -Math.PI / 2;
  energyFloor.position.y = -0.1; // Just below the tiles
  scene.add(energyFloor);

  // --------------------------------------------------------------------
  // 2. HEXAGONAL TILES (Instanced Mesh)
  // --------------------------------------------------------------------
  const shape = createHexagonShape(HEX_RADIUS);
  const extrudeGeometry = new THREE.ExtrudeGeometry(shape, {
    depth: HEX_HEIGHT,
    bevelEnabled: true,
    bevelThickness: 0.02,
    bevelSize: 0.02,
    bevelSegments: 1,
  });
  extrudeGeometry.rotateX(Math.PI / 2); // Lay flat

  const tileMaterial = new THREE.MeshStandardMaterial({
    color: palette.tile,
    roughness: 0.8, // Matte
    metalness: 0.2, // Slightly metallic
  });

  const instanceCount = GRID_ROWS * GRID_COLS;
  const hexMesh = new THREE.InstancedMesh(extrudeGeometry, tileMaterial, instanceCount);
  scene.add(hexMesh);

  // Light for the tiles themselves (so they aren't pitch black voids)
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.3);
  dirLight.position.set(10, 20, 10);
  scene.add(dirLight);

  // Rim light to catch edges
  const pointLight = new THREE.PointLight(0x4444ff, 0.4);
  pointLight.position.set(-10, 5, -5);
  scene.add(pointLight);

  // Position Logic
  const dummy = new THREE.Object3D();
  const centerCol = GRID_COLS / 2;
  const centerRow = GRID_ROWS / 2;
  const positions: { x: number; z: number; id: number }[] = [];

  let idx = 0;
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const [x, z] = hexToWorld(c, r, HEX_RADIUS);
      // Center the grid
      const finalX = x - hexToWorld(centerCol, centerRow, HEX_RADIUS)[0];
      const finalZ = z - hexToWorld(centerCol, centerRow, HEX_RADIUS)[1];

      // Keep strictly flat for the "tight grid" look
      dummy.position.set(finalX, 0, finalZ);
      dummy.updateMatrix();
      hexMesh.setMatrixAt(idx, dummy.matrix);

      positions.push({ x: finalX, z: finalZ, id: idx });
      idx++;
    }
  }
  hexMesh.instanceMatrix.needsUpdate = true;

  // --------------------------------------------------------------------
  // ANIMATION LOOP
  // --------------------------------------------------------------------
  const clock = new THREE.Clock();
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2(-10, -10);

  const onMouseMove = (event: MouseEvent) => {
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
  };
  window.addEventListener("mousemove", onMouseMove);

  let raf = 0;
  const animate = () => {
    raf = requestAnimationFrame(animate);
    const time = clock.getElapsedTime();

    // Update Shader Time
    planeMaterial.uniforms["iTime"]!.value = time;

    // Interactive Tile Ripple
    if (hexMesh) {
      raycaster.setFromCamera(mouse, camera);
      // Intersect with the invisible Y=0 plane
      const targetValues = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
      const target = new THREE.Vector3();
      raycaster.ray.intersectPlane(targetValues, target);

      let i = 0;
      for (let r = 0; r < GRID_ROWS; r++) {
        for (let c = 0; c < GRID_COLS; c++) {
          const pos = positions[i]!;

          // Subtle breathing - SLOWED DOWN
          const waveZ = Math.sin(pos.z * 0.1 + time * 0.15) * 0.03;

          // Mouse interaction lift
          let lift = 0;
          if (target) {
            const d = Math.sqrt((pos.x - target.x) ** 2 + (pos.z - target.z) ** 2);
            if (d < 4) {
              lift = (1 - d / 4) * 0.3; // Max lift 0.3 units
            }
          }

          dummy.position.set(pos.x, waveZ + lift, pos.z);
          dummy.updateMatrix();
          hexMesh.setMatrixAt(i, dummy.matrix);
          i++;
        }
      }
      hexMesh.instanceMatrix.needsUpdate = true;
    }

    composer.render();
  };

  animate();

  const onResize = () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    composer.setSize(w, h);
  };
  window.addEventListener("resize", onResize);

  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("resize", onResize);
    container.innerHTML = "";
    extrudeGeometry.dispose();
    planeGeometry.dispose();
    tileMaterial.dispose();
    planeMaterial.dispose();
    composer.dispose();
    renderer.dispose();
  };
}

// ============================================================================
// THE TWO PALETTES (redesign decision D2)
// ============================================================================

/**
 * Exactly the legacy values.
 *
 * `#382b02ff` is **deliberately left invalid.** THREE.Color does not accept
 * 8-digit hex: it logs `Invalid hex color` and leaves the colour at its
 * default white. So the legacy app's intended warm-olive haze has never once
 * rendered — `scene.background` is white there, and the only reason nobody
 * noticed is that this camera (y=9, looking at y=-8) never sees above the
 * horizon, so the clear colour is covered by floor in every frame.
 *
 * Do not "fix" this to `#382b02`. Decision D2 says this variant reproduces the
 * approved app, and correcting the bug would make it reproduce something the
 * owner has never seen — a warm haze appearing at the top of the frame is a
 * visible change, not a bug fix. The valid-hex version of the intent lives in
 * `BRAND_PALETTE` below, where it is a deliberate choice rather than a typo.
 */
export const LEGACY_PALETTE: HexFieldPalette = {
  colorA: new THREE.Vector3(0.4, 0.2, 0.1), // Significantly Dimmed Copper/Orange
  colorB: new THREE.Vector3(0.1, 0.2, 0.4), // Significantly Dimmed Steel Blue
  tile: new THREE.Color("#080808"), // Matte Black
  background: new THREE.Color("#382b02ff"),
};

/**
 * The brand re-key.
 *
 * `colorA` is brand gold `--gold-500` (#edab48) scaled to the same luminance
 * the legacy copper carried, so the crack-of-light reads at the intensity the
 * owner approved rather than brighter. `colorB` drops the electric blue for a
 * desaturated cool neutral — the brand has no second hue, and art bible §2.1's
 * gold budget survives a cool *sheen* where it would not survive a cool *hue*.
 * The tile falls to `--ink-900` and the haze to a deep gold-tinted near-black,
 * so the frame is the brand's canvas rather than the legacy olive.
 */
export const BRAND_PALETTE: HexFieldPalette = {
  colorA: new THREE.Vector3(0.39, 0.28, 0.12), // --gold-500 at legacy luminance
  colorB: new THREE.Vector3(0.16, 0.18, 0.22), // desaturated cool neutral
  tile: new THREE.Color("#100e0c"), // --ink-900
  background: new THREE.Color("#241a06"), // warm haze, brand-keyed
};
