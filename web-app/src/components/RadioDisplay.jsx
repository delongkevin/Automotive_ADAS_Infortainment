import React from 'react';

export default function RadioDisplay() {
  return (
    <div style={{ background: '#050a10', borderRadius: '8px', padding: '1rem', border: '1px solid rgba(0,212,255,0.2)' }}>
      {/* Speed display */}
      <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
        <div style={{ fontSize: '2.5rem', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>
          0 <span style={{ fontSize: '1rem', color: '#7a8fa0' }}>km/h</span>
        </div>
      </div>

      {/* ADAS Icons */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', marginBottom: '1rem' }}>
        <div style={{ textAlign: 'center', padding: '0.5rem', borderRadius: '4px', background: 'rgba(0,230,118,0.1)' }}>
          <div style={{ fontSize: '1.2rem' }}>ACC</div>
          <div style={{ fontSize: '0.65rem', color: '#00e676' }}>Active</div>
        </div>
        <div style={{ textAlign: 'center', padding: '0.5rem', borderRadius: '4px', background: 'rgba(0,212,255,0.1)' }}>
          <div style={{ fontSize: '1.2rem' }}>LDW</div>
          <div style={{ fontSize: '0.65rem', color: '#00d4ff' }}>Ready</div>
        </div>
        <div style={{ textAlign: 'center', padding: '0.5rem', borderRadius: '4px', background: 'rgba(0,230,118,0.1)' }}>
          <div style={{ fontSize: '1.2rem' }}>AEB</div>
          <div style={{ fontSize: '0.65rem', color: '#00e676' }}>Ready</div>
        </div>
      </div>

      {/* Status bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#7a8fa0', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.5rem' }}>
        <span>Radio Display ECU</span>
        <span>1920x720 @ 60Hz</span>
      </div>
    </div>
  );
}
