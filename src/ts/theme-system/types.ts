/**
 * Theme system type definitions.
 */

export interface ThemeColors {
  bg: string;
  card: string;
  text: string;
  muted: string;
  border: string;
  accent: string;
  btnBg?: string;
  btnText?: string;
  btnHover?: string;
}

export interface ThemeEffects {
  shadow?: string;
  glow?: boolean;
  navGradient?: string;
}

export interface ThemeData {
  id: string;
  name: string;
  base: 'light' | 'dark';
  colors: ThemeColors;
  effects?: ThemeEffects;
}
