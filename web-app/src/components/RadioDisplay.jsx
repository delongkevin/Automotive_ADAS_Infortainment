import React from 'react';

/**
 * Radio Display ECU visualization.
 * Pass `state` from /simulate or /test-cases/run (radio_display / radio_display_state).
 */
export default function RadioDisplay({ state = null }) {
  const speed = state?.speed_display?.current_speed_kmh ?? 0;
  const limit = state?.speed_display?.speed_limit_kmh ?? state?.tsr?.speed_limit_kmh;
  const icons = state?.adas_icons || {};

  const tiles = [
    {
      key: 'ACC',
      label: icons.acc_active ? 'Active' : 'Off',
      on: !!icons.acc_active,
      color: '#00e676',
    },
    {
      key: 'LDW',
      label: icons.ldw_active ? 'Warning' : 'Ready',
      on: !!icons.ldw_active,
      color: icons.ldw_active ? '#ffb74d' : '#00d4ff',
    },
    {
      key: 'AEB',
      label: icons.aeb_warning ? 'Warning' : 'Ready',
      on: !!icons.aeb_warning,
      color: icons.aeb_warning ? '#ff5252' : '#00e676',
    },
    {
      key: 'BSD',
      label: icons.bsd_left || icons.bsd_right
        ? `${icons.bsd_left ? 'L' : ''}${icons.bsd_left && icons.bsd_right ? '/' : ''}${icons.bsd_right ? 'R' : ''}`
        : 'Clear',
      on: !!(icons.bsd_left || icons.bsd_right),
      color: '#ffb74d',
    },
    {
      key: 'TSR',
      label: icons.tsr_detected ? (limit != null ? `${limit}` : 'Sign') : '—',
      on: !!icons.tsr_detected,
      color: '#00d4ff',
    },
    {
      key: 'PRK',
      label: icons.parking_active ? 'Active' : 'Ready',
      on: !!icons.parking_active,
      color: '#ce93d8',
    },
  ];

  return (
    <div style={{ background: '#050a10', borderRadius: '8px', padding: '1rem', border: '1px solid rgba(0,212,255,0.2)' }}>
      <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
        <div style={{ fontSize: '2.5rem', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>
          {Number(speed).toFixed(0)}{' '}
          <span style={{ fontSize: '1rem', color: '#7a8fa0' }}>km/h</span>
        </div>
        {limit != null && (
          <div style={{ fontSize: '0.75rem', color: '#00d4ff', marginTop: '0.25rem' }}>
            Limit {limit} km/h
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', marginBottom: '1rem' }}>
        {tiles.map((tile) => (
          <div
            key={tile.key}
            style={{
              textAlign: 'center',
              padding: '0.5rem',
              borderRadius: '4px',
              background: tile.on ? `${tile.color}22` : 'rgba(255,255,255,0.04)',
            }}
          >
            <div style={{ fontSize: '1rem' }}>{tile.key}</div>
            <div style={{ fontSize: '0.65rem', color: tile.on ? tile.color : '#7a8fa0' }}>{tile.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#7a8fa0', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.5rem' }}>
        <span>Radio Display ECU</span>
        <span>{state?.camera_view ? `View: ${state.camera_view}` : '1920x720 @ 60Hz'}</span>
      </div>
    </div>
  );
}
