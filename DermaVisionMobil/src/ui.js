import React, { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Path } from 'react-native-svg';

const LIGHT = { bg: '#F3F7FC', card: '#FFFFFF', line: '#D9E2F0', ink: '#14284B', mute: '#5B6B86', navy: '#1B3A6B', blue: '#2A66C8', tint: '#E8F0FB', ok: '#1D7A4D', err: '#B3261E' };
const DARK = { bg: '#0E1626', card: '#16213A', line: '#2A3858', ink: '#E6ECF8', mute: '#9AA9C4', navy: '#3B6BC4', blue: '#7FA8F0', tint: '#1C2B4C', ok: '#5CCB97', err: '#F2928C' };
export const useTheme = () => (useColorScheme() === 'dark' ? DARK : LIGHT);

export function Logo({ size = 38 }) {
  const c = useTheme();
  return (
    <Svg width={size} height={size} viewBox="0 0 40 40">
      <Path d="M20 3 6 8v10c0 9 6 16 14 19 8-3 14-10 14-19V8z" fill={c.navy} />
      <Circle cx="19" cy="19" r="6.5" fill="none" stroke="#fff" strokeWidth={2.4} />
      <Path d="M24 24 L30 30" stroke="#fff" strokeWidth={2.6} strokeLinecap="round" />
    </Svg>
  );
}

export function Brand({ right }) {
  const c = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 22 }}>
      <Logo />
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: c.ink }}>DermaVision</Text>
        <Text style={{ fontSize: 11, fontWeight: '500', color: c.blue }}>AI Dermatology</Text>
      </View>
      {right}
    </View>
  );
}

export function Screen({ children, menu = false }) {
  const c = useTheme();
  return (
    <SafeAreaView edges={menu ? ['top'] : ['top', 'bottom']} style={{ flex: 1, backgroundColor: c.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 18, paddingBottom: 36, maxWidth: 420, width: '100%', alignSelf: 'center' }}>
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export const H1 = ({ children, style }) => {
  const c = useTheme();
  return <Text style={[{ fontSize: 28, lineHeight: 33, fontWeight: '700', color: c.ink, marginBottom: 8, letterSpacing: -0.4 }, style]}>{children}</Text>;
};
export const Sub = ({ children, style }) => {
  const c = useTheme();
  return <Text style={[{ fontSize: 14, color: c.mute, marginBottom: 22, lineHeight: 21 }, style]}>{children}</Text>;
};
export const Note = ({ children, style }) => {
  const c = useTheme();
  return <Text style={[{ fontSize: 12, color: c.mute, textAlign: 'center', marginTop: 12, lineHeight: 18 }, style]}>{children}</Text>;
};
export const ErrText = ({ children, style }) => {
  const c = useTheme();
  return children ? <Text style={[{ color: c.err, fontSize: 13, marginBottom: 10 }, style]}>{children}</Text> : null;
};
export const Link = ({ children, onPress, style }) => {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} hitSlop={8}>
      <Text style={[{ color: c.blue, fontWeight: '600', fontSize: 13 }, style]}>{children}</Text>
    </Pressable>
  );
};

export function Field({ label, icon, error, secure, ...props }) {
  const c = useTheme();
  const [hide, setHide] = useState(true);
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Text style={{ fontSize: 13, fontWeight: '600', color: c.ink, marginBottom: 6 }}>{label}</Text> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: c.card, borderWidth: 1, borderColor: error ? c.err : c.line, borderRadius: 12, paddingHorizontal: 14, height: 48 }}>
        {icon ? <Ionicons name={icon} size={20} color={c.mute} /> : null}
        <TextInput
          style={{ flex: 1, color: c.ink, fontSize: 15 }}
          placeholderTextColor={c.mute}
          secureTextEntry={secure && hide}
          autoCapitalize="none"
          autoCorrect={false}
          {...props}
        />
        {secure ? (
          <Pressable onPress={() => setHide(!hide)} hitSlop={10} accessibilityLabel={hide ? 'Şifreyi göster' : 'Şifreyi gizle'}>
            <Ionicons name={hide ? 'eye-outline' : 'eye-off-outline'} size={20} color={c.mute} />
          </Pressable>
        ) : null}
      </View>
      {error ? <Text style={{ color: c.err, fontSize: 12.5, marginTop: 4 }}>{error}</Text> : null}
    </View>
  );
}

export function Btn({ title, onPress, variant = 'p', disabled, loading, icon, iconRight, style }) {
  const c = useTheme();
  const p = variant === 'p';
  const fg = p ? '#fff' : c.ink;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        { height: 50, borderRadius: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: p ? c.navy : c.card, borderWidth: 1, borderColor: p ? 'transparent' : c.line, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon ? <Ionicons name={icon} size={20} color={fg} /> : null}
          <Text style={{ fontWeight: '600', fontSize: 15, color: fg }}>{title}</Text>
          {iconRight ? <Ionicons name={iconRight} size={20} color={fg} /> : null}
        </>
      )}
    </Pressable>
  );
}

export function Check({ checked, onChange, children, style }) {
  const c = useTheme();
  return (
    <Pressable onPress={() => onChange(!checked)} accessibilityRole="checkbox" accessibilityState={{ checked }} style={[{ flexDirection: 'row', gap: 10, alignItems: 'flex-start', marginBottom: 14 }, style]}>
      <View style={{ width: 20, height: 20, borderRadius: 5, borderWidth: 1.5, borderColor: checked ? c.navy : c.mute, backgroundColor: checked ? c.navy : 'transparent', alignItems: 'center', justifyContent: 'center', marginTop: 1 }}>
        {checked ? <Ionicons name="checkmark" size={14} color="#fff" /> : null}
      </View>
      <Text style={{ flex: 1, fontSize: 13, color: c.mute, lineHeight: 19 }}>{children}</Text>
    </Pressable>
  );
}

export function Choice({ selected, onPress, label, style }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="radio" accessibilityState={{ selected }} style={[{ height: 46, borderRadius: 12, borderWidth: 1, borderColor: selected ? c.navy : c.line, backgroundColor: selected ? c.tint : c.card, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }, style]}>
      <Ionicons name={selected ? 'radio-button-on' : 'radio-button-off'} size={18} color={selected ? c.navy : c.mute} />
      <Text style={{ fontSize: 13, color: c.ink, fontWeight: '500' }}>{label}</Text>
    </Pressable>
  );
}

export function Toast({ message, bottom }) {
  const c = useTheme();
  if (!message) return null;
  return (
    <View pointerEvents="none" style={{ position: 'absolute', left: 0, right: 0, bottom, alignItems: 'center' }}>
      <View style={{ backgroundColor: c.ink, borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16, maxWidth: '90%' }}>
        <Text style={{ color: c.bg, fontSize: 13, textAlign: 'center' }}>{message}</Text>
      </View>
    </View>
  );
}
