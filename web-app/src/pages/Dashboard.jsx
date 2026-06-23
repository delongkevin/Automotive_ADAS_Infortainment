import React from 'react';
import VehicleVisualizer from '../components/VehicleVisualizer';
import RadioDisplay from '../components/RadioDisplay';
import CameraView from '../components/CameraView';

export default function Dashboard() {
  return (
    <div>
      <h2 className="page-title">Vehicle ECU Dashboard</h2>
      <p className="page-subtitle">
        Real-time visualization of Radio Display + ADAS Camera ECU simulation
      </p>

      <div className="dashboard-grid">
        <div className="card">
          <div className="card-header">
            <h3>Vehicle Simulation</h3>
            <span className="status-badge running">Live</span>
          </div>
          <VehicleVisualizer />
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Radio Display ECU</h3>
            <div className="ecu-dot" />
          </div>
          <RadioDisplay />
        </div>

        <div className="card">
          <div className="card-header">
            <h3>ADAS Camera System</h3>
            <span className="status-badge pass">Active</span>
          </div>
          <CameraView />
        </div>

        <div className="card">
          <div className="card-header">
            <h3>ECU Status</h3>
          </div>
          <div className="ecu-indicator">
            <div className="ecu-dot" />
            <span>Radio Display ECU — Online</span>
          </div>
          <div className="ecu-indicator">
            <div className="ecu-dot" />
            <span>ADAS Camera ECU — Online</span>
          </div>
          <div className="ecu-indicator">
            <div className="ecu-dot" />
            <span>Vehicle Dynamics ECU — Online</span>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <div className="metric-value">3</div>
            <div className="metric-label">ECUs Connected</div>
          </div>
        </div>
      </div>
    </div>
  );
}
