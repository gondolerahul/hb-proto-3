/**
 * The W district room (POLISH M2, D6 §5, district-visual.html) — a
 * floating district plate seen from a low diagonal: colleague workplaces
 * stand on it as ghost volumes, names print on the plate (never
 * billboard), a raised hand gets the gold shaft and a gold needs-you
 * line — the only gold in the room — and the treasury figure prints
 * large at the plate's edge. Numbers come from the estate read model;
 * this renderer computes no business truth.
 *
 * Lives in renderers/world/ (the only tree that may import three.js),
 * reached by dynamic import from the district surface.
 */
import { Canvas } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import type { EstateDistrict } from "./layout";
import { useNamePlate } from "./plates";
import { FrameWatchdog } from "./WorldTerrace";

const GOLD = "#edab48";
const GOLD_DARK = "#a8722a";
const WARM_WHITE = "#fffdf9";
const INK = "#0a0908";
const SURFACE = "#1a1714";

const PLATE_W = 13;
const PLATE_D = 8.5;
const PLATE_T = 0.35;
const PLATE_Y = 0.5;

export interface DistrictRoomProps {
  district: EstateDistrict;
  phase: "day" | "night";
  quality: "full" | "reduced";
  onOpenDossier: (colleague: { id: string; name: string }) => void;
  onSustainedBreach: () => void;
  onContextLost: () => void;
}

function autonomyLevel(autonomy: string): number {
  const digit = autonomy.match(/\d/);
  return digit === null ? 1 : Math.min(4, Math.max(1, Number(digit[0])));
}

/** Two loose rows across the plate — organic enough, deterministic. */
function colleaguePosition(index: number, count: number): [number, number] {
  const perRow = Math.ceil(count / 2);
  const row = index < perRow ? 0 : 1;
  const column = row === 0 ? index : index - perRow;
  const rowCount = row === 0 ? perRow : count - perRow;
  const spread = Math.min(10.5, rowCount * 2.6);
  const x =
    rowCount === 1 ? 0 : -spread / 2 + (spread / (rowCount - 1)) * column;
  const z = count <= perRow ? 0.2 : row === 0 ? -1.5 : 1.6;
  // A hair of deterministic jitter so the grid never reads as a grid.
  const jitter = ((index * 2654435761) % 100) / 100 - 0.5;
  return [x + jitter * 0.5, z + jitter * 0.35];
}

function Workplace({
  colleague,
  position,
  onOpen,
}: {
  colleague: EstateDistrict["colleagues"][number];
  position: [number, number];
  onOpen: () => void;
}): JSX.Element {
  const [hover, setHover] = useState(false);
  const height = 0.7 + autonomyLevel(colleague.autonomy) * 0.3;
  const edges = useMemo(
    () => new THREE.EdgesGeometry(new THREE.BoxGeometry(1.15, height, 1.15)),
    [height],
  );
  const namePlate = useNamePlate(colleague.name, {
    px: 64,
    weight: 600,
    tracked: false,
    font: "display",
    color: "rgba(246, 241, 233, 0.9)",
  });
  const rolePlate = useNamePlate(
    `${colleague.autonomy} · ${colleague.state}`,
    { px: 40, color: "rgba(246, 241, 233, 0.45)" },
  );
  const needsPlate = useNamePlate("● needs you", {
    px: 44,
    weight: 600,
    color: "rgba(237, 171, 72, 0.95)",
  });
  const [x, z] = position;
  const top = PLATE_Y + PLATE_T / 2;

  return (
    <group position={[x, top, z]}>
      <mesh
        position={[0, height / 2, 0]}
        onClick={(event) => {
          event.stopPropagation();
          onOpen();
        }}
        onPointerOver={() => setHover(true)}
        onPointerOut={() => setHover(false)}
      >
        <boxGeometry args={[1.15, height, 1.15]} />
        <meshStandardMaterial
          color={WARM_WHITE}
          transparent
          opacity={hover ? 0.18 : 0.12}
          depthWrite={false}
        />
      </mesh>
      <lineSegments position={[0, height / 2, 0]} geometry={edges}>
        <lineBasicMaterial
          color={WARM_WHITE}
          transparent
          opacity={hover ? 0.6 : 0.42}
        />
      </lineSegments>
      {namePlate !== null && (
        <mesh position={[0, 0.012, 1.05]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[2.3, 0.42]} />
          <meshBasicMaterial
            map={namePlate}
            transparent
            opacity={hover ? 1 : 0.85}
            depthWrite={false}
          />
        </mesh>
      )}
      {rolePlate !== null && (
        <mesh position={[0, 0.012, 1.45]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[2.1, 0.26]} />
          <meshBasicMaterial
            map={rolePlate}
            transparent
            opacity={0.8}
            depthWrite={false}
          />
        </mesh>
      )}
      {colleague.hand_raised && (
        <>
          {needsPlate !== null && (
            <mesh position={[0, 0.012, 1.78]} rotation={[-Math.PI / 2, 0, 0]}>
              <planeGeometry args={[1.9, 0.28]} />
              <meshBasicMaterial
                map={needsPlate}
                transparent
                opacity={0.95}
                depthWrite={false}
              />
            </mesh>
          )}
          {/* The gold shaft — this needs you (art bible §2.1). */}
          <mesh position={[0, height + 1.1, 0]}>
            <cylinderGeometry args={[0.015, 0.015, 2.2, 6]} />
            <meshBasicMaterial color={GOLD_DARK} transparent opacity={0.5} />
          </mesh>
          <mesh position={[0, height + 2.25, 0]}>
            <sphereGeometry args={[0.09, 12, 12]} />
            <meshBasicMaterial color={GOLD} />
          </mesh>
        </>
      )}
    </group>
  );
}

export default function DistrictRoom({
  district,
  phase,
  quality,
  onOpenDossier,
  onSustainedBreach,
  onContextLost,
}: DistrictRoomProps): JSX.Element {
  const lossCount = useRef(0);
  const plateEdges = useMemo(
    () =>
      new THREE.EdgesGeometry(new THREE.BoxGeometry(PLATE_W, PLATE_T, PLATE_D)),
    [],
  );
  const titlePlate = useNamePlate(district.name, {
    px: 96,
    color: "rgba(246, 241, 233, 0.16)",
  });
  const quarterPlate = useNamePlate(
    `${district.process_code} · ${district.quarter} quarter`,
    { px: 44, color: "rgba(246, 241, 233, 0.35)" },
  );
  const treasury = district.treasury;
  const figure =
    treasury !== null
      ? `₹${Math.round(treasury.spent / 1000)}k`
      : `${district.traffic.in_1h}/h`;
  const figureSub =
    treasury !== null
      ? `of ₹${Math.round(treasury.cap / 1000)}k envelope`
      : "signals this hour";
  const figurePlate = useNamePlate(figure, {
    px: 150,
    weight: 600,
    tracked: false,
    font: "display",
    color: "rgba(246, 241, 233, 0.85)",
  });
  const figureSubPlate = useNamePlate(figureSub, {
    px: 40,
    color: "rgba(246, 241, 233, 0.4)",
  });

  const ambient = phase === "night" ? 0.38 : 0.55;
  const key = phase === "night" ? 0.5 : 1.6;

  return (
    <Canvas
      shadows={quality === "full"}
      dpr={quality === "full" ? [1, 2] : [0.5, 1]}
      camera={{ position: [7.5, 7.5, 10.5], fov: 42 }}
      onCreated={({ gl }) => {
        gl.domElement.addEventListener("webglcontextlost", (event) => {
          event.preventDefault();
          lossCount.current += 1;
          if (lossCount.current >= 2) onContextLost();
        });
      }}
    >
      <color attach="background" args={[INK]} />
      <fog attach="fog" args={[0x000000, 16, 38]} />
      <FrameWatchdog
        floorFps={quality === "full" ? 45 : 24}
        onSustainedBreach={onSustainedBreach}
      />
      <ambientLight intensity={ambient} color={WARM_WHITE} />
      <directionalLight position={[8, 16, 6]} intensity={key} color="#fff3dc" />

      {/* The ground far beneath — the district floats above the estate. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.4, 0]}>
        <planeGeometry args={[80, 80]} />
        <meshStandardMaterial color={INK} />
      </mesh>
      <gridHelper args={[80, 80, WARM_WHITE, WARM_WHITE]} position={[0, -1.38, 0]}>
        <meshBasicMaterial
          attach="material"
          color={WARM_WHITE}
          transparent
          opacity={0.07}
        />
      </gridHelper>

      {/* Light beneath sells the float (§13). */}
      <pointLight
        position={[0, -0.4, 0]}
        intensity={1.1}
        color={WARM_WHITE}
        distance={12}
      />

      {/* The plate. */}
      <mesh position={[0, PLATE_Y, 0]}>
        <boxGeometry args={[PLATE_W, PLATE_T, PLATE_D]} />
        <meshStandardMaterial color={SURFACE} />
      </mesh>
      <lineSegments position={[0, PLATE_Y, 0]} geometry={plateEdges}>
        <lineBasicMaterial color={WARM_WHITE} transparent opacity={0.4} />
      </lineSegments>

      {/* Printed on the plate: the district's name, its quarter, the figure. */}
      {titlePlate !== null && (
        <mesh
          position={[-2.6, PLATE_Y + PLATE_T / 2 + 0.012, -2.9]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[7.5, 0.95]} />
          <meshBasicMaterial map={titlePlate} transparent depthWrite={false} />
        </mesh>
      )}
      {quarterPlate !== null && (
        <mesh
          position={[-3.8, 0.012 - 1.39, 5.6]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[5, 0.36]} />
          <meshBasicMaterial map={quarterPlate} transparent depthWrite={false} />
        </mesh>
      )}
      {figurePlate !== null && (
        <mesh
          position={[4.2, PLATE_Y + PLATE_T / 2 + 0.012, -2.7]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[3.4, 1.15]} />
          <meshBasicMaterial map={figurePlate} transparent depthWrite={false} />
        </mesh>
      )}
      {figureSubPlate !== null && (
        <mesh
          position={[4.2, PLATE_Y + PLATE_T / 2 + 0.012, -1.95]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[3.6, 0.3]} />
          <meshBasicMaterial
            map={figureSubPlate}
            transparent
            depthWrite={false}
          />
        </mesh>
      )}

      {district.colleagues.map((colleague, index) => (
        <Workplace
          key={colleague.entity_id}
          colleague={colleague}
          position={colleaguePosition(index, district.colleagues.length)}
          onOpen={() =>
            onOpenDossier({ id: colleague.entity_id, name: colleague.name })
          }
        />
      ))}
    </Canvas>
  );
}
