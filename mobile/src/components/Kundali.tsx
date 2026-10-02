/**
 * North Indian chart (kundali) rendered as SVG.
 *
 * The north Indian square is the default in Vedic practice: signs run
 * anticlockwise from the top-left, and the twelve houses are fixed cells
 * rather than sign-anchored segments. That keeps it legible at phone
 * widths, which the south Indian wheel does not.
 *
 * House layout (fixed cells, lagna always in cell 1):
 *
 *     12 |  1 |  2 |  3
 *    ----+---+---+----
 *     11 |  * |  * |  4
 *    ----+---+---+----
 *     10 |  * |  * |  5
 *    ----+---+---+----
 *      9 |  8 |  7 |  6
 *
 * `*` cells carry the lagna and its kendras rather than a house number.
 */
import React from 'react';
import Svg, { G, Line, Polygon, Text as SvgText } from 'react-native-svg';

const SIGN_GLYPHS = [
  '♈', '♉', '♊', '♋', '♌', '♍',
  '♎', '♏', '♐', '♑', '♒', '♓',
];

const GLYPHS: Record<string, string> = {
  sun: '☉', moon: '☽', mars: '♂', mercury: '☿', jupiter: '♃',
  venus: '♀', saturn: '♄', rahu: '☊', ketu: '☋',
};

export const planetGlyph = (name: string) => GLYPHS[name] ?? name;

/** Grid position of each house, as [col, row] with 0-indexed cells. */
const HOUSE_GRID: Record<number, [number, number]> = {
  1: [1, 0], 2: [2, 0], 3: [3, 0],
  4: [3, 1], 5: [3, 2], 6: [3, 3],
  7: [2, 3], 8: [1, 3], 9: [0, 3],
  10: [0, 2], 11: [0, 1], 12: [0, 0],
};

export interface ChartPlanet {
  name: string;
  sign: number;
  house: number;
  retrograde: boolean;
  combust: boolean;
  dignity: string;
}

export interface ChartProps {
  planets: Record<string, ChartPlanet>;
  lagnaSign: number;
  ayanamsha?: string;
  size?: number;
}

const KENDRA_LABEL: Record<number, string> = {
  1: 'lagna', 4: '4th', 7: '7th', 10: '10th',
};

export function Kundali({
  planets,
  lagnaSign,
  ayanamsha = 'Lahiri',
  size = 300,
}: ChartProps) {
  const byHouse: Record<number, ChartPlanet[]> = {};
  for (const p of Object.values(planets)) {
    (byHouse[p.house] ??= []).push(p);
  }

  const cell = 62;
  const gap = 2;
  const total = 4 * cell + 3 * gap;
  const ox = 8;
  const oy = 8;

  const lines: React.ReactElement[] = [];
  for (let i = 0; i < 4; i++) {
    const p = i * (cell + gap);
    lines.push(
      <Line
        key={`h${i}`}
        x1={ox}
        y1={oy + p}
        x2={ox + total}
        y2={oy + p}
        stroke="#c8c8c8"
        strokeWidth={1}
      />,
      <Line
        key={`v${i}`}
        x1={ox + p}
        y1={oy}
        x2={ox + p}
        y2={oy + total}
        stroke="#c8c8c8"
        strokeWidth={1}
      />,
    );
  }

  const houses: React.ReactElement[] = [];
  for (const [houseStr, [col, row]] of Object.entries(HOUSE_GRID)) {
    const house = Number(houseStr);
    const sign = (lagnaSign + house - 1) % 12;
    const x = ox + col * (cell + gap);
    const y = oy + row * (cell + gap);
    const inCell = byHouse[house] ?? [];
    const isKendra = KENDRA_LABEL[house] !== undefined;

    houses.push(
      <G key={house}>
        <Polygon
          points={`${x},${y} ${x + cell},${y} ${x + cell},${y + cell} ${x},${y + cell}`}
          fill={house === 1 ? '#f0f7f2' : '#fffdf7'}
          stroke="#d0d0d0"
          strokeWidth={1}
        />
        <SvgText
          x={x + 4}
          y={y + 13}
          fontSize={13}
          fill={house === 1 ? '#1f5c3d' : '#8d8d8d'}
        >
          {SIGN_GLYPHS[sign]}
        </SvgText>
        <SvgText x={x + cell - 15} y={y + 12} fontSize={8} fill="#b0b0b0">
          {isKendra ? KENDRA_LABEL[house] : house}
        </SvgText>
        {inCell.map((p, i) => (
          <SvgText
            key={p.name}
            x={x + 5}
            y={y + 29 + i * 13}
            fontSize={13}
            fill={p.combust ? '#b06a2c' : '#1a1a1a'}
          >
            {planetGlyph(p.name)}
            {p.retrograde ? '℞' : ''}
          </SvgText>
        ))}
      </G>,
    );
  }

  return (
    <Svg width={size} height={size + 14} viewBox={`0 0 ${total + 16} ${total + 30}`}>
      <Polygon
        points={`${ox},${oy} ${ox + total},${oy} ${ox + total},${oy + total} ${ox},${oy + total}`}
        fill="none"
        stroke="#2b2b2b"
        strokeWidth={2.5}
      />
      {lines}
      {houses}
      <SvgText x={ox} y={oy + total + 16} fontSize={9} fill="#666">
        {`sidereal · ${ayanamsha} ayanamsha · whole sign`}
      </SvgText>
    </Svg>
  );
}
