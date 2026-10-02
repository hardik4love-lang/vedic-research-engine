import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Kundali, planetGlyph } from '../src/components/Kundali';
import { getConfig, getProfile } from '../src/lib/api';

const SIGNS = [
  'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
  'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces',
];

const LORDS = [
  'mars', 'venus', 'mercury', 'moon', 'sun', 'mercury',
  'venus', 'mars', 'jupiter', 'saturn', 'saturn', 'jupiter',
];

export default function ChartScreen() {
  const { profileId } = useLocalSearchParams<{ profileId: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['profile', profileId],
    queryFn: () => getProfile(profileId!),
  });
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
        <Text style={styles.loading}>Computing chart…</Text>
      </View>
    );
  }
  if (error || !data?.chart) {
    return (
      <View style={styles.center}>
        <Text style={styles.error}>Could not load chart</Text>
        <Text style={styles.errorDetail}>{String((error as any)?.message ?? error)}</Text>
      </View>
    );
  }

  const chart = data.chart;
  const lagnaSign = chart.lagna.sign;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>{data.profile.name ?? 'Chart'}</Text>
      <Text style={styles.subtitle}>
        {data.profile.birth_date} {data.profile.birth_time}{' '}
        {data.profile.city} · {data.profile.timezone}
      </Text>

      <View style={styles.chartWrap}>
        <Kundali
          planets={chart.planets}
          lagnaSign={lagnaSign}
          ayanamsha={chart.ayanamsha ?? config?.ayanamsha ?? 'Lahiri'}
        />
      </View>

      <Text style={styles.lagna}>
        Lagna: {chart.lagna.sign_name} · {chart.lagna.degree.toFixed(2)}°
      </Text>

      <Section title="Planets">
        {Object.entries(chart.planets).map(([name, p]: [string, any]) => (
          <View key={name} style={styles.row}>
            <Text style={styles.glyph}>{planetGlyph(name)}</Text>
            <Text style={styles.planetName}>{name}</Text>
            <Text style={styles.value}>
              {p.sign_name} {p.degree.toFixed(1)}° · H{p.house}
              {p.retrograde ? ' · ℞' : ''}
              {p.combust ? ' · combust' : ''}
            </Text>
            <Text style={styles.dignity}>{p.dignity}</Text>
          </View>
        ))}
      </Section>

      <Section title="Houses">
        {chart.houses.map((h: any) => (
          <View key={h.number} style={styles.row}>
            <Text style={styles.planetName}>H{h.number}</Text>
            <Text style={styles.value}>
              {h.sign_name} · lord {h.lord}
            </Text>
            <Text style={styles.dignity}>
              {h.planets.length ? h.planets.join(', ') : '—'}
            </Text>
          </View>
        ))}
      </Section>

      <Section title="Vimshottari dasha">
        {chart.dasha.map((d: any, i: number) => (
          <View key={i} style={styles.dashaRow}>
            <Text style={styles.dashaLord}>{planetGlyph(d.lord)} {d.lord}</Text>
            <Text style={styles.dashaDates}>
              {d.start?.slice(0, 10)} → {d.end?.slice(0, 10)}
            </Text>
            {d.sub_periods?.slice(0, 3).map((s: any, j: number) => (
              <Text key={j} style={styles.subDasha}>
                　{planetGlyph(s.lord)} {s.lord} {s.start?.slice(0, 7)}
              </Text>
            ))}
          </View>
        ))}
      </Section>

      <Section title="Divisional charts">
        {Object.entries(chart.divisional_charts).map(([name, dc]: [string, any]) => (
          <View key={name} style={styles.row}>
            <Text style={styles.planetName}>{name}</Text>
            <Text style={styles.value}>lagna {SIGNS[dc.lagna_sign]}</Text>
            <Text style={styles.dignity}>
              {Object.values(dc.planets as Record<string, any>)
                .map((p) => SIGNS[p.sign].slice(0, 3))
                .join(' ')}
            </Text>
          </View>
        ))}
      </Section>

      {chart.yogas?.length > 0 && (
        <Section title="Yogas detected">
          {chart.yogas.map((y: any, i: number) => (
            <View key={i} style={styles.row}>
              <Text style={styles.planetName}>{y.name}</Text>
              <Text style={styles.value}>{y.description}</Text>
            </View>
          ))}
        </Section>
      )}

      <Text style={styles.disclaimer}>
        Computed with the {config?.ayanamsha ?? 'Lahiri'} ayanamsha and whole-sign
        houses. Changing any convention invalidates stored results, so the
        configuration is stored with every chart.
      </Text>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60, backgroundColor: '#faf8f2' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#faf8f2' },
  loading: { marginTop: 12, color: '#666' },
  error: { color: '#a33', fontSize: 16, fontWeight: '600' },
  errorDetail: { color: '#888', fontSize: 12, marginTop: 8, paddingHorizontal: 30, textAlign: 'center' },
  title: { fontSize: 22, fontWeight: '700', color: '#1a1a1a' },
  subtitle: { fontSize: 12, color: '#777', marginTop: 2, marginBottom: 12 },
  chartWrap: { alignItems: 'center', backgroundColor: '#fffdf7', borderRadius: 12, padding: 8 },
  lagna: { fontSize: 15, fontWeight: '600', color: '#1f5c3d', marginTop: 10, marginBottom: 4, textAlign: 'center' },
  section: { marginTop: 20 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#1f5c3d', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 0.5, borderBottomColor: '#e8e8e8' },
  glyph: { width: 22, fontSize: 16, color: '#333' },
  planetName: { width: 82, fontSize: 13, color: '#333', fontWeight: '600' },
  value: { flex: 1, fontSize: 12, color: '#555' },
  dignity: { fontSize: 10, color: '#999', width: 78, textAlign: 'right' },
  dashaRow: { paddingVertical: 6, borderBottomWidth: 0.5, borderBottomColor: '#e8e8e8' },
  dashaLord: { fontSize: 14, fontWeight: '600', color: '#333' },
  dashaDates: { fontSize: 11, color: '#888' },
  subDasha: { fontSize: 11, color: '#666' },
  disclaimer: { marginTop: 28, fontSize: 11, color: '#999', lineHeight: 16, fontStyle: 'italic' },
});
