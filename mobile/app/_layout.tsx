import React from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Charts are immutable once computed, so they are cached aggressively.
      // This is what makes previously calculated charts work offline.
      staleTime: 1000 * 60 * 60 * 24,
      gcTime: 1000 * 60 * 60 * 24 * 7,
      retry: 1,
    },
  },
});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: '#1f5c3d' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
          contentStyle: { backgroundColor: '#faf8f2' },
        }}
      >
        <Stack.Screen name="index" options={{ title: 'Vedic Chart' }} />
        <Stack.Screen name="create-profile" options={{ title: 'New profile' }} />
        <Stack.Screen name="chart" options={{ title: 'Chart' }} />
        <Stack.Screen name="add-event" options={{ title: 'Events' }} />
        <Stack.Screen name="predictions" options={{ title: 'Predictions' }} />
      </Stack>
    </QueryClientProvider>
  );
}
