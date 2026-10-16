import React from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { getDashboard } from '../src/lib/api';

/**
 * Accuracy dashboard.
 *
 * Shows measured performance, including the null result. Every rate is
 * rendered beside its confidence interval and its sample size, because a
 * percentage without a denominator is not information.
 */
export default function Dashboard() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const cats = data?.categories ?? [];
  const supported = data?.categories_supported ?? 0;
  const analysed = data?.categories_analysed ?? 0;

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={
        <RefreshControl refreshing={isRefetching} onRefresh={refetch} />
      }
    >
      <Text style={styles.title}>Accuracy</Text>

      <View style={styles.headline}>
        <Text style={styles.headlineNumber}>{supported}</Text>
        <Text style={styles.headlineLabel}>
          of {analysed} categories show a supported association
        </Text>
      </View>

      <View style={styles.verdict}>
        <Text style={styles.verdictText}>{data?.verdict}</Text>
      </View>

      {data?.sample ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Sample</Text>
          <Text style={styles.cardBody}>{data.sample}</Text>
        </View>
      ) : null}

      {cats.length > 0 && (
        <Text style={styles.section}>Per factor</Text>
      )}

      {cats.map((c: any) => (
        <View key={c.category} style={styles.row}>
          <View style={styles.rowHead}>
            <Text style={styles.factor}>{c.category}</Text>
            <Text
              style={[
                styles.badge,
                c.significant ? styles.badgeGood : styles.badgeNull,
              ]}
            >
              {c.evidence}
            </Text>
          </View>
          <Text style={styles.metric}>
            lift {c.lift.toFixed(2)} · 95% CI [{c.lift_ci[0].toFixed(2)},{' '}
            {c.lift_ci[1].toFixed(2)}]
          </Text>
          <Text style={styles.metricSmall}>
            bootstrap p = {c.p_values.bootstrap.toFixed(3)} · permutation p ={' '}
            {c.p_values.permutation.toFixed(3)} · n = {c.support}
          </Text>
          <Text style={styles.metricSmall}>
            naive p = {c.p_values.naive_not_valid.toFixed(3)} (not valid)
          </Text>
          {c.confound_notes.map((n: string, i: number) => (
            <Text key={i} style={styles.confound}>⚠ {n}</Text>
          ))}
        </View>
      ))}

      <Text style={styles.section}>Method</Text>
      {(data?.method_notes ?? []).map((n: string, i: number) => (
        <Text key={i} style={styles.method}>· {n}</Text>
      ))}

      <Text style={styles.disclaimer}>{data?.disclaimer}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60, backgroundColor: '#faf8f2' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 22, fontWeight: '700', color: '#1a1a1a', marginBottom: 16 },
  headline: {
    backgroundColor: '#fff', borderRadius: 12, padding: 18,
    borderWidth: 1, borderColor: '#e5e5e5', alignItems: 'center',
  },
  headlineNumber: { fontSize: 44, fontWeight: '700', color: '#1f5c3d' },
  headlineLabel: { fontSize: 13, color: '#666', marginTop: 2, textAlign: 'center' },
  verdict: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: '#e5e5e5', marginTop: 12,
  },
  verdictText: { fontSize: 13, color: '#333', lineHeight: 19 },
  card: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: '#e5e5e5', marginTop: 12,
  },
  cardTitle: { fontSize: 12, fontWeight: '700', color: '#1f5c3d', marginBottom: 6 },
  cardBody: { fontSize: 12, color: '#555', lineHeight: 18 },
  section: {
    fontSize: 12, fontWeight: '700', color: '#1f5c3d',
    marginTop: 22, marginBottom: 8, textTransform: 'uppercase',
  },
  row: {
    backgroundColor: '#fff', borderRadius: 10, padding: 13,
    borderWidth: 1, borderColor: '#eee', marginBottom: 8,
  },
  rowHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  factor: { fontSize: 14, fontWeight: '600', color: '#1a1a1a' },
  badge: { fontSize: 10, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, overflow: 'hidden' },
  badgeGood: { backgroundColor: '#d8f0e2', color: '#1f5c3d' },
  badgeNull: { backgroundColor: '#eee', color: '#666' },
  metric: { fontSize: 13, color: '#333', marginTop: 7 },
  metricSmall: { fontSize: 11, color: '#888', marginTop: 2 },
  confound: { fontSize: 11, color: '#8a6d3b', marginTop: 5, lineHeight: 16 },
  method: { fontSize: 12, color: '#666', lineHeight: 18, marginBottom: 6 },
  disclaimer: { marginTop: 22, fontSize: 11, color: '#999', lineHeight: 16, fontStyle: 'italic' },
});