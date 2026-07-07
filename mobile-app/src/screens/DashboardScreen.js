import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import Svg, { Rect, Circle, Line, G, Text as SvgText } from 'react-native-svg';

export default function DashboardScreen() {
  const [ecuStatus, setEcuStatus] = useState({
    radioDisplay: true,
    adasCamera: true,
    vehicleDynamics: true,
  });

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Vehicle ECU Dashboard</Text>
      <Text style={styles.subtitle}>Radio Display + ADAS Camera ECU Simulation</Text>

      {/* Vehicle Visualization */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Vehicle Simulation</Text>
        <View style={styles.vehicleCanvas}>
          <Svg width="100%" height="200" viewBox="0 0 400 200">
            <Rect x="0" y="70" width="400" height="60" fill="#1a2a3a" />
            <Line x1="0" y1="100" x2="400" y2="100" stroke="#334455" strokeWidth="1" strokeDasharray="15 8" />
            <G transform="translate(80, 80)">
              <Rect x="0" y="5" width="50" height="25" rx="4" fill="#2196F3" stroke="#64B5F6" strokeWidth="1" />
              <Circle cx="52" cy="17" r="3" fill="#00d4ff" opacity="0.8" />
            </G>
            <SvgText x="200" y="170" textAnchor="middle" fill="#7a8fa0" fontSize="10">
              Awaiting simulation...
            </SvgText>
          </Svg>
        </View>
      </View>

      {/* ECU Status */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ECU Status</Text>
        {Object.entries(ecuStatus).map(([key, online]) => (
          <View key={key} style={styles.ecuRow}>
            <View style={[styles.ecuDot, { backgroundColor: online ? '#00e676' : '#ff5252' }]} />
            <Text style={styles.ecuText}>
              {key === 'radioDisplay' ? 'Radio Display ECU' :
               key === 'adasCamera' ? 'ADAS Camera ECU' : 'Vehicle Dynamics ECU'}
              {' — '}{online ? 'Online' : 'Offline'}
            </Text>
          </View>
        ))}
      </View>

      {/* Radio Display Preview */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Radio Display</Text>
        <View style={styles.radioDisplay}>
          <Text style={styles.speedValue}>0</Text>
          <Text style={styles.speedUnit}>km/h</Text>
          <View style={styles.adasIcons}>
            <View style={styles.adasIcon}>
              <Text style={styles.adasIconText}>ACC</Text>
              <Text style={[styles.adasStatus, { color: '#00e676' }]}>Active</Text>
            </View>
            <View style={styles.adasIcon}>
              <Text style={styles.adasIconText}>LDW</Text>
              <Text style={[styles.adasStatus, { color: '#00d4ff' }]}>Ready</Text>
            </View>
            <View style={styles.adasIcon}>
              <Text style={styles.adasIconText}>AEB</Text>
              <Text style={[styles.adasStatus, { color: '#00e676' }]}>Ready</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Camera Grid */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ADAS Camera System</Text>
        <View style={styles.cameraGrid}>
          {['Front', 'Rear', 'Left', 'Right'].map((cam) => (
            <View key={cam} style={styles.cameraFeed}>
              <Text style={styles.cameraLabel}>{cam}</Text>
              <View style={styles.recordingDot} />
            </View>
          ))}
        </View>
        <Text style={styles.footnote}>5 cameras active | Object detection: ON</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f1923', padding: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#e0e8f0', marginBottom: 4 },
  subtitle: { fontSize: 13, color: '#7a8fa0', marginBottom: 20 },
  card: { backgroundColor: '#1a2733', borderRadius: 8, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)' },
  cardTitle: { fontSize: 12, color: '#7a8fa0', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 12 },
  vehicleCanvas: { backgroundColor: '#0a1520', borderRadius: 8, overflow: 'hidden' },
  ecuRow: { flexDirection: 'row', alignItems: 'center', padding: 8, backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 6, marginBottom: 6 },
  ecuDot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
  ecuText: { color: '#e0e8f0', fontSize: 13 },
  radioDisplay: { backgroundColor: '#050a10', borderRadius: 8, padding: 16, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(0,212,255,0.2)' },
  speedValue: { fontSize: 48, fontWeight: '700', color: '#fff', fontFamily: 'monospace' },
  speedUnit: { fontSize: 14, color: '#7a8fa0', marginBottom: 16 },
  adasIcons: { flexDirection: 'row', gap: 12 },
  adasIcon: { alignItems: 'center', padding: 8, borderRadius: 6, backgroundColor: 'rgba(0,230,118,0.08)', minWidth: 60 },
  adasIconText: { fontSize: 14, color: '#e0e8f0', fontWeight: '600' },
  adasStatus: { fontSize: 9, marginTop: 2 },
  cameraGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  cameraFeed: { width: '48%', aspectRatio: 16 / 9, backgroundColor: '#050a10', borderRadius: 4, borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)', justifyContent: 'center', alignItems: 'center', position: 'relative' },
  cameraLabel: { color: '#7a8fa0', fontSize: 10 },
  recordingDot: { position: 'absolute', top: 4, right: 4, width: 6, height: 6, borderRadius: 3, backgroundColor: '#ff5252' },
  footnote: { fontSize: 10, color: '#7a8fa0', marginTop: 8 },
});
