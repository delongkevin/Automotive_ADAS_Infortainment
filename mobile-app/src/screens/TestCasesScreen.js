import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { getApiBaseUrl } from '../config/api';

const API_BASE = getApiBaseUrl();

export default function TestCasesScreen() {
  const [testCases, setTestCases] = useState([]);
  const [results, setResults] = useState({});
  const [lastTestId, setLastTestId] = useState(null);
  const [running, setRunning] = useState(null);
  const [listError, setListError] = useState(null);

  useEffect(() => {
    const loadCases = async () => {
      try {
        const res = await fetch(`${API_BASE}/test-cases`);
        if (!res.ok) {
          throw new Error(`Catalog request failed (${res.status})`);
        }
        const data = await res.json();
        setTestCases(data.test_cases || []);
      } catch (error) {
        setListError(error.message || 'Failed to load test catalog');
      }
    };

    loadCases();
  }, []);

  const runTest = async (tc) => {
    setRunning(tc.id);
    try {
      const res = await fetch(`${API_BASE}/test-cases/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          test_id: tc.id,
          scenario: tc.scenario,
          duration: tc.default_duration || 8.0,
          adas_features: tc.adas_features || ['ldw', 'acc', 'aeb'],
        }),
      });
      if (!res.ok) {
        throw new Error(`Test request failed (${res.status})`);
      }
      const data = await res.json();
      setResults((prev) => ({ ...prev, [tc.id]: data }));
      setLastTestId(tc.id);
    } catch (error) {
      setResults((prev) => ({ ...prev, [tc.id]: { status: 'ERROR', error: error.message } }));
      setLastTestId(tc.id);
    }
    setRunning(null);
  };

  const runAll = async () => {
    for (const tc of testCases) {
      await runTest(tc);
    }
  };

  const passCount = Object.values(results).filter((r) => r.status === 'PASS').length;
  const totalRun = Object.keys(results).length;
  const lastResult = lastTestId ? results[lastTestId] : null;
  const lastChecks = lastResult?.validation?.checks || [];

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Test Cases</Text>
          <Text style={styles.subtitle}>Radio Display + ADAS Camera ECU Tests</Text>
        </View>
        <TouchableOpacity style={styles.btnPrimary} onPress={runAll}>
          <Text style={styles.btnText}>Run All</Text>
        </TouchableOpacity>
      </View>

      {totalRun > 0 && (
        <View style={styles.summaryCard}>
          <Text style={styles.summaryValue}>{passCount}/{totalRun}</Text>
          <Text style={styles.summaryLabel}>Tests Passed</Text>
        </View>
      )}

      {listError && (
        <View style={styles.summaryCard}>
          <Text style={{ color: '#ff8a80', fontSize: 12 }}>{listError}</Text>
        </View>
      )}

      {testCases.map((tc) => (
        <View key={tc.id} style={styles.testItem}>
          <View style={{ flex: 1 }}>
            <Text style={styles.testName}>{tc.name}</Text>
            <Text style={styles.testMeta}>{tc.ecu} | {tc.scenario}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {results[tc.id] && (
              <View style={[styles.badge, results[tc.id].status === 'PASS' ? styles.badgePass : styles.badgeFail]}>
                <Text style={[styles.badgeText, results[tc.id].status === 'PASS' ? { color: '#00e676' } : { color: '#ff5252' }]}>
                  {results[tc.id].status}
                </Text>
              </View>
            )}
            {running === tc.id ? (
              <ActivityIndicator size="small" color="#00d4ff" />
            ) : (
              <TouchableOpacity style={styles.btnOutline} onPress={() => runTest(tc)}>
                <Text style={styles.btnOutlineText}>Run</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      ))}

      {lastChecks.length > 0 && (
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Latest Validation Checks</Text>
          {lastChecks.map((check) => (
            <View key={check.name} style={{ marginTop: 6 }}>
              <Text style={{ color: check.passed ? '#00e676' : '#ff5252', fontSize: 11, fontWeight: '700' }}>
                {check.passed ? 'PASS' : 'FAIL'} {check.name}
              </Text>
              <Text style={{ color: '#7a8fa0', fontSize: 10 }}>
                expected {check.expected} | actual {check.actual}
              </Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f1923', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 },
  title: { fontSize: 20, fontWeight: '700', color: '#e0e8f0' },
  subtitle: { fontSize: 12, color: '#7a8fa0', marginTop: 2 },
  summaryCard: { backgroundColor: '#1a2733', borderRadius: 8, padding: 16, marginBottom: 16, alignItems: 'center' },
  summaryValue: { fontSize: 32, fontWeight: '700', color: '#00d4ff' },
  summaryLabel: { fontSize: 12, color: '#7a8fa0' },
  testItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.04)' },
  testName: { fontSize: 14, color: '#e0e8f0' },
  testMeta: { fontSize: 11, color: '#7a8fa0', marginTop: 2 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 100 },
  badgePass: { backgroundColor: 'rgba(0,230,118,0.15)' },
  badgeFail: { backgroundColor: 'rgba(255,82,82,0.15)' },
  badgeText: { fontSize: 10, fontWeight: '700' },
  btnPrimary: { backgroundColor: '#00d4ff', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  btnText: { color: '#0f1923', fontSize: 13, fontWeight: '600' },
  btnOutline: { borderWidth: 1, borderColor: '#00d4ff', paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6 },
  btnOutlineText: { color: '#00d4ff', fontSize: 11, fontWeight: '600' },
});
