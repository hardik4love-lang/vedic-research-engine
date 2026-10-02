import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { flushOutbox, getConfig, pendingEventCount } from '../src/lib/api';
import { useEffect, useState } from 'react';

export default function Index() {
  const router = useRouter();
  const [pending, setPending] = useState(0);
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig });

  useEffect(() => {
    // Retry any events that failed to send on a previous run.
    flushOutbox().then(() => pendingEventCount().then(setPending));
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Vedic Chart</Text>
      <Text style={styles.tagline}>
        Sidereal charts with the calculation conventions shown and stored.
      </Text>

      <MenuCard
        title="Create a profile"
        body="Enter birth data and compute a natal chart."
        onPress={() => router.push('/create-profile')}
      />
      <MenuCard
        title="Add past events"
        body="Record dated life events with their actual precision."
        onPress={() => router.push({ pathname: '/add-event', params: {} })}
      />
      <MenuCard
        title="Predictions"
        body="What the model can and cannot currently tell you."
        onPress={() => router.push({ pathname: '/predictions', params: {} })}
      />

      {pending > 0 && (
        <View style={styles.pending}>
          <Text style={styles.pendingText}>
            {pending} event{pending > 1 ? 's' : ''} waiting to sync
          </Text>
        </View>
      )}

      <View style={styles.config}>
        <Text style={styles.configTitle}>Calculation conventions</Text>
        {config && (
          <>
            <ConfigRow label="Ayanamsha" value={config.ayanamsha} />
            <ConfigRow label="House system" value={config.house_system} />
            <ConfigRow label="Vargas" value={config.divisional_charts?.join(', ')} />
            <ConfigRow label="Dasha" value={config.dasha_system} />
            <Text style={styles.configNote}>{config.note}</Text>
          </>
        )}
      </View>

      <Pressable style={styles.link} onPress={() => router.push('/create-profile')}>
        <Text style={styles.linkText}>Get started →</Text>
      </Pressable>
    </ScrollView>
  );
}

function MenuCard({ title, body, onPress }: { title: string; body: string; onPress: () => void }) {
  return (
    <Pressable style={styles.card} onPress={onPress}>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardBody}>{body}</Text>
    </Pressable>
  );
}

function ConfigRow({ label, value }: { label: string; value?: string }) {
  return (
    <View style={styles.configRow}>
      <Text style={styles.configLabel}>{label}</Text>
      <Text style={styles.configValue}>{value ?? '—'}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingBottom: 60, backgroundColor: '#faf8f2' },
  title: { fontSize: 28, fontWeight: '700', color: '#1a1a1a' },
  tagline: { fontSize: 14, color: '#666', marginTop: 4, marginBottom: 24, lineHeight: 20 },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#e5e5e5' },
  cardTitle: { fontSize: 16, fontWeight: '600', color: '#1f5c3d' },
  cardBody: { fontSize: 13, color: '#666', marginTop: 3, lineHeight: 18 },
  pending: { backgroundColor: '#fff4e0', borderRadius: 8, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: '#e8c98a' },
  pendingText: { color: '#8a6d3b', fontSize: 13, fontWeight: '600' },
  config: { backgroundColor: '#fff', borderRadius: 12, padding: 16, borderWidth: 1, borderColor: '#e5e5e5', marginTop: 12 },
  configTitle: { fontSize: 12, fontWeight: '700', color: '#1f5c3d', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  configRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  configLabel: { fontSize: 13, color: '#666' },
  configValue: { fontSize: 13, color: '#333', fontWeight: '600' },
  configNote: { fontSize: 11, color: '#999', marginTop: 10, lineHeight: 16, fontStyle: 'italic' },
  link: { marginTop: 24, alignItems: 'center' },
  linkText: { color: '#1f5c3d', fontSize: 15, fontWeight: '600' },
});
