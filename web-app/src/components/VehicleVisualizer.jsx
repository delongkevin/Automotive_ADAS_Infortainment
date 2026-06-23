import React from 'react';

export default function VehicleVisualizer({ trace }) {
  const points = trace || [];
  const maxSpeed = Math.max(...points.map((p) => p?.speed_kmh || 0), 1);

  return (
    <div className="vehicle-canvas">
      <svg width="100%" height="100%" viewBox="0 0 500 280" preserveAspectRatio="xMidYMid meet">
        {/* Road */}
        <rect x="0" y="100" width="500" height="80" fill="#1a2a3a" />
        <line x1="0" y1="140" x2="500" y2="140" stroke="#334455" strokeWidth="1" strokeDasharray="20 10" />

        {/* Vehicle body */}
        <g transform="translate(100, 120)">
          {/* Car body */}
          <rect x="0" y="5" width="60" height="30" rx="5" fill="#2196F3" stroke="#64B5F6" strokeWidth="1" />
          {/* Windshield */}
          <polygon points="45,8 55,14 55,26 45,32" fill="#1565C0" />
          {/* Front camera indicator */}
          <circle cx="62" cy="20" r="3" fill="#00d4ff">
            <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
          </circle>
          {/* Wheels */}
          <rect x="8" y="0" width="12" height="5" rx="2" fill="#333" />
          <rect x="8" y="35" width="12" height="5" rx="2" fill="#333" />
          <rect x="38" y="0" width="12" height="5" rx="2" fill="#333" />
          <rect x="38" y="35" width="12" height="5" rx="2" fill="#333" />
          {/* Radar beam */}
          <path d="M 62 20 L 120 5 L 120 35 Z" fill="rgba(0, 212, 255, 0.08)" stroke="rgba(0, 212, 255, 0.3)" strokeWidth="0.5" />
        </g>

        {/* Speed trace chart */}
        {points.length > 1 && (
          <g transform="translate(0, 200)">
            <text x="10" y="10" fill="#7a8fa0" fontSize="8">Speed</text>
            <polyline
              fill="none"
              stroke="#00d4ff"
              strokeWidth="1.5"
              points={points.map((pt, i) => {
                const x = 10 + (i / points.length) * 480;
                const y = 70 - (pt.speed_kmh / maxSpeed) * 60;
                return `${x},${y}`;
              }).join(' ')}
            />
          </g>
        )}

        {/* Labels */}
        <text x="250" y="270" textAnchor="middle" fill="#7a8fa0" fontSize="9">
          {points.length > 0
            ? `Speed: ${points[points.length - 1]?.speed_kmh?.toFixed(0)} km/h`
            : 'Awaiting simulation data...'
          }
        </text>
      </svg>
    </div>
  );
}
