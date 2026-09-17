/**
 * Built-in theme presets.
 */

import type { ThemeData } from './types';

export const PRESETS: ThemeData[] = [
  {
    id: 'preset-midnight',
    name: 'Midnight Blue',
    base: 'dark',
    colors: {
      bg: '#0b0e1a',
      card: '#141929',
      text: '#d4daf0',
      muted: '#7a84a0',
      border: '#1e2540',
      accent: '#4a8eff',
      btnBg: '#161c30',
      btnText: '#d4daf0',
      btnHover: '#1e2845',
    },
    effects: {
      shadow: '0 8px 24px rgba(10,20,60,0.5)',
    },
  },
  {
    id: 'preset-sakura',
    name: 'Sakura',
    base: 'light',
    colors: {
      bg: '#fef5f7',
      card: '#ffffff',
      text: '#3a2a30',
      muted: '#9a7a85',
      border: '#f0d8de',
      accent: '#d4548a',
      btnBg: '#fff0f4',
      btnText: '#3a2a30',
      btnHover: '#fde0e8',
    },
    effects: {
      shadow: '0 4px 16px rgba(200,80,130,0.1)',
    },
  },
  {
    id: 'preset-forest',
    name: 'Forest',
    base: 'dark',
    colors: {
      bg: '#0a120e',
      card: '#12201a',
      text: '#d0e8dc',
      muted: '#6a9a80',
      border: '#1a3028',
      accent: '#3abf7a',
      btnBg: '#142820',
      btnText: '#d0e8dc',
      btnHover: '#1c3a2e',
    },
    effects: {
      shadow: '0 8px 24px rgba(0,40,20,0.4)',
    },
  },
  {
    id: 'preset-ocean',
    name: 'Ocean',
    base: 'dark',
    colors: {
      bg: '#0a1218',
      card: '#122030',
      text: '#d0e4f0',
      muted: '#6a90b0',
      border: '#1a3048',
      accent: '#20c4d4',
      btnBg: '#142838',
      btnText: '#d0e4f0',
      btnHover: '#1c3850',
    },
    effects: {
      shadow: '0 8px 24px rgba(0,30,60,0.5)',
    },
  },
  {
    id: 'preset-retro-neon',
    name: 'Retro Neon',
    base: 'dark',
    colors: {
      bg: '#0a0014',
      card: '#120024',
      text: '#e0d0ff',
      muted: '#a080d0',
      border: '#2a1050',
      accent: '#bf5af2',
      btnBg: '#1a0038',
      btnText: '#e0d0ff',
      btnHover: '#2a1050',
    },
    effects: {
      shadow: '0 0 20px rgba(160,80,255,0.3)',
      glow: true,
      navGradient: 'linear-gradient(90deg, #0a0014 0%, #1a0040 50%, #0a0014 100%)',
    },
  },
];

export function getPresetById(id: string): ThemeData | undefined {
  return PRESETS.find(p => p.id === id);
}
