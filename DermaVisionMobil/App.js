import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api, getToken, setToken } from './src/api';
import { Toast, useTheme } from './src/ui';
import { Forgot, Login, Signup, Welcome } from './src/screens/Auth';
import { Done, Upload } from './src/screens/Upload';

const SEKMELER = [
  { id: 'up', ad: 'Yükle', ikon: 'scan-outline' },
  { id: 'x1', ad: 'Açıklama', ikon: 'document-text-outline' },
  { id: 'x2', ad: 'Hastaneler', ikon: 'location-outline' },
  { id: 'x3', ad: 'Profil', ikon: 'person-outline' },
];

function Root() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const [screen, setScreen] = useState(null); // null = oturum kontrol ediliyor
  const [photo, setPhoto] = useState(null);
  const [toastMsg, setToastMsg] = useState('');
  const tt = useRef();

  const toast = useCallback((m, ms = 3500) => {
    setToastMsg(m);
    clearTimeout(tt.current);
    tt.current = setTimeout(() => setToastMsg(''), ms);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        if (await getToken()) { await api('/api/ben'); setScreen('up'); return; }
      } catch (e) {}
      setScreen('welcome');
    })();
  }, []);

  const logout = async () => { await setToken(null); setPhoto(null); setScreen('login'); };

  if (!screen) {
    return <View style={{ flex: 1, backgroundColor: c.bg, justifyContent: 'center' }}><ActivityIndicator color={c.blue} /></View>;
  }
  const menu = screen === 'up' || screen === 'done';

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <StatusBar style="auto" />
      <View style={{ flex: 1 }}>
        {screen === 'welcome' && <Welcome onStart={() => setScreen('login')} />}
        {screen === 'login' && <Login go={setScreen} toast={toast} onLogin={() => setScreen('up')} />}
        {screen === 'forgot' && <Forgot go={setScreen} toast={toast} />}
        {screen === 'signup' && <Signup go={setScreen} toast={toast} />}
        {screen === 'up' && (
          <Upload
            onLogout={logout}
            onDone={(a) => { setPhoto(a); setScreen('done'); }}
            onExpired={() => { toast('Oturum süresi doldu, tekrar giriş yapın.'); setScreen('login'); }}
          />
        )}
        {screen === 'done' && <Done photo={photo} onAgain={() => { setPhoto(null); setScreen('up'); }} />}
      </View>

      {menu && (
        <View style={{ flexDirection: 'row', backgroundColor: c.card, borderTopWidth: 1, borderTopColor: c.line, paddingBottom: insets.bottom }}>
          {SEKMELER.map((t) => {
            const on = t.id === 'up';
            return (
              <Pressable key={t.id} style={{ flex: 1, alignItems: 'center', gap: 3, paddingTop: 10, paddingBottom: 8 }} onPress={() => (on ? setScreen('up') : toast('Bu bölüm sonraki aşamada eklenecek.'))}>
                <View style={{ backgroundColor: on ? c.tint : 'transparent', paddingHorizontal: 14, paddingVertical: 4, borderRadius: 999 }}>
                  <Ionicons name={t.ikon} size={20} color={on ? c.blue : c.mute} />
                </View>
                <Text style={{ fontSize: 11, fontWeight: '500', color: on ? c.blue : c.mute }}>{t.ad}</Text>
              </Pressable>
            );
          })}
        </View>
      )}
      <Toast message={toastMsg} bottom={24 + (menu ? 64 + insets.bottom : insets.bottom)} />
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <Root />
    </SafeAreaProvider>
  );
}
