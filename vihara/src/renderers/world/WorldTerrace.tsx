/**
 * The walkable terrace (WORLD W4) — the only module tree that imports
 * three.js, and only ever reached through a dynamic import behind the tier
 * gate: a tier-C device never downloads this chunk (D7 §3.3).
 *
 * The construction language is art bible §13, structurally: floating
 * plinths (sites rest off the ground, light beneath sells the float),
 * holographic volumes with a ghost wireframe scaffold, flat
 * surface-printed roads at the world's own perspective, the energy floor
 * as light-never-gold, one gold beacon per raised hand breathing on a
 * ~4s cycle — the only repeating *attention* animation; road flow and
 * lamplight are sanctioned world-liveness (R1 ruling 6). Day–night is
 * luminance: one key colour, two intensities.
 *
 * Numbers on the map come from the estate read model exclusively — this
 * renderer computes no business truth, it draws the layout module's.
 */
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import type { EstateSnapshot } from "./layout";
import { placeTerritory, type PlacedDistrict, type Road } from "./layout";

const GOLD = "#edab48";
const GOLD_DARK = "#a8722a";
const WARM_WHITE = "#fffdf9";
const INK = "#0a0908";
const SURFACE = "#1a1714";

export interface WorldTerraceProps {
  estate: EstateSnapshot;
  quality: "full" | "reduced";
  onEnterDistrict: (code: string) => void;
  onSustainedBreach: () => void;
  onContextLost: () => void;
}

export default function WorldTerrace({
  estate,
  quality,
  onEnterDistrict,
  onSustainedBreach,
  onContextLost,
}: WorldTerraceProps): JSX.Element {
  const layout = useMemo(() => placeTerritory(estate), [estate]);
  const lossCount = useRef(0);

  return (
    <Canvas
      shadows={quality === "full"}
      dpr={quality === "full" ? [1, 2] : [0.5, 1]}
      camera={{ position: [0, 16, 24], fov: 42 }}
      onCreated={({ gl }) => {
        gl.domElement.addEventListener("webglcontextlost", (event) => {
          event.preventDefault();
          lossCount.current += 1;
          if (lossCount.current >= 2) {
            // Restore once; on a second loss switch to the sheet and say
            // so — never a black rectangle (D7 §4).
            onContextLost();
          }
        });
      }}
    >
      <color attach="background" args={[INK]} />
      <FrameWatchdog
        floorFps={quality === "full" ? 45 : 24}
        onSustainedBreach={onSustainedBreach}
      />
      <ambientLight
        intensity={layout.lighting.ambientIntensity}
        color={WARM_WHITE}
      />
      <directionalLight
        position={[8, 18, 6]}
        intensity={layout.lighting.keyIntensity}
        color={layout.lighting.keyColor}
        castShadow={quality === "full"}
      />
      <EnergyFloor bounds={layout.bounds} />
      {layout.roads.map((road, index) => (
        <RoadStrip key={index} road={road} />
      ))}
      {layout.districts.map((district) => (
        <DistrictSite
          key={district.process_code}
          district={district}
          lampIntensity={layout.lighting.lampIntensity}
          onEnter={() => onEnterDistrict(district.process_code)}
        />
      ))}
      {layout.gatehouses.map((gatehouse) => (
        <group
          key={gatehouse.gateway_code}
          position={[gatehouse.position[0], 0, gatehouse.position[1]]}
        >
          <mesh position={[0, 0.25, 0]}>
            <boxGeometry args={[1.6, 0.5, 1.2]} />
            <meshStandardMaterial color={SURFACE} />
          </mesh>
        </group>
      ))}
      {layout.beacons.map((beacon) => (
        <Beacon
          key={beacon.approval_id}
          position={[beacon.position[0], beacon.position[1]]}
        />
      ))}
    </Canvas>
  );
}

/** 90 frames below the floor inside a 5s window (D7 §3.2) — long enough
 * that one scroll hitch does not demote a working device. */
function FrameWatchdog({
  floorFps,
  onSustainedBreach,
}: {
  floorFps: number;
  onSustainedBreach: () => void;
}): null {
  const slowFrames = useRef(0);
  const windowStart = useRef(0);
  const fired = useRef(false);
  useFrame((state, delta) => {
    if (fired.current) return;
    const now = state.clock.elapsedTime;
    if (now - windowStart.current > 5) {
      windowStart.current = now;
      slowFrames.current = 0;
    }
    if (delta > 1 / floorFps) {
      slowFrames.current += 1;
      if (slowFrames.current >= 90) {
        fired.current = true;
        onSustainedBreach();
      }
    }
  });
  return null;
}

function EnergyFloor({ bounds }: { bounds: number }): JSX.Element {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]} receiveShadow>
        <planeGeometry args={[bounds * 2.4, bounds * 2.4]} />
        <meshStandardMaterial color={INK} />
      </mesh>
      {/* The glow is light, never gold (§13) — a warm-white grid, faint. */}
      <gridHelper
        args={[bounds * 2.4, 48, WARM_WHITE, WARM_WHITE]}
        position={[0, -0.04, 0]}
      >
        <meshBasicMaterial
          attach="material"
          color={WARM_WHITE}
          transparent
          opacity={0.07}
        />
      </gridHelper>
    </group>
  );
}

function DistrictSite({
  district,
  lampIntensity,
  onEnter,
}: {
  district: PlacedDistrict;
  lampIntensity: number;
  onEnter: () => void;
}): JSX.Element {
  const [hover, setHover] = useState(false);
  const height = 0.9 + district.colleagues.length * 0.35;
  const [x, z] = district.position;
  const float = hover ? 0.55 : 0.35;

  return (
    <group position={[x, 0, z]}>
      {/* Light beneath sells the float (§13). */}
      <pointLight
        position={[0, 0.12, 0]}
        intensity={hover ? 0.9 : 0.4}
        color={WARM_WHITE}
        distance={3.2}
      />
      {lampIntensity > 0.5 && (
        <pointLight
          position={[0, height + 1.2, 0]}
          intensity={lampIntensity}
          color={WARM_WHITE}
          distance={6}
        />
      )}
      <mesh
        position={[0, float, 0]}
        castShadow
        onClick={(event) => {
          event.stopPropagation();
          onEnter();
        }}
        onPointerOver={() => setHover(true)}
        onPointerOut={() => setHover(false)}
      >
        <boxGeometry args={[2.6, 0.3, 2.6]} />
        <meshStandardMaterial color={SURFACE} />
      </mesh>
      {/* The holographic volume: translucent warm glass … */}
      <mesh position={[0, float + 0.15 + height / 2, 0]}>
        <boxGeometry args={[2.1, height, 2.1]} />
        <meshStandardMaterial
          color={WARM_WHITE}
          transparent
          opacity={0.09}
          depthWrite={false}
        />
      </mesh>
      {/* … with the ghost wireframe scaffold above the solid mass. */}
      <mesh position={[0, float + 0.15 + height + 0.35, 0]}>
        <boxGeometry args={[2.1, 0.6, 2.1]} />
        <meshBasicMaterial color={WARM_WHITE} wireframe transparent opacity={0.18} />
      </mesh>
      <Weather state={district.weather.state} height={float + height + 1.4} />
    </group>
  );
}

function Weather({
  state,
  height,
}: {
  state: string;
  height: number;
}): JSX.Element | null {
  const shimmer = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (shimmer.current !== null) {
      // Faster than any other motion in the product (art bible §8).
      shimmer.current.scale.y = 1 + Math.sin(clock.elapsedTime * 9) * 0.18;
    }
  });
  if (state === "storm") {
    return (
      <mesh position={[0, height + 0.6, 0]}>
        <boxGeometry args={[2.4, 0.35, 2.4]} />
        <meshStandardMaterial color="#000000" transparent opacity={0.82} />
      </mesh>
    );
  }
  if (state === "heat-shimmer") {
    return (
      <mesh ref={shimmer} position={[0, height, 0]}>
        <planeGeometry args={[1.6, 1.8]} />
        <meshBasicMaterial
          color={WARM_WHITE}
          transparent
          opacity={0.12}
          side={THREE.DoubleSide}
        />
      </mesh>
    );
  }
  if (state === "fog") {
    return (
      <mesh position={[0, 0.55, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[2.6, 24]} />
        <meshBasicMaterial color={WARM_WHITE} transparent opacity={0.1} />
      </mesh>
    );
  }
  // clear and moonlit add nothing here — moonlit is the lamp's job, and
  // clear is silence (art bible §8).
  return null;
}

/** Flat surface-printed roads with a dot flow at constant velocity —
 * world-liveness, not attention (R1 ruling 6). */
function RoadStrip({ road }: { road: Road }): JSX.Element {
  const [fx, fz] = road.from;
  const [tx, tz] = road.to;
  const length = Math.hypot(tx - fx, tz - fz);
  const angle = Math.atan2(tz - fz, tx - fx);
  const dot = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (dot.current === null || road.intensity === 0) return;
    const t = (clock.elapsedTime * 0.12) % 1;
    dot.current.position.set(fx + (tx - fx) * t, 0.06, fz + (tz - fz) * t);
  });
  return (
    <group>
      <mesh
        position={[(fx + tx) / 2, 0.01, (fz + tz) / 2]}
        rotation={[0, -angle, 0]}
      >
        <boxGeometry args={[length, 0.02, 0.14]} />
        <meshBasicMaterial
          color={WARM_WHITE}
          transparent
          opacity={0.05 + road.intensity * 0.08}
        />
      </mesh>
      {road.intensity > 0 && (
        <mesh ref={dot}>
          <sphereGeometry args={[0.07, 8, 8]} />
          <meshBasicMaterial color={WARM_WHITE} />
        </mesh>
      )}
    </group>
  );
}

/** The one gold ripple: a raised hand, breathing on a ~4s cycle — the
 * slowest thing in the product and the only repeating attention animation
 * (art bible §9). Flat gold-500; the gradient stays reserved. */
function Beacon({ position }: { position: [number, number] }): JSX.Element {
  const ring = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ring.current === null) return;
    const breath = 1 + Math.sin((clock.elapsedTime * Math.PI) / 2) * 0.12;
    ring.current.scale.setScalar(breath);
  });
  const [x, z] = position;
  return (
    <group position={[x, 0, z]}>
      <mesh ref={ring} position={[0, 3.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.45, 0.06, 12, 32]} />
        <meshBasicMaterial color={GOLD} />
      </mesh>
      <mesh position={[0, 1.8, 0]}>
        <cylinderGeometry args={[0.015, 0.015, 2.8, 6]} />
        <meshBasicMaterial color={GOLD_DARK} transparent opacity={0.5} />
      </mesh>
    </group>
  );
}
