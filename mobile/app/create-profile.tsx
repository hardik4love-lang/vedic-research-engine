import React, { useState } from 'react';
import {
  Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import {
  createProfile, getChart, getCities, type BirthInput, type CityResult,
} from '../src/lib/api';

/**
 * Three required fields: name, date, time. City fills in the rest.
 *
 * Coordinates and timezone are deliberately not asked for. For births before
 * about 1900 there is an "advanced" escape hatch, because a named timezone
 * zone is often subtly wrong for those and the difference can move the
 * ascendant by several degrees.
 */
export default function CreateProfile() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [city, setCity] = useState<CityResult | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CityResult[]>([]);
  const [advanced, setAdvanced] = useState(false);
  const [offset, setOffset] = useState('');
  const [busy, setBusy] = useState(false);

  const search = async (q: string) => {
    setQuery(q);
    if (!q.trim()) return setResults([]);
    try {
      setResults((await getCities(q)).cities);
    } catch {
      setResults([]);
    }
  };

  const oldYear = date.length === 10 && Number(date.slice(0, 4)) < 1900;

  const submit = async () => {
    if (!name || !date || !time) {
      Alert.alert('Missing fields', 'Name, date and time are all that is needed.');
      return;
    }
    setBusy(true);
    try {
      const birth: BirthInput = {
        name,
        birth_date: date,
        birth_time: time,
        city: city?.name,
        utc_offset: offset ? `+${offset}` : null,
      };
      const preview = await getChart(birth);
      const { profile_id: profileId } = await createProfile(birth);
      router.push({
        pathname: '/chart',
        params: { profileId, lagna: String(preview.chart.lagna.sign_name) },
      });
    } catch (err: any) {
      Alert.alert('Could not create profile', String(err?.message ?? err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>New profile</Text>

        <Field label="Name" value={name} onChangeText={setName} placeholder="e.g. Einstein" />
        <Field label="Date of birth" value={date} onChangeText={setDate} placeholder="1879-03-14" />
        <Field label="Time of birth" value={time} onChangeText={setTime} placeholder="11:30" />

        <Text style={styles.label}>{city ? 'City' : 'City (optional)'}</Text>
        {city ? (
          <Pressable onPress={() => { setCity(null); setQuery(''); }}>
            <View style={styles.picked}>
              <Text style={styles.pickedName}>{city.name}</Text>
              <Text style={styles.pickedMeta}>
                {city.country} · {city.timezone.replace('_', ' ')}
              </Text>
              <Text style={styles.pickedChange}>change</Text>
            </View>
          </Pressable>
        ) : (
          <>
            <TextInput
              style={styles.input}
              value={query}
              onChangeText={search}
              placeholder="Start typing a city…"
              placeholderTextColor="#aaa"
              autoCapitalize="words"
            />
            {results.map((c) => (
              <Pressable
                key={c.name}
                style={styles.cityRow}
                onPress={() => { setCity(c); setQuery(''); setResults([]); }}
              >
                <Text style={styles.cityName}>{c.name}</Text>
                <Text style={styles.cityCountry}>{c.country}</Text>
              </Pressable>
            ))}
            {query && results.length === 0 && (
              <Text style={styles.none}>
                No match. Leave blank to use the default (Delhi, IST).
              </Text>
            )}
          </>
        )}

        {!city && (
          <Text style={styles.note}>
            No city selected — Delhi coordinates and IST will be used.
          </Text>
        )}

        {(advanced || oldYear) && (
          <View style={styles.advanced}>
            <Text style={styles.advancedTitle}>
              {oldYear ? 'Needed for a pre-1900 birth' : 'Advanced'}
            </Text>
            <Text style={styles.advancedBody}>
              Before about 1900 most zones used local mean time, which two
              sources derive differently. The difference is small but can move
              the ascendant several degrees. Enter the UTC offset recorded
              with the birth certificate if you have one, e.g.{' '}
              {city?.timezone === 'Europe/Berlin' ? '+00:40' : '+05:30'}.
            </Text>
            <TextInput
              style={styles.input}
              value={offset}
              onChangeText={setOffset}
              placeholder="+05:30"
              placeholderTextColor="#aaa"
              autoCapitalize="none"
            />
          </View>
        )}

        <Pressable
          style={styles.toggle}
          onPress={() => setAdvanced((v) => !v)}
        >
          <Text style={styles.toggleText}>
            {advanced ? 'Hide advanced' : 'Advanced: set exact UTC offset'}
          </Text>
        </Pressable>

        <Pressable style={styles.button} onPress={submit} disabled={busy}>
          <Text style={styles.buttonText}>{busy ? 'Computing…' : 'Create profile'}</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({
  label, value, onChangeText, placeholder,
}: {
  label: string;
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#aaa"
        autoCapitalize="none"
        autoCorrect={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#faf8f2' },
  container: { padding: 20, paddingBottom: 60 },
  title: { fontSize: 24, fontWeight: '700', color: '#1a1a1a', marginBottom: 20 },
  field: { marginBottom: 14 },
  label: { fontSize: 12, fontWeight: '600', color: '#444', marginBottom: 4 },
  input: {
    borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 13,
    fontSize: 16, backgroundColor: '#fff', color: '#1a1a1a',
  },
  cityRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 12, paddingHorizontal: 13,
    backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#eee',
  },
  cityName: { fontSize: 15, color: '#1a1a1a' },
  cityCountry: { fontSize: 13, color: '#888' },
  none: { fontSize: 12, color: '#999', marginTop: 8 },
  note: { fontSize: 12, color: '#888', marginTop: 10, marginBottom: 4 },
  picked: {
    borderWidth: 1, borderColor: '#1f5c3d', borderRadius: 8,
    padding: 13, backgroundColor: '#f0f7f2',
  },
  pickedName: { fontSize: 16, color: '#1a1a1a', fontWeight: '600' },
  pickedMeta: { fontSize: 12, color: '#666', marginTop: 2 },
  pickedChange: { fontSize: 12, color: '#1f5c3d', marginTop: 6 },
  advanced: {
    backgroundColor: '#fff8ec', borderRadius: 10, padding: 14,
    marginTop: 16, borderWidth: 1, borderColor: '#e8d9b0',
  },
  advancedTitle: { fontSize: 12, fontWeight: '700', color: '#8a6d3b', marginBottom: 6 },
  advancedBody: { fontSize: 12, color: '#7a6440', lineHeight: 18, marginBottom: 10 },
  toggle: { marginTop: 18, alignItems: 'center' },
  toggleText: { fontSize: 13, color: '#1f5c3d', fontWeight: '600' },
  button: {
    backgroundColor: '#1f5c3d', padding: 16, borderRadius: 10,
    alignItems: 'center', marginTop: 18,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});