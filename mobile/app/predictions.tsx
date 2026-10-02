import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getAnalysis } from '../src/lib/api';

export default function Predictions() {
  const { profileId } = useLocalSearchParams<{ profileId: string }>();
  const { data, isLoading } = useQuery({
    queryKey: ['analysis', profileId],
    queryFn: () => getAnalysis(profileId!),
  });

  if (isLoading) return <Text style={styles.p}>Loading…</Text>;

  const total = data?.summary?.total_events ?? 0;
  const usable = data?.summary?.usable_events ?? 0;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Predictions</Text>

      <View style={styles.honesty}>
        <Text style={styles.honestyTitle}>No predictions available</Text>
        <Text style={styles.honestyBody}>
          This build does not generate predictions, and that is deliberate.
        </Text>
        <Text style={styles.honestyBody}>
          Predictions require a rule set trained on a cohort of people and then
          tested out-of-sample against outcomes the model never saw. That
          backtest has not been run on sufficient data: the largest public
          dataset of documented life events with verified birth times averages
          about one event per person, and the protocol needs at least five.
        </Text>
        <Text style={styles.honestyBody}>
          Showing plausible-looking windows here would be indistinguishable
          from the real thing, which is exactly why it is not done.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>What your data supports so far</Text>
        <Text style={styles.stat}>
          <Text style={styles.statValue}>{total}</Text> documented events
        </Text>
        <Text style={styles.stat}>
          <Text style={styles.statValue}>{usable}</Text> usable for timing analysis
        </Text>
        <Text style={styles.stat}>
          <Text style={styles.statValue}>{data?.summary?.meets_m3_benchmark ? 'yes' : 'no'}</Text>
          {' '}meets the 10-events benchmark
        </Text>
      </View>

      <Text style={styles.sectionTitle}>Events by category</Text>
      {Object.entries(data?.events_by_category ?? {}).map(([cat, n]) => (
        <View key={cat} style={styles.row}>
          <Text style={styles.rowLabel}>{cat}</Text>
          <Text style={styles.rowValue}>{String(n)}</Text>
        </View>
      ))}

      <Text style={styles.sectionTitle}>Date precision</Text>
      {Object.entries(data?.precision_breakdown ?? {}).map(([p, n]) => (
        <View key={p} style={styles.row}>
          <Text style={styles.rowLabel}>{p}</Text>
          <Text style={styles.rowValue}>{String(n)}</Text>
        </View>
      ))}

      <Text style={styles.disclaimer}>{data?.caveat}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60, backgroundColor: '#faf8f2' },
  p: { padding: 20, color: '#666' },
  title: { fontSize: 22, fontWeight: '700', color: '#1a1a1a', marginBottom: 16 },
  honesty: { backgroundColor: '#fff', borderRadius: 12, padding: 16, borderWidth: 1, borderColor: '#e0e0e0', marginBottom: 20 },
  honestyTitle: { fontSize: 15, fontWeight: '700', color: '#1a1a1a', marginBottom: 8 },
  honestyBody: { fontSize: 13, color: '#555', lineHeight: 19, marginBottom: 8 },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 16, borderWidth: 1, borderColor: '#e0e0e0', marginBottom: 20 },
  cardTitle: { fontSize: 13, fontWeight: '700', color: '#1f5c3d', marginBottom: 10 },
  stat: { fontSize: 14, color: '#555', marginBottom: 4 },
  statValue: { fontSize: 18, fontWeight: '700', color: '#1a1a1a' },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#1f5c3d', marginBottom: 8, textTransform: 'uppercase' },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 7, borderBottomWidth: 0.5, borderBottomColor: '#eee' },
  rowLabel: { fontSize: 13, color: '#444' },
  rowValue: { fontSize: 13, fontWeight: '600', color: '#333' },
  disclaimer: { marginTop: 24, fontSize: 11, color: '#999', lineHeight: 16, fontStyle: 'italic' },
});
