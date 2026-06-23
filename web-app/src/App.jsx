import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import TestCases from './pages/TestCases';
import Simulation from './pages/Simulation';

export default function App() {
  return (
    <>
      <header className="app-header">
        <h1>ADAS + Infotainment Simulation</h1>
        <nav className="nav-links">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/test-cases">Test Cases</NavLink>
          <NavLink to="/simulation">Simulation</NavLink>
        </nav>
      </header>
      <main className="page-container">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/test-cases" element={<TestCases />} />
          <Route path="/simulation" element={<Simulation />} />
        </Routes>
      </main>
    </>
  );
}
