import React, { useState } from 'react';
import {
  Alert, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  addEvent, flushOutbox, getTimeline, getTaxonomy, pendingEventCount,
  type Precision,
} from '../src/lib/api';

const IMPACT_LABELS = ['trivial', 'minor', 'moderate', 'major', 'defining'];

export default function AddEvent() {
  const { profileId } = useLocalSearchParams<{ profileId: string }>();
  const [category, setCategory] = useState<string | null>(null);
  const [subCategory, setSubCategory] = useState<string | null>(null);
  const [date, setDate] = useState('');
  const [precision, setPrecision] = useState<Precision>('exact');
  const [impact, setImpact] = useState(3);
  const [description, setDescription] = useState('');
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(0);

  const { data: taxonomy } = useQuery({ queryKey: ['taxonomy'], queryFn: getTaxonomy });
  const { data: timeline, refetch } = useQuery({
    queryKey: ['timeline', profileId],
    queryFn: () => getTimeline(profileId!),
  });

  React.useEffect(() => {
    pendingEventCount().then(setPending);
  }, [saved]);

  const save = async () => {
    if (!category || !subCategory || !date) {
      Alert.alert('Missing fields', 'Category, sub-category and date are required.');
      return;
    }
    const { sent } = await addEvent(profileId!, {
      category,
      sub_category: subCategory,
      date,
      precision,
      impact,
      certainty: 3,
      description,
    });
    setSaved(true);
    setDate('');
    setDescription('');
    refetch();
    pendingEventCount().then(setPending);

    if (!sent) {
      Alert.alert(
        'Saved on device',
        'The server was unreachable, so this event is queued and will be sent automatically.',
      );
    }
  };

  const retry = async () => {
    await flushOutbox();
    pendingEventCount().then(setPending);
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Add past event</Text>
      <Text style={styles.subtitle}>
        Record how precisely you actually know the date. A year-only answer is
        treated as a range, not as 1 January.
      </Text>

      {pending > 0 && (
        <Pressable style={styles.pendingBanner} onPress={retry}>
          <Text style={styles.pendingText}>
            {pending} event{pending > 1 ? 's' : ''} waiting to sync — tap to retry
          </Text>
        </Pressable>
      )}

      <Text style={styles.label}>Category</Text>
      <View style={styles.chips}>
        {Object.keys(taxonomy?.categories ?? {}).map((c) => (
          <Chip
            key={c}
            label={c}
            active={category === c}
            onPress={() => {
              setCategory(c);
              setSubCategory(null);
            }}
          />
        ))}
      </View>

      {category && (
        <>
          <Text style={styles.label}>Sub-category</Text>
          <View style={styles.chips}>
            {(taxonomy?.categories[category] ?? []).map((s) => (
              <Chip
                key={s}
                label={s.replace(/_/g, ' ')}
                active={subCategory === s}
                onPress={() => setSubCategory(s)}
              />
            ))}
          </View>
        </>
      )}

      <Text style={styles.label}>Date ({precision})</Text>
      <View style={styles.chips}>
        {(taxonomy?.precisions ?? ['exact']).map((p) => (
          <Chip
            key={p}
            label={p}
            active={precision === p}
            onPress={() => setPrecision(p)}
          />
        ))}
      </View>

      <View style={styles.inputRow}>
        {(['exact', 'month', 'quarter', 'year'] as Precision[]).includes(precision) ? (
          <TextInputCompat value={date} onChange={setDate} />
        ) : null}
      </View>
      <Text style={styles.hint}>
        {precision === 'year' && 'Format: 1998'}
        {precision === 'quarter' && 'Format: 1998-Q2'}
        {precision === 'month' && 'Format: 1998-06'}
        {precision === 'exact' && 'Format: 1998-06-15'}
      </Text>

      <Text style={styles.label}>Impact: {IMPACT_LABELS[impact - 1]}</Text>
      <View style={styles.chips}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Chip key={n} label={String(n)} active={impact === n} onPress={() => setImpact(n)} />
        ))}
      </View>

      <TextInputCompat value={description} onChange={setDescription} placeholder="Description (optional)" />

      <Pressable style={styles.button} onPress={save}>
        <Text style={styles.buttonText}>Save event</Text>
      </Pressable>
      {saved && <Text style={styles.saved}>Saved</Text>}

      <Text style={styles.sectionTitle}>Timeline</Text>
      {(timeline?.events ?? []).map((e: any) => (
        <View key={e.event_id} style={styles.eventRow}>
          <Text style={styles.eventDate}>
            {e.start.start}
            {e.start.precision !== 'exact' && ` – ${e.start.end}`}
          </Text>
          <Text style={styles.eventCat}>
            {e.category} / {e.sub_category.replace(/_/g, ' ')}
          </Text>
          <Text style={styles.eventPrecision}>
            {e.start.precision} · {e.candidate_dates} candidate date
            {e.candidate_dates === 1 ? '' : 's'} ·{' '}
            {e.dasha_configurations.length} dasha configuration
            {e.dasha_configurations.length === 1 ? '' : 's'}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.chip, active && styles.chipActive]} onPress={onPress}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

function TextInputCompat({ value, onChange, placeholder }: { value: string; onChange: (t: string) => void; placeholder?: string }) {
  const { TextInput } = require('react-native');
  return (
    <TextInput
      style={styles.input}
      value={value}
      onChangeText={onChange}
      placeholder={placeholder}
      placeholderTextColor="#aaa"
      autoCapitalize="none"
    />
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 60, backgroundColor: '#faf8f2' },
  title: { fontSize: 22, fontWeight: '700', color: '#1a1a1a' },
  subtitle: { fontSize: 13, color: '#666', marginTop: 4, marginBottom: 16, lineHeight: 18 },
  pendingBanner: { backgroundColor: '#fff4e0', borderRadius: 8, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: '#e8c98a' },
  pendingText: { color: '#8a6d3b', fontSize: 13, fontWeight: '600' },
  label: { fontSize: 12, fontWeight: '600', color: '#444', marginBottom: 6, marginTop: 14 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16, backgroundColor: '#fff', borderWidth: 1, borderColor: '#ddd' },
  chipActive: { backgroundColor: '#1f5c3d', borderColor: '#1f5c3d' },
  chipText: { fontSize: 12, color: '#444' },
  chipTextActive: { color: '#fff' },
  inputRow: { marginTop: 12 },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 12, fontSize: 15, backgroundColor: '#fff', color: '#1a1a1a', marginTop: 10 },
  hint: { fontSize: 11, color: '#999', marginTop: 4 },
  button: { backgroundColor: '#1f5c3d', padding: 15, borderRadius: 10, alignItems: 'center', marginTop: 20 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  saved: { textAlign: 'center', color: '#1f5c3d', marginTop: 10, fontSize: 13 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#1f5c3d', marginTop: 28, marginBottom: 8, textTransform: 'uppercase' },
  eventRow: { paddingVertical: 8, borderBottomWidth: 0.5, borderBottomColor: '#e8e8e8' },
  eventDate: { fontSize: 13, fontWeight: '600', color: '#333' },
  eventCat: { fontSize: 13, color: '#555' },
  eventPrecision: { fontSize: 11, color: '#999' },
});
