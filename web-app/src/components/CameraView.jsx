import React from 'react';

export default function CameraView() {
  const cameras = [
    { name: 'Front', status: 'active' },
    { name: 'Rear', status: 'active' },
    { name: 'Left', status: 'active' },
    { name: 'Right', status: 'active' },
  ];

  return (
    <div>
      <div className="camera-grid">
        {cameras.map((cam) => (
          <div key={cam.name} className="camera-feed">
            <svg width="100%" height="100%" viewBox="0 0 160 90">
              {/* Simulated camera feed visualization */}
              <rect width="160" height="90" fill="#050a10" />
              {/* Road lines */}
              {cam.name === 'Front' && (
                <g>
                  <line x1="40" y1="90" x2="70" y2="40" stroke="#334" strokeWidth="1" />
                  <line x1="120" y1="90" x2="90" y2="40" stroke="#334" strokeWidth="1" />
                  <line x1="70" y1="40" x2="75" y2="30" stroke="#334" strokeWidth="0.5" strokeDasharray="3 2" />
                  <line x1="90" y1="40" x2="85" y2="30" stroke="#334" strokeWidth="0.5" strokeDasharray="3 2" />
                  {/* Detection box */}
                  <rect x="65" y="35" width="30" height="20" fill="none" stroke="#00d4ff" strokeWidth="0.5" />
                  <text x="80" y="60" textAnchor="middle" fill="#00d4ff" fontSize="5">Vehicle</text>
                </g>
              )}
              {cam.name === 'Rear' && (
                <g>
                  <line x1="30" y1="0" x2="60" y2="90" stroke="#334" strokeWidth="1" />
                  <line x1="130" y1="0" x2="100" y2="90" stroke="#334" strokeWidth="1" />
                </g>
              )}
              <text x="80" y="85" textAnchor="middle" fill="#7a8fa0" fontSize="7">{cam.name} Camera</text>
            </svg>
          </div>
        ))}
      </div>
      <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#7a8fa0' }}>
        <span>5 cameras active</span>
        <span>Object detection: ON</span>
      </div>
    </div>
  );
}
