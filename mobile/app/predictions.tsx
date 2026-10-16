import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { getDashboard } from '../src/lib/api';

export default function Predictions() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
  });

  if (isLoading) return <Text style={styles.p}>Loading…</Text>;

  const supported = data?.categories_supported ?? 0;
  const analysed = data?.categories_analysed ?? 0;
  const canPredict = supported > 0;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Predictions</Text>

      <View style={styles.verdictCard}>
        <Text style={styles.verdictHead}>
          {canPredict ? 'Predictions available' : 'No predictions available'}
        </Text>
        <Text style={styles.verdictBody}>{data?.verdict}</Text>
      </View>

      {!canPredict && (
        <View style={styles.why}>
          <Text style={styles.whyTitle}>What would unlock this</Text>
          <Text style={styles.whyBody}>
            A prediction needs a rule set trained on a cohort and then scored
            on outcomes the model never saw. Both exist in the system; neither
            has enough data behind it.
          </Text>
          <Text style={styles.whyBody}>
            Specifically: the protocol needs at least five dated events per
            subject, and the largest public dataset of documented life events
            with verified birth times averages 1.1. Widening from one
            category to nine makes the shortfall worse, not better.
          </Text>
          <Text style={styles.whyBody}>
            Showing windows anyway would be indistinguishable from a real
            forecast, which is exactly why it is not done.
          </Text>
        </View>
      )}

      <View style={styles.statsCard}>
        <Text style={styles.statsTitle}>Current state</Text>
        <Stat label="Categories analysed" value={String(analysed)} />
        <Stat label="Categories supported" value={String(supported)} />
        <Stat
          label="Can predict?"
          value={canPredict ? 'yes' : 'no'}
        />
      </View>

      {(data?.method_notes ?? []).map((n: string, i: number) => (
        <Text key={i} style={styles.method}>· {n}</Text>
      ))}

      <Text style={styles.disclaimer}>{data?.disclaimer}</Text>
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60, backgroundColor: '#faf8f2' },
  p: { padding: 20, color: '#666' },
  title: { fontSize: 22, fontWeight: '700', color: '#1a1a1a', marginBottom: 16 },
  verdictCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: '#e5e5e5', marginBottom: 16,
  },
  verdictHead: { fontSize: 15, fontWeight: '700', color: '#1a1a1a', marginBottom: 8 },
  verdictBody: { fontSize: 13, color: '#555', lineHeight: 19 },
  why: {
    backgroundColor: '#fff8ec', borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: '#e8d9b0', marginBottom: 16,
  },
  whyTitle: { fontSize: 13, fontWeight: '700', color: '#8a6d3b', marginBottom: 8 },
  whyBody: { fontSize: 13, color: '#7a6440', lineHeight: 19, marginBottom: 8 },
  statsCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: '#e5e5e5', marginBottom: 16,
  },
  statsTitle: { fontSize: 12, fontWeight: '700', color: '#1f5c3d', marginBottom: 10 },
  statRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  statLabel: { fontSize: 13, color: '#555' },
  statValue: { fontSize: 14, fontWeight: '700', color: '#1a1a1a' },
  method: { fontSize: 12, color: '#666', lineHeight: 18, marginBottom: 6 },
  disclaimer: { marginTop: 20, fontSize: 11, color: '#999', lineHeight: 16, fontStyle: 'italic' },
});
